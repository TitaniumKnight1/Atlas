from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable

from backend.adapters.persistence import AutomationRepository, ProjectRepository
from backend.application.automation.engine import AutomationEngine, AutomationEngineError
from backend.application.automation.scheduler import AutomationSchedulerService
from backend.domain.automation.types import ActionType, ConditionType, RunStatus, SafetyClass, TriggerType
from backend.domain.shared_kernel import ErrorCode, ProjectId, StableIdentifier
from backend.domain.shared_kernel.events import DomainEventEnvelope


class AutomationApplicationError(RuntimeError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


class AutomationApplicationService:
    def __init__(self, *, container: Any, clock: Callable[[], datetime] | None = None) -> None:
        self._container = container
        self._clock = clock or (lambda: datetime.now(UTC))
        self._engine = AutomationEngine(container=container, clock=self._clock)
        self._scheduler = AutomationSchedulerService(container=container, engine=self._engine, clock=self._clock)
        self._subscribers_registered = False

    @property
    def engine(self) -> AutomationEngine:
        return self._engine

    @property
    def scheduler(self) -> AutomationSchedulerService:
        return self._scheduler

    def register_event_subscribers(self) -> None:
        if self._subscribers_registered:
            return
        bus = self._container.event_bus
        bus.register("AlertFired", self._on_domain_event)
        bus.register("ServerCrashed", self._on_domain_event)
        bus.register("GitOperationCompleted", self._on_domain_event)
        self._subscribers_registered = True

    def start_scheduler(self) -> dict[str, Any]:
        return self._scheduler.start()

    def stop_scheduler(self) -> dict[str, Any]:
        return self._scheduler.stop()

    def _on_domain_event(self, envelope: DomainEventEnvelope) -> None:
        self._engine.handle_domain_event(envelope)

    def get_global_settings(self) -> dict[str, Any]:
        with self._container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext

            enabled = AutomationRepository(RepositoryContext(session=session)).get_global_enabled()
        return {"global_enabled": enabled}

    def set_global_enabled(self, *, enabled: bool) -> dict[str, Any]:
        now = self._clock()
        with self._container.create_unit_of_work() as uow:
            uow.begin()
            payload = uow.repository(AutomationRepository).set_global_enabled(enabled=enabled, updated_at=now)
            uow.commit()
        return {"global_enabled": payload["enabled"]}

    def create_workflow(
        self,
        project_id: ProjectId,
        *,
        name: str,
        description: str | None,
        trigger_type: str,
        trigger_config: dict[str, Any] | None,
        conditions: list[dict[str, Any]] | None,
        actions: list[dict[str, Any]],
        schedule_interval_seconds: int | None = None,
        is_enabled: bool = True,
    ) -> dict[str, Any]:
        now = self._clock()
        workflow_id = StableIdentifier.new()
        version_id = StableIdentifier.new()
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(AutomationRepository)
            self._require_project(uow.repository(ProjectRepository), project_id)
            repository.create_workflow(
                workflow_id=workflow_id,
                project_id=project_id,
                name=name,
                description=description,
                is_enabled=is_enabled,
                created_at=now,
            )
            repository.create_version(
                version_id=version_id,
                workflow_id=str(workflow_id),
                project_id=project_id,
                version_number=1,
                created_at=now,
            )
            uow.session.flush()
            repository.create_trigger(
                trigger_id=StableIdentifier.new(),
                version_id=str(version_id),
                project_id=project_id,
                trigger_type=trigger_type,
                config_json=trigger_config,
            )
            for index, condition in enumerate(conditions or [{"condition_type": ConditionType.ALWAYS.value}]):
                repository.create_condition(
                    condition_id=StableIdentifier.new(),
                    version_id=str(version_id),
                    project_id=project_id,
                    condition_type=condition["condition_type"],
                    config_json=condition.get("config_json"),
                    position=index,
                )
            for index, action in enumerate(actions):
                repository.create_action(
                    action_id=StableIdentifier.new(),
                    version_id=str(version_id),
                    project_id=project_id,
                    action_type=action["action_type"],
                    safety_class=action.get("safety_class", SafetyClass.READ_ONLY.value),
                    config_json=action.get("config_json"),
                    position=index,
                )
            uow.session.flush()
            workflow = repository.get_workflow(project_id, str(workflow_id))
            if workflow is None:
                raise AutomationApplicationError(ErrorCode.EXTERNAL_ADAPTER_FAILED, "Workflow creation failed")
            repository.set_workflow_current_version(workflow, str(version_id))
            schedule_data = None
            if trigger_type == TriggerType.SCHEDULE.value or schedule_interval_seconds is not None:
                interval = schedule_interval_seconds or int((trigger_config or {}).get("interval_seconds", 60))
                schedule_id = StableIdentifier.new()
                repository.create_schedule(
                    schedule_id=schedule_id,
                    workflow_id=str(workflow_id),
                    project_id=project_id,
                    schedule_json={"interval_seconds": interval},
                    next_run_at=now,
                    is_enabled=is_enabled,
                )
                schedule_data = {"automation_schedule_id": str(schedule_id), "interval_seconds": interval}
            uow.commit()
        return {
            "automation_workflow_id": str(workflow_id),
            "automation_workflow_version_id": str(version_id),
            "name": name,
            "trigger_type": trigger_type,
            "schedule": schedule_data,
            "is_enabled": is_enabled,
        }

    def list_workflows(self, project_id: ProjectId) -> list[dict[str, Any]]:
        with self._container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext

            records = AutomationRepository(RepositoryContext(session=session, project_id=project_id)).list_workflows(project_id)
        return [_workflow_data(record) for record in records]

    def set_workflow_enabled(self, project_id: ProjectId, workflow_id: str, *, is_enabled: bool) -> dict[str, Any]:
        now = self._clock()
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(AutomationRepository)
            workflow = repository.get_workflow(project_id, workflow_id)
            if workflow is None:
                raise AutomationApplicationError(ErrorCode.NOT_FOUND, f"Workflow not found: {workflow_id}")
            repository.set_workflow_enabled(workflow, is_enabled=is_enabled, updated_at=now)
            uow.commit()
        return _workflow_data(workflow)

    def list_runs(self, project_id: ProjectId, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext

            repository = AutomationRepository(RepositoryContext(session=session, project_id=project_id))
            runs = repository.list_runs(project_id, limit=limit)
            return [_run_summary(run, repository.list_run_steps(run.automation_run_id), repository.list_approvals_for_run(run.automation_run_id)) for run in runs]

    def get_run(self, project_id: ProjectId, run_id: str) -> dict[str, Any]:
        with self._container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext

            repository = AutomationRepository(RepositoryContext(session=session, project_id=project_id))
            run = repository.get_run(project_id, run_id)
            if run is None:
                raise AutomationApplicationError(ErrorCode.NOT_FOUND, f"Run not found: {run_id}")
            return _run_summary(run, repository.list_run_steps(run_id), repository.list_approvals_for_run(run_id))

    def run_now(self, project_id: ProjectId, workflow_id: str, *, idempotency_key: str | None = None) -> dict[str, Any]:
        try:
            return self._engine.run_manual(project_id, workflow_id, idempotency_key=idempotency_key)
        except AutomationEngineError as error:
            raise AutomationApplicationError(error.code, str(error)) from error

    def undo_run_step(self, project_id: ProjectId, step_id: str) -> dict[str, Any]:
        try:
            return self._engine.undo_run_step(project_id, step_id)
        except AutomationEngineError as error:
            raise AutomationApplicationError(error.code, str(error)) from error

    def list_recipes(self) -> list[dict[str, Any]]:
        from backend.application.automation.recipes import list_available_recipes

        return list_available_recipes()

    def instantiate_recipe(
        self,
        project_id: ProjectId,
        recipe_key: str,
        *,
        params: dict[str, Any] | None = None,
        is_enabled: bool = True,
    ) -> dict[str, Any]:
        from backend.application.automation.recipes import RecipeInstantiationError, instantiate_recipe

        try:
            return instantiate_recipe(self, project_id, recipe_key, params=params, is_enabled=is_enabled)
        except RecipeInstantiationError as error:
            raise AutomationApplicationError(error.code, str(error)) from error

    def list_recipe_instances(self, project_id: ProjectId) -> list[dict[str, Any]]:
        with self._container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext

            records = AutomationRepository(RepositoryContext(session=session, project_id=project_id)).list_recipe_instances(project_id)
        return [
            {
                "automation_recipe_instance_id": record.automation_recipe_instance_id,
                "recipe_key": record.recipe_key,
                "automation_workflow_id": record.automation_workflow_id,
                "instance_status": record.instance_status,
                "deferred_capabilities": record.deferred_capabilities_json or [],
                "params": record.params_json or {},
                "created_at": record.created_at,
            }
            for record in records
        ]

    def list_pending_approvals(self, project_id: ProjectId) -> list[dict[str, Any]]:
        with self._container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext

            approvals = AutomationRepository(RepositoryContext(session=session, project_id=project_id)).list_pending_approvals(project_id)
        return [_approval_data(approval) for approval in approvals]

    def approve_run(self, project_id: ProjectId, run_id: str, approval_id: str, *, decided_by: str | None = None) -> dict[str, Any]:
        try:
            return self._engine.approve_run(project_id, run_id, approval_id, decided_by=decided_by)
        except AutomationEngineError as error:
            raise AutomationApplicationError(error.code, str(error)) from error

    def reject_run(
        self,
        project_id: ProjectId,
        run_id: str,
        approval_id: str,
        *,
        reason: str | None = None,
        decided_by: str | None = None,
    ) -> dict[str, Any]:
        try:
            return self._engine.reject_run(project_id, run_id, approval_id, reason=reason, decided_by=decided_by)
        except AutomationEngineError as error:
            raise AutomationApplicationError(error.code, str(error)) from error

    def _require_project(self, repository: ProjectRepository, project_id: ProjectId) -> None:
        if repository.get_project(project_id) is None:
            raise AutomationApplicationError(ErrorCode.NOT_FOUND, f"Project not found: {project_id}")


def _workflow_data(record: Any) -> dict[str, Any]:
    return {
        "automation_workflow_id": record.automation_workflow_id,
        "project_id": record.project_id,
        "name": record.name,
        "description": record.description,
        "is_enabled": bool(record.is_enabled),
        "current_version_id": record.current_version_id,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _run_summary(run: Any, steps: list[Any], approvals: list[Any] | None = None) -> dict[str, Any]:
    return {
        "automation_run_id": run.automation_run_id,
        "automation_workflow_id": run.automation_workflow_id,
        "project_id": run.project_id,
        "trigger_type": run.trigger_type,
        "status": run.status,
        "idempotency_key": run.idempotency_key,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "summary": run.summary,
        "steps": [
            {
                "automation_run_step_id": step.automation_run_step_id,
                "automation_action_id": step.automation_action_id,
                "position": step.position,
                "status": step.status,
                "result_json": step.result_json,
                "has_undo": step.undo_plan_json is not None,
            }
            for step in steps
        ],
        "approvals": [_approval_data(approval) for approval in (approvals or [])],
    }


def _approval_data(approval: Any) -> dict[str, Any]:
    return {
        "automation_approval_id": approval.automation_approval_id,
        "automation_run_id": approval.automation_run_id,
        "automation_run_step_id": approval.automation_run_step_id,
        "approval_state": approval.approval_state,
        "preview_json": approval.preview_json,
        "requested_at": approval.requested_at,
        "decided_at": approval.decided_at,
        "decided_by": approval.decided_by,
        "approval_reason": approval.approval_reason,
    }
