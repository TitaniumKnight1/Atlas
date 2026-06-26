from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Callable

from backend.adapters.persistence import AutomationRepository
from backend.application.automation.actions import AutomationActionExecutor, action_execution_tier
from backend.domain.automation import (
    RunStatus,
    StepStatus,
    TriggerType,
    automation_approval_granted,
    automation_approval_rejected,
    automation_approval_requested,
    automation_run_completed,
    automation_run_failed,
    automation_triggered,
    evaluate_conditions,
    recipe_run_halted,
)
from backend.domain.automation.types import ApprovalState, ExecutionTier
from backend.domain.shared_kernel import ErrorCode, ProjectId, StableIdentifier
from backend.domain.shared_kernel.events import DomainEventEnvelope


_EVENT_TRIGGER_MAP = {
    "AlertFired": TriggerType.ALERT_FIRED,
    "ServerCrashed": TriggerType.SERVER_CRASHED,
}


class AutomationEngine:
    """Trigger→action execution with approvals, idempotent runs, and stop-and-hold."""

    def __init__(self, *, container: Any, clock: Callable[[], datetime] | None = None) -> None:
        self._container = container
        self._clock = clock or (lambda: datetime.now(UTC))
        self._executor = AutomationActionExecutor(container=container, filesystem=container.setup_filesystem)

    def handle_domain_event(self, envelope: DomainEventEnvelope) -> list[dict[str, Any]]:
        if envelope.project_id is None or not self._is_globally_enabled():
            return []
        trigger_type = _resolve_trigger_type(envelope)
        if trigger_type is None:
            return []
        idempotency_key = _event_idempotency_key(envelope)
        return self._run_matching_workflows(
            project_id=envelope.project_id,
            trigger_type=trigger_type.value,
            trigger_payload=dict(envelope.payload),
            idempotency_key=idempotency_key,
        )

    def trigger_schedule(self, schedule_id: str) -> dict[str, Any] | None:
        if not self._is_globally_enabled():
            return {"status": RunStatus.SKIPPED.value, "reason": "global_disabled"}
        now = self._clock()
        with self._container.session_factory() as session:
            from backend.adapters.persistence.models import AutomationScheduleRecord

            schedule_row = session.get(AutomationScheduleRecord, schedule_id)
            if schedule_row is None:
                return None
            project_id = ProjectId(schedule_row.project_id)
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(AutomationRepository)
            schedule = repository.get_schedule(project_id, schedule_id)
            if schedule is None or not schedule.is_enabled:
                uow.rollback()
                return None
            workflow = repository.get_workflow(project_id, schedule.automation_workflow_id)
            if workflow is None or not workflow.is_enabled or workflow.current_version_id is None:
                uow.rollback()
                return {"status": RunStatus.SKIPPED.value, "reason": "workflow_disabled"}
            if schedule.next_run_at > now.isoformat():
                uow.rollback()
                return {"status": RunStatus.SKIPPED.value, "reason": "not_due"}
            due_at = schedule.next_run_at
            idempotency_key = f"schedule:{schedule.automation_schedule_id}:{due_at}"
            result = self._start_run(
                uow=uow,
                repository=repository,
                project_id=project_id,
                workflow=workflow,
                version_id=workflow.current_version_id,
                trigger_type=TriggerType.SCHEDULE.value,
                trigger_payload={"schedule_id": schedule.automation_schedule_id, "due_at": due_at},
                idempotency_key=idempotency_key,
            )
            if result.get("status") == RunStatus.SKIPPED.value:
                uow.commit()
                return result
            uow.commit()
        if result.get("status") not in {RunStatus.WAITING_APPROVAL.value, RunStatus.SKIPPED.value}:
            result = self._continue_run(project_id, result["automation_run_id"], start_after_position=-1)
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(AutomationRepository)
            schedule = repository.get_schedule(project_id, schedule_id)
            if schedule is not None:
                interval_seconds = int((schedule.schedule_json or {}).get("interval_seconds", 60))
                next_run = datetime.fromisoformat(due_at)
                while next_run <= now:
                    next_run = next_run + timedelta(seconds=interval_seconds)
                repository.advance_schedule(schedule, next_run_at=next_run, last_run_at=now)
            uow.commit()
        return result

    def run_manual(
        self,
        project_id: ProjectId,
        workflow_id: str,
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if not self._is_globally_enabled():
            return {"status": RunStatus.SKIPPED.value, "reason": "global_disabled"}
        now = self._clock()
        key = idempotency_key or f"manual:{workflow_id}:{now.isoformat()}"
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(AutomationRepository)
            workflow = repository.get_workflow(project_id, workflow_id)
            if workflow is None or not workflow.is_enabled or workflow.current_version_id is None:
                uow.rollback()
                raise AutomationEngineError(ErrorCode.NOT_FOUND, f"Workflow not found or disabled: {workflow_id}")
            result = self._start_run(
                uow=uow,
                repository=repository,
                project_id=project_id,
                workflow=workflow,
                version_id=workflow.current_version_id,
                trigger_type=TriggerType.MANUAL.value,
                trigger_payload={"workflow_id": workflow_id},
                idempotency_key=key,
            )
            if result.get("status") == RunStatus.SKIPPED.value:
                uow.commit()
                return result
            uow.commit()
        if result.get("status") == RunStatus.WAITING_APPROVAL.value:
            return result
        return self._continue_run(project_id, result["automation_run_id"], start_after_position=-1)

    def approve_run(self, project_id: ProjectId, run_id: str, approval_id: str, *, decided_by: str | None = None) -> dict[str, Any]:
        if not self._is_globally_enabled():
            raise AutomationEngineError(ErrorCode.PRECONDITION_FAILED, "Automation globally disabled")
        now = self._clock()
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(AutomationRepository)
            approval = repository.get_approval(project_id, approval_id)
            if approval is None or approval.automation_run_id != run_id:
                uow.rollback()
                raise AutomationEngineError(ErrorCode.NOT_FOUND, f"Approval not found: {approval_id}")
            if approval.approval_state != ApprovalState.PENDING.value:
                uow.rollback()
                raise AutomationEngineError(ErrorCode.CONFLICT, f"Approval is not pending: {approval.approval_state}")
            run = repository.get_run(project_id, run_id)
            if run is None or run.status != RunStatus.WAITING_APPROVAL.value:
                uow.rollback()
                raise AutomationEngineError(ErrorCode.CONFLICT, "Run is not waiting for approval")
            step = repository.get_run_step(project_id, approval.automation_run_step_id)
            if step is None:
                uow.rollback()
                raise AutomationEngineError(ErrorCode.NOT_FOUND, "Approval step not found")
            actions = repository.list_actions(run.automation_workflow_version_id)
            action = next((item for item in actions if item.automation_action_id == approval.automation_action_id), None)
            if action is None:
                uow.rollback()
                raise AutomationEngineError(ErrorCode.NOT_FOUND, "Action not found for approval")
            repository.decide_approval(approval, state=ApprovalState.APPROVED.value, decided_at=now, decided_by=decided_by)
            uow.collect_event(automation_approval_granted(project_id, run_id, approval_id))
            run.status = RunStatus.RUNNING.value
            uow.commit()
        trigger_payload = run.trigger_payload_json or {}
        step_key = f"{run.idempotency_key}:action:{action.automation_action_id}:approved"
        try:
            result = self._executor.execute(
                project_id=project_id,
                action_type=action.action_type,
                safety_class=action.safety_class,
                config=action.config_json or {},
                trigger_payload=trigger_payload,
                idempotency_key=step_key,
            )
        except Exception as error:
            return self._halt_run(
                project_id,
                run_id,
                failed_position=step.position,
                message=str(error),
                step_id=step.automation_run_step_id,
                step_error=str(error),
            )
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(AutomationRepository)
            step = repository.get_run_step(project_id, step.automation_run_step_id)
            assert step is not None
            step.status = StepStatus.SUCCEEDED.value if not result.get("skipped") else StepStatus.SKIPPED.value
            step.result_json = result
            step.command_execution_id = result.get("command_execution_id")
            step.undo_plan_json = result.get("undo_plan_json")
            uow.commit()
        return self._continue_run(project_id, run_id, start_after_position=step.position)

    def reject_run(
        self,
        project_id: ProjectId,
        run_id: str,
        approval_id: str,
        *,
        reason: str | None = None,
        decided_by: str | None = None,
    ) -> dict[str, Any]:
        now = self._clock()
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(AutomationRepository)
            approval = repository.get_approval(project_id, approval_id)
            if approval is None or approval.automation_run_id != run_id:
                uow.rollback()
                raise AutomationEngineError(ErrorCode.NOT_FOUND, f"Approval not found: {approval_id}")
            if approval.approval_state != ApprovalState.PENDING.value:
                uow.rollback()
                raise AutomationEngineError(ErrorCode.CONFLICT, f"Approval is not pending: {approval.approval_state}")
            run = repository.get_run(project_id, run_id)
            if run is None:
                uow.rollback()
                raise AutomationEngineError(ErrorCode.NOT_FOUND, f"Run not found: {run_id}")
            step = repository.get_run_step(project_id, approval.automation_run_step_id)
            if step is not None:
                step.status = StepStatus.REJECTED.value
                step.result_json = {"rejected": True, "reason": reason}
            repository.decide_approval(
                approval,
                state=ApprovalState.DENIED.value,
                decided_at=now,
                decided_by=decided_by,
                reason=reason,
            )
            self._mark_remaining_not_attempted(repository, run_id, project_id=project_id, after_position=step.position if step else -1)
            repository.finish_run(
                run,
                status=RunStatus.CANCELLED.value,
                finished_at=now,
                summary=reason or "Approval rejected",
            )
            uow.collect_event(automation_approval_rejected(project_id, run_id, approval_id, reason or "rejected"))
            uow.commit()
        return {"automation_run_id": run_id, "status": RunStatus.CANCELLED.value, "approval_id": approval_id}

    def undo_run_step(self, project_id: ProjectId, step_id: str) -> dict[str, Any]:
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(AutomationRepository)
            step = repository.get_run_step(project_id, step_id)
            if step is None or not step.undo_plan_json:
                uow.rollback()
                raise AutomationEngineError(ErrorCode.NOT_FOUND, f"Undo not available for step: {step_id}")
            result = self._executor.undo_step(uow=uow, undo_plan_json=step.undo_plan_json)
            step.result_json = {**(step.result_json or {}), "undone": True, "undo_result": result}
            step.status = StepStatus.SUCCEEDED.value
            uow.commit()
        return {"step_id": step_id, "undo_result": result}

    def _run_matching_workflows(
        self,
        *,
        project_id: ProjectId,
        trigger_type: str,
        trigger_payload: dict[str, Any],
        idempotency_key: str,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        with self._container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext

            matches = AutomationRepository(RepositoryContext(session=session, project_id=project_id)).list_enabled_event_workflows(
                project_id, trigger_type
            )
        for workflow_row, version_row in matches:
            workflow_id = workflow_row.automation_workflow_id
            version_id = version_row.automation_workflow_version_id
            with self._container.session_factory() as session:
                from backend.infrastructure.unit_of_work import RepositoryContext

                repository = AutomationRepository(RepositoryContext(session=session, project_id=project_id))
                conditions = [
                    {"condition_type": item.condition_type, "config_json": item.config_json or {}}
                    for item in repository.list_conditions(version_id)
                ]
            if not evaluate_conditions(conditions, trigger_payload):
                results.append({"workflow_id": workflow_id, "status": RunStatus.SKIPPED.value, "reason": "conditions_not_met"})
                continue
            workflow_key = f"{idempotency_key}:workflow:{workflow_id}"
            with self._container.create_unit_of_work(project_id) as uow:
                uow.begin()
                repository = uow.repository(AutomationRepository)
                workflow = repository.get_workflow(project_id, workflow_id)
                if workflow is None or not workflow.is_enabled or workflow.current_version_id is None:
                    uow.rollback()
                    continue
                result = self._start_run(
                    uow=uow,
                    repository=repository,
                    project_id=project_id,
                    workflow=workflow,
                    version_id=version_id,
                    trigger_type=trigger_type,
                    trigger_payload=trigger_payload,
                    idempotency_key=workflow_key,
                )
                if result.get("status") == RunStatus.SKIPPED.value:
                    uow.commit()
                    results.append(result)
                    continue
                uow.commit()
            if result.get("status") == RunStatus.WAITING_APPROVAL.value:
                results.append(result)
                continue
            results.append(self._continue_run(project_id, result["automation_run_id"], start_after_position=-1))
        return results

    def _start_run(
        self,
        *,
        uow: Any,
        repository: AutomationRepository,
        project_id: ProjectId,
        workflow: Any,
        version_id: str,
        trigger_type: str,
        trigger_payload: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        now = self._clock()
        existing = repository.get_run_by_idempotency_key(idempotency_key)
        if existing is not None:
            return _run_data(existing, skipped=True)
        run_id = StableIdentifier.new()
        run = repository.create_run(
            run_id=run_id,
            project_id=project_id,
            workflow_id=workflow.automation_workflow_id,
            version_id=version_id,
            trigger_type=trigger_type,
            status=RunStatus.RUNNING.value,
            idempotency_key=idempotency_key,
            trigger_payload=trigger_payload,
            started_at=now,
        )
        uow.session.flush()
        repository.record_idempotency_key(
            claim_id=StableIdentifier.new(),
            project_id=project_id,
            idempotency_key=idempotency_key,
            automation_run_id=str(run_id),
            created_at=now,
        )
        uow.collect_event(automation_triggered(project_id, str(run_id), workflow.automation_workflow_id, trigger_type))
        return _run_data(run)

    def _continue_run(self, project_id: ProjectId, run_id: str, *, start_after_position: int) -> dict[str, Any]:
        with self._container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext

            repository = AutomationRepository(RepositoryContext(session=session, project_id=project_id))
            run = repository.get_run(project_id, run_id)
            if run is None:
                raise AutomationEngineError(ErrorCode.NOT_FOUND, f"Run not found: {run_id}")
            actions = repository.list_actions(run.automation_workflow_version_id)
            trigger_payload = run.trigger_payload_json or {}
        step_results: list[dict[str, Any]] = []
        for action in actions:
            if action.position <= start_after_position:
                continue
            step_id = StableIdentifier.new()
            step_key = f"{run.idempotency_key}:action:{action.automation_action_id}"
            config = action.config_json or {}
            if action_execution_tier(config) == ExecutionTier.APPROVAL_GATED.value:
                preview = self._executor.preview(
                    project_id=project_id,
                    action_type=action.action_type,
                    config=config,
                    trigger_payload=trigger_payload,
                )
                if preview.get("skipped"):
                    with self._container.create_unit_of_work(project_id) as uow:
                        uow.begin()
                        repository = uow.repository(AutomationRepository)
                        repository.create_run_step(
                            step_id=step_id,
                            run_id=run_id,
                            project_id=project_id,
                            action_id=action.automation_action_id,
                            position=action.position,
                            status=StepStatus.SKIPPED.value,
                            result_json=preview,
                        )
                        uow.commit()
                    step_results.append({"action_type": action.action_type, "status": StepStatus.SKIPPED.value})
                    continue
                approval_id = StableIdentifier.new()
                with self._container.create_unit_of_work(project_id) as uow:
                    uow.begin()
                    repository = uow.repository(AutomationRepository)
                    run_row = repository.get_run(project_id, run_id)
                    assert run_row is not None
                    repository.create_run_step(
                        step_id=step_id,
                        run_id=run_id,
                        project_id=project_id,
                        action_id=action.automation_action_id,
                        position=action.position,
                        status=StepStatus.PENDING_APPROVAL.value,
                        result_json={"preview": preview},
                    )
                    uow.session.flush()
                    repository.create_approval(
                        approval_id=approval_id,
                        run_id=run_id,
                        step_id=str(step_id),
                        action_id=action.automation_action_id,
                        project_id=project_id,
                        preview_json=preview,
                        requested_at=self._clock(),
                    )
                    run_row.status = RunStatus.WAITING_APPROVAL.value
                    uow.collect_event(
                        automation_approval_requested(project_id, run_id, str(approval_id), preview)
                    )
                    uow.commit()
                return {
                    "automation_run_id": run_id,
                    "status": RunStatus.WAITING_APPROVAL.value,
                    "approval_id": str(approval_id),
                    "steps": step_results,
                }
            try:
                result = self._executor.execute(
                    project_id=project_id,
                    action_type=action.action_type,
                    safety_class=action.safety_class,
                    config=config,
                    trigger_payload=trigger_payload,
                    idempotency_key=step_key,
                )
                status = StepStatus.SKIPPED.value if result.get("skipped") else StepStatus.SUCCEEDED.value
                with self._container.create_unit_of_work(project_id) as uow:
                    uow.begin()
                    repository = uow.repository(AutomationRepository)
                    repository.create_run_step(
                        step_id=step_id,
                        run_id=run_id,
                        project_id=project_id,
                        action_id=action.automation_action_id,
                        position=action.position,
                        status=status,
                        result_json=result,
                        undo_plan_json=result.get("undo_plan_json"),
                        command_execution_id=result.get("command_execution_id"),
                    )
                    uow.commit()
                step_results.append({"action_type": action.action_type, "status": status})
            except Exception as error:
                return self._halt_run(
                    project_id,
                    run_id,
                    failed_position=action.position,
                    message=str(error),
                    step_id=str(step_id),
                    step_error=str(error),
                    action_id=action.automation_action_id,
                    prior_steps=step_results,
                )
        finished_at = self._clock()
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(AutomationRepository)
            run_row = repository.get_run(project_id, run_id)
            assert run_row is not None
            repository.finish_run(run_row, status=RunStatus.SUCCEEDED.value, finished_at=finished_at, summary="Completed")
            uow.collect_event(automation_run_completed(project_id, run_id, run_row.automation_workflow_id))
            uow.commit()
        return {
            "automation_run_id": run_id,
            "status": RunStatus.SUCCEEDED.value,
            "steps": step_results,
        }

    def _halt_run(
        self,
        project_id: ProjectId,
        run_id: str,
        *,
        failed_position: int,
        message: str,
        step_id: str,
        step_error: str,
        action_id: str | None = None,
        prior_steps: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        finished_at = self._clock()
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(AutomationRepository)
            run_row = repository.get_run(project_id, run_id)
            assert run_row is not None
            if action_id is not None:
                repository.create_run_step(
                    step_id=StableIdentifier(step_id),
                    run_id=run_id,
                    project_id=project_id,
                    action_id=action_id,
                    position=failed_position,
                    status=StepStatus.FAILED.value,
                    result_json={"error": step_error},
                )
            self._mark_remaining_not_attempted(repository, run_id, project_id=project_id, after_position=failed_position)
            repository.finish_run(
                run_row,
                status=RunStatus.FAILED.value,
                finished_at=finished_at,
                summary=f"Halted at step {failed_position}: {message}",
            )
            uow.collect_event(recipe_run_halted(project_id, run_id, failed_step=failed_position, message=message))
            uow.collect_event(automation_run_failed(project_id, run_id, run_row.automation_workflow_id, message))
            uow.commit()
        steps = list(prior_steps or [])
        steps.append({"position": failed_position, "status": StepStatus.FAILED.value, "error": step_error})
        return {"automation_run_id": run_id, "status": RunStatus.FAILED.value, "steps": steps, "halted_at": failed_position}

    def _mark_remaining_not_attempted(
        self,
        repository: AutomationRepository,
        run_id: str,
        *,
        project_id: ProjectId,
        after_position: int,
    ) -> None:
        with self._container.session_factory() as session:
            from backend.adapters.persistence.models import AutomationRunRecord

            run_row = session.get(AutomationRunRecord, run_id)
            if run_row is None:
                return
            actions = repository.list_actions(run_row.automation_workflow_version_id)
        existing_positions = {step.position for step in repository.list_run_steps(run_id)}
        for action in actions:
            if action.position <= after_position or action.position in existing_positions:
                continue
            repository.create_run_step(
                step_id=StableIdentifier.new(),
                run_id=run_id,
                project_id=project_id,
                action_id=action.automation_action_id,
                position=action.position,
                status=StepStatus.NOT_ATTEMPTED.value,
                result_json={"reason": "halted_before_step"},
            )

    def _is_globally_enabled(self) -> bool:
        with self._container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext

            return AutomationRepository(RepositoryContext(session=session)).get_global_enabled()


class AutomationEngineError(RuntimeError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


def _resolve_trigger_type(envelope: DomainEventEnvelope) -> TriggerType | None:
    if envelope.event_type == "GitOperationCompleted":
        if envelope.payload.get("operation_type") != "pull" or envelope.payload.get("status") != "succeeded":
            return None
        return TriggerType.GIT_PULL_COMPLETED
    return _EVENT_TRIGGER_MAP.get(envelope.event_type)


def _event_idempotency_key(envelope: DomainEventEnvelope) -> str:
    payload = envelope.payload
    if envelope.event_type == "AlertFired" and payload.get("alert_event_id"):
        return f"event:AlertFired:{envelope.project_id}:{payload['alert_event_id']}"
    if envelope.event_type == "ServerCrashed":
        token = payload.get("occurrence_id") or payload.get("process_run_id") or envelope.aggregate_ref.aggregate_id
        return f"event:ServerCrashed:{envelope.project_id}:{token}"
    if envelope.event_type == "GitOperationCompleted" and payload.get("git_operation_id"):
        return f"event:GitPullCompleted:{envelope.project_id}:{payload['git_operation_id']}"
    return f"event:{envelope.event_type}:{envelope.project_id}:{envelope.aggregate_ref.aggregate_id}"


def _run_data(run: Any, *, skipped: bool = False) -> dict[str, Any]:
    return {
        "automation_run_id": run.automation_run_id,
        "automation_workflow_id": run.automation_workflow_id,
        "status": RunStatus.SKIPPED.value if skipped else run.status,
        "idempotency_key": run.idempotency_key,
        "trigger_type": run.trigger_type,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
    }
