from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Callable

from backend.adapters.persistence import AutomationRepository
from backend.application.automation.actions import AutomationActionExecutor
from backend.domain.automation import (
    RunStatus,
    TriggerType,
    automation_run_completed,
    automation_run_failed,
    automation_triggered,
    evaluate_conditions,
)
from backend.domain.shared_kernel import ErrorCode, ProjectId, StableIdentifier
from backend.domain.shared_kernel.events import DomainEventEnvelope


_EVENT_TRIGGER_MAP = {
    "AlertFired": TriggerType.ALERT_FIRED,
    "ServerCrashed": TriggerType.SERVER_CRASHED,
}


class AutomationEngine:
    """Trigger→action execution with idempotent runs and M0b single-writer writes."""

    def __init__(self, *, container: Any, clock: Callable[[], datetime] | None = None) -> None:
        self._container = container
        self._clock = clock or (lambda: datetime.now(UTC))
        self._executor = AutomationActionExecutor(container=container, filesystem=container.setup_filesystem)

    def handle_domain_event(self, envelope: DomainEventEnvelope) -> list[dict[str, Any]]:
        trigger_type = _EVENT_TRIGGER_MAP.get(envelope.event_type)
        if trigger_type is None or envelope.project_id is None:
            return []
        if not self._is_globally_enabled():
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
            result = self._execute_workflow(
                uow=uow,
                repository=repository,
                project_id=project_id,
                workflow=workflow,
                version_id=workflow.current_version_id,
                trigger_type=TriggerType.SCHEDULE.value,
                trigger_payload={"schedule_id": schedule.automation_schedule_id, "due_at": due_at},
                idempotency_key=idempotency_key,
            )
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
            result = self._execute_workflow(
                uow=uow,
                repository=repository,
                project_id=project_id,
                workflow=workflow,
                version_id=workflow.current_version_id,
                trigger_type=TriggerType.MANUAL.value,
                trigger_payload={"workflow_id": workflow_id},
                idempotency_key=key,
            )
            uow.commit()
        return result

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
            step.status = RunStatus.SUCCEEDED.value
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
            with self._container.create_unit_of_work(project_id) as uow:
                uow.begin()
                repository = uow.repository(AutomationRepository)
                workflow = repository.get_workflow(project_id, workflow_id)
                if workflow is None or not workflow.is_enabled or workflow.current_version_id is None:
                    uow.rollback()
                    continue
                conditions = [
                    {"condition_type": item.condition_type, "config_json": item.config_json or {}}
                    for item in repository.list_conditions(version_id)
                ]
                if not evaluate_conditions(conditions, trigger_payload):
                    uow.rollback()
                    results.append(
                        {
                            "workflow_id": workflow_id,
                            "status": RunStatus.SKIPPED.value,
                            "reason": "conditions_not_met",
                        }
                    )
                    continue
                workflow_key = f"{idempotency_key}:workflow:{workflow_id}"
                result = self._execute_workflow(
                    uow=uow,
                    repository=repository,
                    project_id=project_id,
                    workflow=workflow,
                    version_id=version_id,
                    trigger_type=trigger_type,
                    trigger_payload=trigger_payload,
                    idempotency_key=workflow_key,
                )
                uow.commit()
                results.append(result)
        return results

    def _execute_workflow(
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
        uow.collect_event(
            automation_triggered(project_id, str(run_id), workflow.automation_workflow_id, trigger_type)
        )
        actions = repository.list_actions(version_id)
        step_results: list[dict[str, Any]] = []
        failed = False
        for action in actions:
            step_id = StableIdentifier.new()
            step_key = f"{idempotency_key}:action:{action.automation_action_id}"
            try:
                result = self._executor.execute(
                    uow=uow,
                    project_id=project_id,
                    action_type=action.action_type,
                    safety_class=action.safety_class,
                    config=action.config_json or {},
                    trigger_payload=trigger_payload,
                    idempotency_key=step_key,
                )
                uow.session.flush()
                undo_json = result.get("undo_plan_json")
                repository.create_run_step(
                    step_id=step_id,
                    run_id=str(run_id),
                    project_id=project_id,
                    action_id=action.automation_action_id,
                    position=action.position,
                    status=RunStatus.SUCCEEDED.value,
                    result_json=result,
                    undo_plan_json=undo_json,
                    command_execution_id=result.get("command_execution_id"),
                )
                step_results.append({"action_type": action.action_type, "status": RunStatus.SUCCEEDED.value})
            except Exception as error:
                failed = True
                repository.create_run_step(
                    step_id=step_id,
                    run_id=str(run_id),
                    project_id=project_id,
                    action_id=action.automation_action_id,
                    position=action.position,
                    status=RunStatus.FAILED.value,
                    result_json={"error": str(error)},
                )
                step_results.append({"action_type": action.action_type, "status": RunStatus.FAILED.value, "error": str(error)})
                break

        finished_at = self._clock()
        if failed:
            repository.finish_run(run, status=RunStatus.FAILED.value, finished_at=finished_at, summary="One or more actions failed")
            uow.collect_event(automation_run_failed(project_id, str(run_id), workflow.automation_workflow_id, "action_failed"))
        else:
            repository.finish_run(run, status=RunStatus.SUCCEEDED.value, finished_at=finished_at, summary="Completed")
            uow.collect_event(automation_run_completed(project_id, str(run_id), workflow.automation_workflow_id))
        return {
            **_run_data(run),
            "steps": step_results,
        }

    def _is_globally_enabled(self) -> bool:
        with self._container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext

            return AutomationRepository(RepositoryContext(session=session)).get_global_enabled()


class AutomationEngineError(RuntimeError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


def _event_idempotency_key(envelope: DomainEventEnvelope) -> str:
    payload = envelope.payload
    if envelope.event_type == "AlertFired" and payload.get("alert_event_id"):
        return f"event:AlertFired:{envelope.project_id}:{payload['alert_event_id']}"
    if envelope.event_type == "ServerCrashed":
        token = payload.get("occurrence_id") or payload.get("process_run_id") or envelope.aggregate_ref.aggregate_id
        return f"event:ServerCrashed:{envelope.project_id}:{token}"
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
