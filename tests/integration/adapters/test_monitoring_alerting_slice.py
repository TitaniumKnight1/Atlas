from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import func, select

from backend.adapters.persistence import MonitoringRepository
from backend.adapters.persistence.models import MonitoringAlertEventRecord, TelemetryQueueRecord, TelemetryRejectionRecord
from backend.application.monitoring.alerts import MonitoringAlertService
from backend.domain.shared_kernel import ProjectId, StableIdentifier
from backend.infrastructure.di import create_application_container
from backend.infrastructure.streams import DeliveryPolicy, StreamTopic, TOPIC_DELIVERY_POLICIES
from backend.infrastructure.unit_of_work import RepositoryContext


def test_immediate_alert_fires_once_not_per_sample(tmp_path: Path) -> None:
    container, project_id, series_id = _project_with_series(tmp_path)
    alerts = container.create_monitoring_alert_service()
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    try:
        alert = alerts.create_alert(
            project_id,
            name="high-memory",
            severity="warning",
            metric_series_id=series_id,
            comparator=">",
            threshold=80.0,
            duration_seconds=0,
        )
        _insert_samples(container, project_id, series_id, now, [85.0, 90.0, 95.0])
        with patch.object(alerts, "_clock", return_value=now + timedelta(seconds=30)):
            first = alerts.evaluate_project(project_id)
            second = alerts.evaluate_project(project_id)
        assert first["fired"] == 1
        assert second["fired"] == 0
        assert _event_count(container) == 1
        updated = alerts.list_alerts(project_id)[0]
        assert updated["runtime_state"] == "firing"
    finally:
        container.close()


def test_firing_to_resolved_emits_one_resolve_event(tmp_path: Path) -> None:
    container, project_id, series_id = _project_with_series(tmp_path)
    alerts = container.create_monitoring_alert_service()
    t0 = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    try:
        alerts.create_alert(project_id, name="high-memory", severity="warning", metric_series_id=series_id, comparator=">", threshold=80.0)
        _insert_samples(container, project_id, series_id, t0, [90.0])
        with patch.object(alerts, "_clock", return_value=t0 + timedelta(seconds=10)):
            alerts.evaluate_project(project_id)
        _insert_samples(container, project_id, series_id, t0 + timedelta(seconds=20), [50.0])
        with patch.object(alerts, "_clock", return_value=t0 + timedelta(seconds=30)):
            result = alerts.evaluate_project(project_id)
        assert result["resolved"] == 1
        events = _list_events(container, project_id)
        assert len(events) == 2
        assert events[0]["status"] == "resolved"
        assert alerts.list_alerts(project_id)[0]["runtime_state"] == "ok"
    finally:
        container.close()


def test_sustained_rule_does_not_fire_on_single_spike(tmp_path: Path) -> None:
    container, project_id, series_id = _project_with_series(tmp_path)
    alerts = container.create_monitoring_alert_service()
    t0 = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    try:
        alerts.create_alert(
            project_id,
            name="sustained-high",
            severity="critical",
            metric_series_id=series_id,
            comparator=">",
            threshold=80.0,
            duration_seconds=60,
        )
        _insert_samples(container, project_id, series_id, t0, [90.0])
        with patch.object(alerts, "_clock", return_value=t0 + timedelta(seconds=10)):
            result = alerts.evaluate_project(project_id)
        assert result["fired"] == 0
        assert alerts.list_alerts(project_id)[0]["runtime_state"] == "pending"
    finally:
        container.close()


def test_sustained_rule_fires_after_persistent_breach(tmp_path: Path) -> None:
    container, project_id, series_id = _project_with_series(tmp_path)
    alerts = container.create_monitoring_alert_service()
    t0 = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    try:
        alerts.create_alert(
            project_id,
            name="sustained-high",
            severity="critical",
            metric_series_id=series_id,
            comparator=">",
            threshold=80.0,
            duration_seconds=60,
        )
        _insert_samples(
            container,
            project_id,
            series_id,
            t0,
            [85.0, 86.0, 87.0, 88.0, 89.0, 90.0, 91.0, 92.0, 93.0, 94.0, 95.0, 96.0, 97.0],
            step_seconds=5,
        )
        with patch.object(alerts, "_clock", return_value=t0 + timedelta(seconds=10)):
            alerts.evaluate_project(project_id)
        with patch.object(alerts, "_clock", return_value=t0 + timedelta(seconds=75)):
            result = alerts.evaluate_project(project_id)
        assert result["fired"] == 1
        assert _event_count(container) == 1
    finally:
        container.close()


def test_alert_events_stream_on_guaranteed_alerts_topic(tmp_path: Path) -> None:
    container, project_id, series_id = _project_with_series(tmp_path)
    alerts = container.create_monitoring_alert_service()
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    try:
        assert TOPIC_DELIVERY_POLICIES[StreamTopic.ALERTS] == DeliveryPolicy.GUARANTEED
        hub = container.stream_hub
        subscriber = hub.subscribe(str(project_id), {StreamTopic.ALERTS})
        alerts.create_alert(project_id, name="stream-alert", severity="warning", metric_series_id=series_id, comparator=">", threshold=10.0)
        _insert_samples(container, project_id, series_id, now, [20.0])
        with patch.object(alerts, "_clock", return_value=now + timedelta(seconds=5)):
            alerts.evaluate_project(project_id)
        event = subscriber.wait_next(timeout=2.0)
        assert event is not None
        assert event.topic == StreamTopic.ALERTS
        assert event.event_type == "AlertFired"
        hub.unsubscribe(subscriber)
    finally:
        container.close()


def test_m6c_performs_no_actions(tmp_path: Path) -> None:
    source = inspect.getsource(MonitoringAlertService)
    forbidden = ("execute_start_server", "execute_stop_server", "execute_restart_server", "automation", "notify", "webhook")
    assert not any(token in source for token in forbidden)


def test_alert_data_never_enters_telemetry(tmp_path: Path) -> None:
    container, project_id, series_id = _project_with_series(tmp_path)
    alerts = container.create_monitoring_alert_service()
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    try:
        alerts.create_alert(project_id, name="telemetry-check", severity="info", metric_series_id=series_id, comparator=">", threshold=1.0)
        _insert_samples(container, project_id, series_id, now, [5.0])
        with patch.object(alerts, "_clock", return_value=now + timedelta(seconds=1)):
            alerts.evaluate_project(project_id)
        assert _count(container, TelemetryQueueRecord) == 0
        assert _count(container, TelemetryRejectionRecord) == 0
    finally:
        container.close()


def test_project_isolation_for_alert_events(tmp_path: Path) -> None:
    container, project_a, series_a = _project_with_series(tmp_path, "project-a")
    project_b = ProjectId(
        container.create_project_service().execute_import_project(root_path=_project_root(tmp_path, "project-b")).result["project_id"]
    )
    _, series_b = _ensure_series(container, project_b)
    alerts = container.create_monitoring_alert_service()
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    try:
        alerts.create_alert(project_a, name="a-alert", severity="warning", metric_series_id=series_a, comparator=">", threshold=1.0)
        alerts.create_alert(project_b, name="b-alert", severity="warning", metric_series_id=series_b, comparator=">", threshold=1.0)
        _insert_samples(container, project_a, series_a, now, [10.0])
        _insert_samples(container, project_b, series_b, now, [20.0])
        with patch.object(alerts, "_clock", return_value=now + timedelta(seconds=1)):
            alerts.evaluate_all_projects()
        events_a = alerts.list_alert_events(project_a)
        events_b = alerts.list_alert_events(project_b)
        assert len(events_a) == 1
        assert len(events_b) == 1
        assert events_a[0]["details"]["observed_value"] == 10.0
        assert events_b[0]["details"]["observed_value"] == 20.0
    finally:
        container.close()


def test_alert_rule_crud(tmp_path: Path) -> None:
    container, project_id, series_id = _project_with_series(tmp_path)
    alerts = container.create_monitoring_alert_service()
    try:
        created = alerts.create_alert(project_id, name="crud", severity="info", metric_series_id=series_id, comparator=">=", threshold=5.0)
        updated = alerts.update_alert(project_id, created["monitoring_alert_id"], threshold=10.0, is_enabled=False)
        assert updated["condition"]["threshold"] == 10.0
        assert updated["is_enabled"] is False
        listed = alerts.list_alerts(project_id)
        assert len(listed) == 1
        deleted = alerts.delete_alert(project_id, created["monitoring_alert_id"])
        assert deleted["deleted"] is True
        assert alerts.list_alerts(project_id) == []
    finally:
        container.close()


def _project_with_series(tmp_path: Path, name: str = "alert-project"):
    container = create_application_container(tmp_path / "app-data")
    project_id = ProjectId(
        container.create_project_service().execute_import_project(root_path=_project_root(tmp_path, name)).result["project_id"]
    )
    _, series_id = _ensure_series(container, project_id)
    return container, project_id, series_id


def _ensure_series(container, project_id: ProjectId) -> tuple[ProjectId, str]:
    with container.create_unit_of_work(project_id) as uow:
        uow.begin()
        repository = uow.repository(MonitoringRepository)
        source = repository.upsert_source(
            metric_source_id=StableIdentifier.new(),
            project_id=project_id,
            source_type="system",
            source_ref="host",
            display_name="system:host",
            is_enabled=True,
        )
        uow.session.flush()
        series = repository.upsert_series(
            metric_series_id=StableIdentifier.new(),
            metric_source_id=source.metric_source_id,
            metric_name="memory_used_percent",
            unit="percent",
            value_type="gauge",
            retention_class="high",
            created_at=datetime.now(UTC),
        )
        uow.commit()
        return project_id, series.metric_series_id


def _insert_samples(
    container,
    project_id: ProjectId,
    series_id: str,
    start: datetime,
    values: list[float],
    *,
    step_seconds: int = 1,
) -> None:
    with container.create_unit_of_work(project_id) as uow:
        uow.begin()
        rows = [
            {
                "sample_id": str(StableIdentifier.new()),
                "metric_series_id": series_id,
                "sampled_at": (start + timedelta(seconds=index * step_seconds)).isoformat(),
                "value_real": value,
                "value_text": None,
                "quality": "ok",
            }
            for index, value in enumerate(values)
        ]
        uow.repository(MonitoringRepository).add_samples(rows)
        uow.commit()


def _event_count(container) -> int:
    return _count(container, MonitoringAlertEventRecord)


def _list_events(container, project_id: ProjectId) -> list[dict]:
    return container.create_monitoring_alert_service().list_alert_events(project_id, limit=10)


def _project_root(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    (root / "resources").mkdir(parents=True)
    return root


def _count(container, model) -> int:
    with container.session_factory() as session:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)
