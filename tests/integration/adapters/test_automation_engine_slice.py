from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from backend.adapters.persistence.models import AutomationRunRecord, TelemetryQueueRecord, TelemetryRejectionRecord
from backend.application.automation import AutomationApplicationService
from backend.domain.automation.types import ActionType, ConditionType, RunStatus, SafetyClass, TriggerType
from backend.domain.shared_kernel import AggregateRef, DomainEventEnvelope, ProjectId, StableIdentifier
from backend.infrastructure.di import create_application_container
from sqlalchemy import func, select


def test_alert_fired_triggers_audited_run_once(tmp_path: Path) -> None:
    container, project_id = _fixture(tmp_path)
    automation = container.create_automation_service()
    try:
        workflow = automation.create_workflow(
            project_id,
            name="alert-notify",
            description=None,
            trigger_type=TriggerType.ALERT_FIRED.value,
            trigger_config={},
            conditions=[{"condition_type": ConditionType.ALWAYS.value}],
            actions=[
                {
                    "action_type": ActionType.RECORD_LOCAL_NOTIFICATION.value,
                    "safety_class": SafetyClass.READ_ONLY.value,
                    "config_json": {"message": "Alert received"},
                }
            ],
        )
        event_id = str(StableIdentifier.new())
        _publish_alert_fired(container, project_id, event_id=event_id, severity="warning")
        _publish_alert_fired(container, project_id, event_id=event_id, severity="warning")
        runs = automation.list_runs(project_id)
        assert len(runs) == 1
        assert runs[0]["status"] == RunStatus.SUCCEEDED.value
        assert runs[0]["automation_workflow_id"] == workflow["automation_workflow_id"]
        assert len(runs[0]["steps"]) == 1
    finally:
        container.close()


def test_server_crashed_triggers_audited_run(tmp_path: Path) -> None:
    container, project_id = _fixture(tmp_path)
    automation = container.create_automation_service()
    try:
        automation.create_workflow(
            project_id,
            name="crash-notify",
            description=None,
            trigger_type=TriggerType.SERVER_CRASHED.value,
            trigger_config={},
            conditions=None,
            actions=[
                {
                    "action_type": ActionType.RECORD_LOCAL_NOTIFICATION.value,
                    "safety_class": SafetyClass.READ_ONLY.value,
                    "config_json": {"message": "Server crashed"},
                }
            ],
        )
        process_run_id = str(StableIdentifier.new())
        _publish_server_crashed(container, project_id, process_run_id=process_run_id)
        runs = automation.list_runs(project_id)
        assert len(runs) == 1
        assert runs[0]["trigger_type"] == TriggerType.SERVER_CRASHED.value
    finally:
        container.close()


def test_schedule_trigger_fires_with_fake_clock(tmp_path: Path) -> None:
    container, project_id = _fixture(tmp_path)
    t0 = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    automation = AutomationApplicationService(container=container, clock=lambda: t0)
    automation.register_event_subscribers()
    try:
        created = automation.create_workflow(
            project_id,
            name="heartbeat",
            description=None,
            trigger_type=TriggerType.SCHEDULE.value,
            trigger_config={"interval_seconds": 30},
            conditions=None,
            actions=[
                {
                    "action_type": ActionType.RECORD_LOCAL_NOTIFICATION.value,
                    "safety_class": SafetyClass.READ_ONLY.value,
                    "config_json": {"message": "heartbeat"},
                }
            ],
            schedule_interval_seconds=30,
        )
        schedule_id = created["schedule"]["automation_schedule_id"]
        results = automation.scheduler.run_due_schedules(before=t0)
        assert len(results) == 1
        assert results[0]["status"] == RunStatus.SUCCEEDED.value
        with container.session_factory() as session:
            from backend.adapters.persistence.models import AutomationScheduleRecord

            schedule = session.get(AutomationScheduleRecord, schedule_id)
            assert schedule is not None
            assert schedule.next_run_at > t0.isoformat()
    finally:
        automation.stop_scheduler()
        container.close()


def test_manual_run_idempotency_prevents_duplicate_execution(tmp_path: Path) -> None:
    container, project_id = _fixture(tmp_path)
    automation = container.create_automation_service()
    try:
        workflow = automation.create_workflow(
            project_id,
            name="manual-dup",
            description=None,
            trigger_type=TriggerType.MANUAL.value,
            trigger_config={},
            conditions=None,
            actions=[
                {
                    "action_type": ActionType.RECORD_LOCAL_NOTIFICATION.value,
                    "safety_class": SafetyClass.READ_ONLY.value,
                    "config_json": {"message": "once"},
                }
            ],
        )
        first = automation.run_now(project_id, workflow["automation_workflow_id"], idempotency_key="manual:dup-key")
        second = automation.run_now(project_id, workflow["automation_workflow_id"], idempotency_key="manual:dup-key")
        assert first["status"] == RunStatus.SUCCEEDED.value
        assert second["status"] == RunStatus.SKIPPED.value
        assert _run_count(container) == 1
    finally:
        container.close()


def test_schedule_idempotency_key_prevents_double_fire_for_same_due_slot(tmp_path: Path) -> None:
    container, project_id = _fixture(tmp_path)
    t0 = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    automation = AutomationApplicationService(container=container, clock=lambda: t0)
    automation.register_event_subscribers()
    try:
        created = automation.create_workflow(
            project_id,
            name="heartbeat-dup",
            description=None,
            trigger_type=TriggerType.SCHEDULE.value,
            trigger_config={"interval_seconds": 60},
            conditions=None,
            actions=[
                {
                    "action_type": ActionType.RECORD_LOCAL_NOTIFICATION.value,
                    "safety_class": SafetyClass.READ_ONLY.value,
                    "config_json": {"message": "tick"},
                }
            ],
            schedule_interval_seconds=60,
        )
        schedule_id = created["schedule"]["automation_schedule_id"]
        due_key = f"schedule:{schedule_id}:{t0.isoformat()}"
        automation.engine.run_manual(
            project_id,
            created["automation_workflow_id"],
            idempotency_key=due_key,
        )
        with container.session_factory() as session:
            from backend.adapters.persistence.models import AutomationScheduleRecord

            schedule = session.get(AutomationScheduleRecord, schedule_id)
            assert schedule is not None
            schedule.next_run_at = t0.isoformat()
            session.commit()
        second = automation.engine.trigger_schedule(schedule_id)
        assert second is not None
        assert second["status"] == RunStatus.SKIPPED.value
        assert _run_count(container) == 1
    finally:
        automation.stop_scheduler()
        container.close()


def test_global_kill_switch_blocks_event_and_schedule(tmp_path: Path) -> None:
    container, project_id = _fixture(tmp_path)
    t0 = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    automation = AutomationApplicationService(container=container, clock=lambda: t0)
    automation.register_event_subscribers()
    try:
        created = automation.create_workflow(
            project_id,
            name="blocked",
            description=None,
            trigger_type=TriggerType.SCHEDULE.value,
            trigger_config={"interval_seconds": 10},
            conditions=None,
            actions=[
                {
                    "action_type": ActionType.RECORD_LOCAL_NOTIFICATION.value,
                    "safety_class": SafetyClass.READ_ONLY.value,
                    "config_json": {"message": "should not run"},
                }
            ],
            schedule_interval_seconds=10,
        )
        automation.create_workflow(
            project_id,
            name="alert-blocked",
            description=None,
            trigger_type=TriggerType.ALERT_FIRED.value,
            trigger_config={},
            conditions=None,
            actions=[
                {
                    "action_type": ActionType.RECORD_LOCAL_NOTIFICATION.value,
                    "safety_class": SafetyClass.READ_ONLY.value,
                    "config_json": {"message": "nope"},
                }
            ],
        )
        automation.set_global_enabled(enabled=False)
        automation.scheduler.run_due_schedules(before=t0)
        _publish_alert_fired(container, project_id, event_id=str(StableIdentifier.new()), severity="critical")
        assert _run_count(container) == 0
        automation.set_global_enabled(enabled=True)
        automation.scheduler.run_due_schedules(before=t0)
        assert _run_count(container) == 1
        assert created["schedule"]["automation_schedule_id"]
    finally:
        automation.stop_scheduler()
        container.close()


def test_destructive_action_records_undo_and_reverses(tmp_path: Path) -> None:
    container, project_id = _fixture(tmp_path)
    root = tmp_path / "automation-project"
    marker_path = root / "server-data" / "automation-marker.cfg"
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text("original\n", encoding="utf-8")
    automation = container.create_automation_service()
    try:
        workflow = automation.create_workflow(
            project_id,
            name="append-marker",
            description=None,
            trigger_type=TriggerType.MANUAL.value,
            trigger_config={},
            conditions=None,
            actions=[
                {
                    "action_type": ActionType.APPEND_CONFIG_MARKER.value,
                    "safety_class": SafetyClass.DESTRUCTIVE.value,
                    "config_json": {"relative_path": "server-data/automation-marker.cfg", "marker_line": "# atlas-marker"},
                }
            ],
        )
        result = automation.run_now(project_id, workflow["automation_workflow_id"], idempotency_key="manual:test-undo")
        assert "# atlas-marker" in marker_path.read_text(encoding="utf-8")
        run = automation.get_run(project_id, result["automation_run_id"])
        step_id = run["steps"][0]["automation_run_step_id"]
        automation.undo_run_step(project_id, step_id)
        assert marker_path.read_text(encoding="utf-8") == "original\n"
    finally:
        container.close()


def test_conditions_gate_alert_actions(tmp_path: Path) -> None:
    container, project_id = _fixture(tmp_path)
    automation = container.create_automation_service()
    try:
        automation.create_workflow(
            project_id,
            name="severity-filter",
            description=None,
            trigger_type=TriggerType.ALERT_FIRED.value,
            trigger_config={},
            conditions=[{"condition_type": ConditionType.SEVERITY_EQUALS.value, "config_json": {"severity": "critical"}}],
            actions=[
                {
                    "action_type": ActionType.RECORD_LOCAL_NOTIFICATION.value,
                    "safety_class": SafetyClass.READ_ONLY.value,
                    "config_json": {"message": "critical only"},
                }
            ],
        )
        _publish_alert_fired(container, project_id, event_id=str(StableIdentifier.new()), severity="warning")
        assert _run_count(container) == 0
        _publish_alert_fired(container, project_id, event_id=str(StableIdentifier.new()), severity="critical")
        assert _run_count(container) == 1
    finally:
        container.close()


def test_scheduler_stops_cleanly_without_leaked_thread(tmp_path: Path) -> None:
    container, _project_id = _fixture(tmp_path)
    automation = container.create_automation_service()
    try:
        assert automation.scheduler.active() is True
        automation.stop_scheduler()
        assert automation.scheduler.active() is False
        assert automation.scheduler.stop()["status"] == "not_running"
    finally:
        container.close()


def test_project_isolation_for_automation_runs(tmp_path: Path) -> None:
    container, first_project_id = _fixture(tmp_path, name="alpha")
    second_project_id = ProjectId(
        container.create_project_service().execute_import_project(root_path=_project_root(tmp_path, "beta")).result["project_id"]
    )
    automation = container.create_automation_service()
    try:
        workflow = automation.create_workflow(
            first_project_id,
            name="alpha-only",
            description=None,
            trigger_type=TriggerType.MANUAL.value,
            trigger_config={},
            conditions=None,
            actions=[
                {
                    "action_type": ActionType.RECORD_LOCAL_NOTIFICATION.value,
                    "safety_class": SafetyClass.READ_ONLY.value,
                    "config_json": {"message": "alpha"},
                }
            ],
        )
        result = automation.run_now(first_project_id, workflow["automation_workflow_id"], idempotency_key="manual:alpha")
        try:
            automation.get_run(second_project_id, result["automation_run_id"])
        except Exception as error:  # noqa: BLE001
            assert "not found" in str(error).lower()
        else:
            raise AssertionError("cross-project run access was allowed")
    finally:
        container.close()


def test_automation_data_not_written_to_telemetry(tmp_path: Path) -> None:
    container, project_id = _fixture(tmp_path)
    automation = container.create_automation_service()
    try:
        workflow = automation.create_workflow(
            project_id,
            name="telemetry-check",
            description=None,
            trigger_type=TriggerType.MANUAL.value,
            trigger_config={},
            conditions=None,
            actions=[
                {
                    "action_type": ActionType.RECORD_LOCAL_NOTIFICATION.value,
                    "safety_class": SafetyClass.READ_ONLY.value,
                    "config_json": {"message": "local only secret-token-abc"},
                }
            ],
        )
        automation.run_now(project_id, workflow["automation_workflow_id"], idempotency_key="manual:telemetry")
        with container.session_factory() as session:
            assert int(session.scalar(select(func.count()).select_from(TelemetryQueueRecord)) or 0) == 0
            assert int(session.scalar(select(func.count()).select_from(TelemetryRejectionRecord)) or 0) == 0
    finally:
        container.close()


def _fixture(tmp_path: Path, name: str = "automation-project"):
    container = create_application_container(tmp_path / "app-data")
    root = _project_root(tmp_path, name)
    project_id = ProjectId(container.create_project_service().execute_import_project(root_path=root).result["project_id"])
    return container, project_id


def _project_root(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    (root / "resources").mkdir(parents=True)
    return root


def _publish_alert_fired(container, project_id: ProjectId, *, event_id: str, severity: str) -> None:
    container.event_bus.publish(
        [
            DomainEventEnvelope.create(
                event_type="AlertFired",
                aggregate_ref=AggregateRef("MonitoringAlert", event_id),
                project_id=project_id,
                payload={
                    "alert_event_id": event_id,
                    "monitoring_alert_id": str(StableIdentifier.new()),
                    "severity": severity,
                    "status": "triggered",
                },
            )
        ]
    )


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


def _run_count(container) -> int:
    with container.session_factory() as session:
        return int(session.scalar(select(func.count()).select_from(AutomationRunRecord)) or 0)
