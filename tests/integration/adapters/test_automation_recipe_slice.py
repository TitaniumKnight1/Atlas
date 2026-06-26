from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import func, select

from backend.adapters.persistence.models import AutomationRunRecord, TelemetryQueueRecord, TelemetryRejectionRecord
from backend.domain.automation.types import ActionType, ExecutionTier, RecipeKey, RunStatus, SafetyClass, StepStatus, TriggerType
from backend.domain.shared_kernel import AggregateRef, DomainEventEnvelope, ProjectId, StableIdentifier
from backend.infrastructure.di import create_application_container


def test_restart_on_crash_creates_pending_approval_without_restart(tmp_path: Path) -> None:
    container, project_id = _fixture(tmp_path)
    automation = container.create_automation_service()
    params = _recipe_params(tmp_path)
    try:
        automation.instantiate_recipe(project_id, RecipeKey.RESTART_ON_CRASH.value, params=params)
        process_run_id = str(StableIdentifier.new())
        with patch.object(automation.engine._executor, "execute") as execute_mock:
            _publish_server_crashed(container, project_id, process_run_id=process_run_id)
            execute_mock.assert_not_called()
        runs = automation.list_runs(project_id)
        assert len(runs) == 1
        assert runs[0]["status"] == RunStatus.WAITING_APPROVAL.value
        assert len(runs[0]["approvals"]) == 1
        assert runs[0]["approvals"][0]["approval_state"] == "pending"
    finally:
        container.close()


def test_approve_restart_on_crash_executes_stubbed_restart(tmp_path: Path) -> None:
    container, project_id = _fixture(tmp_path)
    automation = container.create_automation_service()
    params = _recipe_params(tmp_path)
    try:
        automation.instantiate_recipe(project_id, RecipeKey.RESTART_ON_CRASH.value, params=params)
        process_run_id = str(StableIdentifier.new())
        _publish_server_crashed(container, project_id, process_run_id=process_run_id)
        run = automation.list_runs(project_id)[0]
        approval_id = run["approvals"][0]["automation_approval_id"]

        def fake_execute(**kwargs):
            return {"restarted": True, "process_run_id": "new-run"}

        with patch.object(automation.engine._executor, "execute", side_effect=fake_execute) as execute_mock:
            result = automation.approve_run(project_id, run["automation_run_id"], approval_id)
            execute_mock.assert_called_once()
            assert execute_mock.call_args.kwargs["action_type"] == ActionType.RESTART_SERVER.value
        assert result["status"] == RunStatus.SUCCEEDED.value
        updated = automation.get_run(project_id, run["automation_run_id"])
        assert updated["approvals"][0]["approval_state"] == "approved"
    finally:
        container.close()


def test_reject_restart_on_crash_executes_nothing(tmp_path: Path) -> None:
    container, project_id = _fixture(tmp_path)
    automation = container.create_automation_service()
    params = _recipe_params(tmp_path)
    try:
        automation.instantiate_recipe(project_id, RecipeKey.RESTART_ON_CRASH.value, params=params)
        _publish_server_crashed(container, project_id, process_run_id=str(StableIdentifier.new()))
        run = automation.list_runs(project_id)[0]
        approval_id = run["approvals"][0]["automation_approval_id"]
        with patch.object(automation.engine._executor, "execute") as execute_mock:
            automation.reject_run(project_id, run["automation_run_id"], approval_id, reason="not now")
            execute_mock.assert_not_called()
        updated = automation.get_run(project_id, run["automation_run_id"])
        assert updated["status"] == RunStatus.CANCELLED.value
    finally:
        container.close()


def test_post_git_pull_validation_auto_executes_without_restart(tmp_path: Path) -> None:
    container, project_id = _fixture(tmp_path)
    automation = container.create_automation_service()
    params = {**_recipe_params(tmp_path), "git_repository_id": str(StableIdentifier.new())}
    try:
        automation.instantiate_recipe(project_id, RecipeKey.POST_GIT_PULL_VALIDATION.value, params=params)
        op_id = str(StableIdentifier.new())
        executed: list[str] = []

        def fake_execute(**kwargs):
            executed.append(kwargs["action_type"])
            if kwargs["action_type"] == ActionType.RUN_CONFIG_VALIDATION.value:
                return {"validation": {"status": "pass"}}
            if kwargs["action_type"] == ActionType.RESCAN_RESOURCES.value:
                return {"rescan": {"added": 0}}
            return {"restarted": True}

        with patch.object(automation.engine._executor, "execute", side_effect=fake_execute):
            _publish_git_pull(container, project_id, git_repository_id=params["git_repository_id"], operation_id=op_id)
        assert ActionType.RUN_CONFIG_VALIDATION.value in executed
        assert ActionType.RESCAN_RESOURCES.value in executed
        assert ActionType.RESTART_SERVER.value not in executed
        run = automation.get_run(project_id, automation.list_runs(project_id)[0]["automation_run_id"])
        assert run["status"] == RunStatus.SUCCEEDED.value
    finally:
        container.close()


def test_multi_step_stop_and_hold_on_failure(tmp_path: Path) -> None:
    container, project_id = _fixture(tmp_path)
    automation = container.create_automation_service()
    try:
        automation.create_workflow(
            project_id,
            name="halt-demo",
            description=None,
            trigger_type=TriggerType.MANUAL.value,
            trigger_config={},
            conditions=None,
            actions=[
                {
                    "action_type": ActionType.RECORD_LOCAL_NOTIFICATION.value,
                    "safety_class": SafetyClass.READ_ONLY.value,
                    "config_json": {"execution_tier": ExecutionTier.AUTO.value, "message": "one"},
                },
                {
                    "action_type": ActionType.RUN_CONFIG_VALIDATION.value,
                    "safety_class": SafetyClass.READ_ONLY.value,
                    "config_json": {"execution_tier": ExecutionTier.AUTO.value},
                },
                {
                    "action_type": ActionType.RECORD_LOCAL_NOTIFICATION.value,
                    "safety_class": SafetyClass.READ_ONLY.value,
                    "config_json": {"execution_tier": ExecutionTier.AUTO.value, "message": "three"},
                },
            ],
        )
        workflow_id = automation.list_workflows(project_id)[0]["automation_workflow_id"]
        calls = {"count": 0}

        def flaky_execute(**kwargs):
            calls["count"] += 1
            if kwargs["action_type"] == ActionType.RUN_CONFIG_VALIDATION.value:
                raise RuntimeError("validation exploded")
            return {"notification": "ok"}

        with patch.object(automation.engine._executor, "execute", side_effect=flaky_execute):
            result = automation.run_now(project_id, workflow_id, idempotency_key="manual:halt")
        assert result["status"] == RunStatus.FAILED.value
        run = automation.get_run(project_id, result["automation_run_id"])
        statuses = {step["position"]: step["status"] for step in run["steps"]}
        assert statuses[0] == StepStatus.SUCCEEDED.value
        assert statuses[1] == StepStatus.FAILED.value
        assert statuses[2] == StepStatus.NOT_ATTEMPTED.value
    finally:
        container.close()


def test_redelivered_server_crashed_creates_one_pending_run(tmp_path: Path) -> None:
    container, project_id = _fixture(tmp_path)
    automation = container.create_automation_service()
    params = _recipe_params(tmp_path)
    try:
        automation.instantiate_recipe(project_id, RecipeKey.RESTART_ON_CRASH.value, params=params)
        process_run_id = str(StableIdentifier.new())
        _publish_server_crashed(container, project_id, process_run_id=process_run_id)
        _publish_server_crashed(container, project_id, process_run_id=process_run_id)
        assert _run_count(container) == 1
    finally:
        container.close()


def test_kill_switch_blocks_approve(tmp_path: Path) -> None:
    container, project_id = _fixture(tmp_path)
    automation = container.create_automation_service()
    params = _recipe_params(tmp_path)
    try:
        automation.instantiate_recipe(project_id, RecipeKey.RESTART_ON_CRASH.value, params=params)
        _publish_server_crashed(container, project_id, process_run_id=str(StableIdentifier.new()))
        run = automation.list_runs(project_id)[0]
        approval_id = run["approvals"][0]["automation_approval_id"]
        automation.set_global_enabled(enabled=False)
        try:
            automation.approve_run(project_id, run["automation_run_id"], approval_id)
        except Exception as error:  # noqa: BLE001
            assert "disabled" in str(error).lower()
        else:
            raise AssertionError("approve should fail when globally disabled")
    finally:
        container.close()


def test_nightly_maintenance_includes_backup_step(tmp_path: Path) -> None:
    container, project_id = _fixture(tmp_path)
    automation = container.create_automation_service()
    try:
        recipes = automation.list_recipes()
        nightly = next(item for item in recipes if item["recipe_key"] == RecipeKey.NIGHTLY_MAINTENANCE.value)
        assert nightly["deferred_capabilities"] == []
        instance = automation.instantiate_recipe(project_id, RecipeKey.NIGHTLY_MAINTENANCE.value, params=_recipe_params(tmp_path))
        assert instance["deferred_capabilities"] == []
        assert instance["resolved_action_count"] == 3
    finally:
        container.close()


def test_recipe_data_not_sent_to_telemetry(tmp_path: Path) -> None:
    container, project_id = _fixture(tmp_path)
    automation = container.create_automation_service()
    try:
        automation.instantiate_recipe(project_id, RecipeKey.RESTART_ON_CRASH.value, params=_recipe_params(tmp_path))
        _publish_server_crashed(container, project_id, process_run_id=str(StableIdentifier.new()))
        with container.session_factory() as session:
            assert int(session.scalar(select(func.count()).select_from(TelemetryQueueRecord)) or 0) == 0
            assert int(session.scalar(select(func.count()).select_from(TelemetryRejectionRecord)) or 0) == 0
    finally:
        container.close()


def _fixture(tmp_path: Path, name: str = "recipe-project"):
    container = create_application_container(tmp_path / "app-data")
    root = _project_root(tmp_path, name)
    project_id = ProjectId(container.create_project_service().execute_import_project(root_path=root).result["project_id"])
    return container, project_id


def _project_root(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    (root / "resources").mkdir(parents=True)
    (root / "server-data").mkdir(parents=True)
    return root


def _recipe_params(tmp_path: Path) -> dict[str, str]:
    root = tmp_path / "recipe-project"
    return {
        "fxserver_path": str(root / "FXServer.exe"),
        "server_data_path": str(root / "server-data"),
    }


def _publish_server_crashed(container, project_id: ProjectId, *, process_run_id: str) -> None:
    container.event_bus.publish(
        [
            DomainEventEnvelope.create(
                event_type="ServerCrashed",
                aggregate_ref=AggregateRef("ServerProcess", process_run_id),
                project_id=project_id,
                payload={"project_id": str(project_id), "process_run_id": process_run_id, "exit_code": 1},
            )
        ]
    )


def _publish_git_pull(container, project_id: ProjectId, *, git_repository_id: str, operation_id: str) -> None:
    container.event_bus.publish(
        [
            DomainEventEnvelope.create(
                event_type="GitOperationCompleted",
                aggregate_ref=AggregateRef("GitOperation", operation_id),
                project_id=project_id,
                payload={
                    "project_id": str(project_id),
                    "git_repository_id": git_repository_id,
                    "operation_type": "pull",
                    "status": "succeeded",
                    "git_operation_id": operation_id,
                },
            )
        ]
    )


def _run_count(container) -> int:
    with container.session_factory() as session:
        return int(session.scalar(select(func.count()).select_from(AutomationRunRecord)) or 0)
