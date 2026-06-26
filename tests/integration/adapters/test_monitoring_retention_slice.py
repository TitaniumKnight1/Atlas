from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import func, select

from backend.adapters.persistence import MonitoringRepository
from backend.adapters.persistence.models import MetricRollupRecord, MetricSampleRecord, TelemetryQueueRecord, TelemetryRejectionRecord
from backend.domain.monitoring.aggregation import MINUTE_BUCKET_SECONDS, aggregate_raw_values
from backend.domain.shared_kernel import ProjectId, StableIdentifier
from backend.infrastructure.di import create_application_container
from backend.infrastructure.unit_of_work import RepositoryContext


def test_faithful_minute_rollup_matches_raw_truth(tmp_path: Path) -> None:
    container, project_id, series_id = _project_with_series(tmp_path)
    retention = container.create_monitoring_retention_service()
    now = datetime(2026, 6, 1, 12, 5, tzinfo=UTC)
    bucket_start = datetime(2026, 6, 1, 12, 4, tzinfo=UTC)
    values = [10.0, 50.0, 30.0, 90.0, 20.0]
    try:
        _insert_raw_samples(container, project_id, series_id, bucket_start, values)
        with patch.object(retention, "_clock", return_value=now):
            result = retention.run_rollup_cycle(project_id)
        assert result["minute_buckets"] >= 1
        expected = aggregate_raw_values(values, bucket_start=bucket_start, bucket_size_seconds=MINUTE_BUCKET_SECONDS)
        assert expected is not None
        rollups = _minute_rollups(container, project_id, series_id)
        assert len(rollups) == 1
        rollup = rollups[0]
        assert rollup.min_value == expected.min_value
        assert rollup.max_value == expected.max_value
        assert rollup.avg_value == expected.avg_value
        assert rollup.sample_count == expected.sample_count
        assert rollup.max_value == 90.0
    finally:
        container.close()


def test_idempotent_rollup_rerun_does_not_double_count(tmp_path: Path) -> None:
    container, project_id, series_id = _project_with_series(tmp_path)
    retention = container.create_monitoring_retention_service()
    now = datetime(2026, 6, 1, 12, 5, tzinfo=UTC)
    bucket_start = datetime(2026, 6, 1, 12, 4, tzinfo=UTC)
    try:
        _insert_raw_samples(container, project_id, series_id, bucket_start, [1.0, 3.0, 5.0])
        with patch.object(retention, "_clock", return_value=now):
            retention.run_rollup_cycle(project_id)
            first = _minute_rollups(container, project_id, series_id)[0]
            retention.run_rollup_cycle(project_id)
            second = _minute_rollups(container, project_id, series_id)[0]
        assert first.rollup_id == second.rollup_id
        assert second.sample_count == 3
        assert second.avg_value == 3.0
    finally:
        container.close()


def test_resumable_catch_up_after_skipped_window(tmp_path: Path) -> None:
    container, project_id, series_id = _project_with_series(tmp_path)
    retention = container.create_monitoring_retention_service()
    first_bucket = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    second_bucket = datetime(2026, 6, 1, 12, 1, tzinfo=UTC)
    try:
        _insert_raw_samples(container, project_id, series_id, first_bucket, [2.0, 4.0])
        with patch.object(retention, "_clock", return_value=datetime(2026, 6, 1, 12, 1, 30, tzinfo=UTC)):
            retention.run_rollup_cycle(project_id)
        _insert_raw_samples(container, project_id, series_id, second_bucket, [100.0])
        with patch.object(retention, "_clock", return_value=datetime(2026, 6, 1, 12, 3, tzinfo=UTC)):
            retention.run_rollup_cycle(project_id)
        rollups = _minute_rollups(container, project_id, series_id)
        assert len(rollups) == 2
        by_start = {row.bucket_start: row for row in rollups}
        assert by_start[second_bucket.isoformat()].max_value == 100.0
    finally:
        container.close()


def test_retention_drops_raw_but_preserves_rollup_history(tmp_path: Path) -> None:
    container, project_id, series_id = _project_with_series(tmp_path)
    retention = container.create_monitoring_retention_service()
    bucket_start = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    try:
        _insert_raw_samples(container, project_id, series_id, bucket_start, [7.0, 13.0, 99.0])
        with patch.object(retention, "_clock", return_value=now):
            retention.run_rollup_cycle(project_id)
        assert _count(container, MetricSampleRecord) > 0
        assert len(_minute_rollups(container, project_id, series_id)) == 1
        with patch.object(retention, "_clock", return_value=now), patch("backend.application.monitoring.retention.RAW_RETENTION", timedelta(hours=1)):
            retention.run_rollup_cycle(project_id)
        assert _count(container, MetricSampleRecord) == 0
        rollups = _minute_rollups(container, project_id, series_id)
        assert len(rollups) == 1
        assert rollups[0].max_value == 99.0
    finally:
        container.close()


def test_time_window_query_returns_spike_preserving_aggregates(tmp_path: Path) -> None:
    container, project_id, series_id = _project_with_series(tmp_path)
    retention = container.create_monitoring_retention_service()
    bucket_start = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    now = datetime(2026, 6, 1, 13, 0, tzinfo=UTC)
    try:
        _insert_raw_samples(container, project_id, series_id, bucket_start, [1.0, 200.0, 3.0])
        with patch.object(retention, "_clock", return_value=now):
            retention.run_rollup_cycle(project_id)
        result = retention.query_time_window(
            project_id,
            start_at=bucket_start,
            end_at=now,
            metric_series_id=series_id,
            resolution="minute",
        )
        assert result["resolution"] == "minute"
        assert result["points"][0]["max_value"] == 200.0
        assert result["points"][0]["min_value"] == 1.0
    finally:
        container.close()


def test_project_isolation_on_history_query(tmp_path: Path) -> None:
    container, project_a, series_a = _project_with_series(tmp_path, "project-a")
    project_b = ProjectId(
        container.create_project_service().execute_import_project(root_path=_project_root(tmp_path, "project-b")).result["project_id"]
    )
    _, series_b = _ensure_series(container, project_b)
    retention = container.create_monitoring_retention_service()
    now = datetime(2026, 6, 1, 12, 5, tzinfo=UTC)
    try:
        _insert_raw_samples(container, project_a, series_a, datetime(2026, 6, 1, 12, 4, tzinfo=UTC), [5.0])
        _insert_raw_samples(container, project_b, series_b, datetime(2026, 6, 1, 12, 4, tzinfo=UTC), [50.0])
        with patch.object(retention, "_clock", return_value=now):
            retention.run_rollup_cycle()
        points_a = retention.query_time_window(
            project_a,
            start_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
            end_at=datetime(2026, 6, 1, 13, 0, tzinfo=UTC),
            metric_series_id=series_a,
            resolution="minute",
        )["points"]
        points_b = retention.query_time_window(
            project_b,
            start_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
            end_at=datetime(2026, 6, 1, 13, 0, tzinfo=UTC),
            metric_series_id=series_b,
            resolution="minute",
        )["points"]
        assert points_a[0]["max_value"] == 5.0
        assert points_b[0]["max_value"] == 50.0
    finally:
        container.close()


def test_rollup_uses_same_single_writer_lock_as_collection(tmp_path: Path) -> None:
    container, project_id, series_id = _project_with_series(tmp_path)
    monitoring = container.create_monitoring_service()
    retention = container.create_monitoring_retention_service()
    try:
        assert container.writer_lock is not None
        _insert_raw_samples(container, project_id, series_id, datetime(2026, 6, 1, 12, 4, tzinfo=UTC), [1.0, 2.0])
        monitoring.start_collection(project_id, interval_seconds=0.05)
        time.sleep(0.15)
        with patch.object(retention, "_clock", return_value=datetime(2026, 6, 1, 12, 10, tzinfo=UTC)):
            retention.run_rollup_cycle(project_id)
        monitoring.stop_collection(project_id)
        assert _count(container, MetricRollupRecord) >= 1
    finally:
        container.close()


def test_rollup_scheduler_starts_and_stops_cleanly(tmp_path: Path) -> None:
    container, project_id, _ = _project_with_series(tmp_path)
    retention = container.create_monitoring_retention_service()
    try:
        retention.start_rollup_scheduler(interval_seconds=0.05)
        assert retention.active_rollup_scheduler() is True
        retention.stop_rollup_scheduler()
        assert retention.active_rollup_scheduler() is False
        container.close()
        assert retention.active_rollup_scheduler() is False
    finally:
        container.close()


def test_retention_never_enters_telemetry(tmp_path: Path) -> None:
    container, project_id, series_id = _project_with_series(tmp_path)
    retention = container.create_monitoring_retention_service()
    try:
        _insert_raw_samples(container, project_id, series_id, datetime(2026, 6, 1, 12, 4, tzinfo=UTC), [4.0])
        with patch.object(retention, "_clock", return_value=datetime(2026, 6, 1, 12, 10, tzinfo=UTC)):
            retention.run_rollup_cycle(project_id)
        assert _count(container, TelemetryQueueRecord) == 0
        assert _count(container, TelemetryRejectionRecord) == 0
    finally:
        container.close()


def _project_with_series(tmp_path: Path, name: str = "retention-project"):
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


def _insert_raw_samples(container, project_id: ProjectId, series_id: str, bucket_start: datetime, values: list[float]) -> None:
    with container.create_unit_of_work(project_id) as uow:
        uow.begin()
        repository = uow.repository(MonitoringRepository)
        rows = []
        for index, value in enumerate(values):
            sampled_at = bucket_start + timedelta(seconds=index * 5)
            rows.append(
                {
                    "sample_id": str(StableIdentifier.new()),
                    "metric_series_id": series_id,
                    "sampled_at": sampled_at.isoformat(),
                    "value_real": value,
                    "value_text": None,
                    "quality": "ok",
                }
            )
        repository.add_samples(rows)
        uow.commit()


def _minute_rollups(container, project_id: ProjectId, series_id: str) -> list[MetricRollupRecord]:
    with container.session_factory() as session:
        return list(
            session.execute(
                select(MetricRollupRecord).where(
                    MetricRollupRecord.project_id == str(project_id),
                    MetricRollupRecord.metric_series_id == series_id,
                    MetricRollupRecord.bucket_size_seconds == MINUTE_BUCKET_SECONDS,
                )
            ).scalars()
        )


def _project_root(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    (root / "resources").mkdir(parents=True)
    return root


def _count(container, model) -> int:
    with container.session_factory() as session:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)
