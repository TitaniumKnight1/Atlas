from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

from backend.adapters.persistence import MonitoringRepository, ProjectRepository
from backend.domain.monitoring.aggregation import (
    HOUR_BUCKET_SECONDS,
    MINUTE_BUCKET_SECONDS,
    MetricAggregate,
    aggregate_raw_values,
    aggregate_to_payload,
    bucket_end,
    compose_aggregates,
    floor_to_bucket,
)
from backend.domain.shared_kernel import ErrorCode, ProjectId, StableIdentifier


# Retention horizons — raw short-term, coarser tiers longer (docs/database/overview.md intent).
RAW_RETENTION = timedelta(hours=24)
MINUTE_RETENTION = timedelta(days=7)
HOUR_RETENTION = timedelta(days=90)

ROLLUP_INTERVAL_SECONDS = 60.0


class MonitoringRetentionError(RuntimeError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


class MonitoringRetentionService:
    """M6b rollup, retention, and historical queries — single-writer-safe, no second writer."""

    def __init__(self, *, container: Any, clock: Callable[[], datetime] | None = None) -> None:
        self._container = container
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start_rollup_scheduler(self, *, interval_seconds: float = ROLLUP_INTERVAL_SECONDS) -> dict[str, Any]:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return {"status": "already_running", "interval_seconds": interval_seconds}
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._rollup_loop,
                args=(interval_seconds,),
                name="metric-rollup-retention",
                daemon=True,
            )
            self._thread.start()
        return {"status": "running", "interval_seconds": interval_seconds}

    def stop_rollup_scheduler(self) -> dict[str, Any]:
        with self._lock:
            if self._thread is None:
                return {"status": "not_running"}
            self._stop_event.set()
            thread = self._thread
        thread.join(timeout=5.0)
        with self._lock:
            self._thread = None
        return {"status": "stopped"}

    def active_rollup_scheduler(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def run_rollup_cycle(self, project_id: ProjectId | None = None) -> dict[str, Any]:
        project_ids = [project_id] if project_id is not None else self._list_project_ids()
        totals = {"minute_buckets": 0, "hour_buckets": 0, "raw_deleted": 0, "minute_deleted": 0, "hour_deleted": 0}
        for current_id in project_ids:
            result = self._rollup_project(current_id)
            for key in totals:
                totals[key] += result.get(key, 0)
        return totals

    def query_time_window(
        self,
        project_id: ProjectId,
        *,
        start_at: datetime,
        end_at: datetime,
        metric_series_id: str | None = None,
        resolution: str | None = None,
    ) -> dict[str, Any]:
        if end_at <= start_at:
            raise MonitoringRetentionError(ErrorCode.VALIDATION_FAILED, "end_at must be after start_at")
        now = self._clock()
        chosen = resolution or self._choose_resolution(start_at, end_at, now)
        with self._container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext

            repository = MonitoringRepository(RepositoryContext(session=session, project_id=project_id))
            series_ids = [metric_series_id] if metric_series_id else [item.metric_series_id for item in repository.list_series(project_id)]
            if chosen == "raw":
                points = repository.list_raw_samples_window(project_id, series_ids, start_at, end_at)
                return {"resolution": "raw", "points": points}
            bucket_size = MINUTE_BUCKET_SECONDS if chosen == "minute" else HOUR_BUCKET_SECONDS
            rollups = repository.list_rollups_window(project_id, series_ids, bucket_size, start_at, end_at)
            return {"resolution": chosen, "points": rollups}

    def list_series(self, project_id: ProjectId) -> list[dict[str, Any]]:
        with self._container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext

            records = MonitoringRepository(RepositoryContext(session=session, project_id=project_id)).list_series(project_id)
        return [
            {
                "metric_series_id": record.metric_series_id,
                "metric_source_id": record.metric_source_id,
                "metric_name": record.metric_name,
                "unit": record.unit,
                "value_type": record.value_type,
                "retention_class": record.retention_class,
            }
            for record in records
        ]

    def _rollup_loop(self, interval_seconds: float) -> None:
        while not self._stop_event.wait(interval_seconds):
            try:
                self.run_rollup_cycle()
            except Exception:
                continue

    def _rollup_project(self, project_id: ProjectId) -> dict[str, int]:
        now = self._clock()
        minute_cutoff = floor_to_bucket(now, MINUTE_BUCKET_SECONDS)
        hour_cutoff = floor_to_bucket(now, HOUR_BUCKET_SECONDS)
        minute_buckets = 0
        hour_buckets = 0
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(MonitoringRepository)
            watermark = repository.get_watermark(project_id, "minute")
            cursor = watermark or self._oldest_raw_bucket_start(repository, project_id)
            last_minute_end: datetime | None = watermark
            while cursor is not None and cursor < minute_cutoff:
                bucket_start = cursor
                series_ids = repository.list_numeric_series_ids(project_id)
                for series_id in series_ids:
                    values = repository.list_raw_values_in_bucket(series_id, bucket_start, MINUTE_BUCKET_SECONDS)
                    aggregate = aggregate_raw_values(values, bucket_start=bucket_start, bucket_size_seconds=MINUTE_BUCKET_SECONDS)
                    if aggregate is not None:
                        repository.upsert_rollup(
                            rollup_id=StableIdentifier.new(),
                            metric_series_id=series_id,
                            project_id=project_id,
                            aggregate=aggregate,
                            bucket_size_seconds=MINUTE_BUCKET_SECONDS,
                        )
                        minute_buckets += 1
                last_minute_end = bucket_end(bucket_start, MINUTE_BUCKET_SECONDS)
                cursor = last_minute_end
            if last_minute_end is not None and (watermark is None or last_minute_end > watermark):
                repository.set_watermark(project_id, "minute", last_minute_end)
            hour_watermark = repository.get_watermark(project_id, "hour")
            hour_cursor = hour_watermark or self._oldest_minute_bucket_start(repository, project_id)
            last_hour_end: datetime | None = hour_watermark
            while hour_cursor is not None and hour_cursor < hour_cutoff:
                bucket_start = hour_cursor
                series_ids = repository.list_numeric_series_ids(project_id)
                for series_id in series_ids:
                    lower = repository.list_rollup_aggregates_in_window(
                        series_id, bucket_start, HOUR_BUCKET_SECONDS, MINUTE_BUCKET_SECONDS
                    )
                    aggregate = compose_aggregates(lower, bucket_start=bucket_start, bucket_size_seconds=HOUR_BUCKET_SECONDS)
                    if aggregate is not None:
                        repository.upsert_rollup(
                            rollup_id=StableIdentifier.new(),
                            metric_series_id=series_id,
                            project_id=project_id,
                            aggregate=aggregate,
                            bucket_size_seconds=HOUR_BUCKET_SECONDS,
                        )
                        hour_buckets += 1
                last_hour_end = bucket_end(bucket_start, HOUR_BUCKET_SECONDS)
                hour_cursor = last_hour_end
            if last_hour_end is not None and (hour_watermark is None or last_hour_end > hour_watermark):
                repository.set_watermark(project_id, "hour", last_hour_end)
            raw_deleted = repository.delete_raw_samples_before_rollup(project_id, now - RAW_RETENTION)
            minute_deleted = repository.delete_minute_rollups_before(project_id, now - MINUTE_RETENTION)
            hour_deleted = repository.delete_hour_rollups_before(project_id, now - HOUR_RETENTION)
            uow.commit()
        return {
            "minute_buckets": minute_buckets,
            "hour_buckets": hour_buckets,
            "raw_deleted": raw_deleted,
            "minute_deleted": minute_deleted,
            "hour_deleted": hour_deleted,
        }

    def _choose_resolution(self, start_at: datetime, end_at: datetime, now: datetime) -> str:
        span = end_at - start_at
        if span <= timedelta(hours=6) and end_at >= now - RAW_RETENTION:
            return "raw"
        if span <= timedelta(days=7) or end_at >= now - MINUTE_RETENTION:
            return "minute"
        return "hour"

    def _list_project_ids(self) -> list[ProjectId]:
        with self._container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext

            repository = MonitoringRepository(RepositoryContext(session=session))
            return repository.list_projects_with_metric_data()

    def _oldest_raw_bucket_start(self, repository: MonitoringRepository, project_id: ProjectId) -> datetime | None:
        oldest = repository.oldest_raw_sample_at(project_id)
        if oldest is None:
            return None
        return floor_to_bucket(oldest, MINUTE_BUCKET_SECONDS)

    def _oldest_minute_bucket_start(self, repository: MonitoringRepository, project_id: ProjectId) -> datetime | None:
        oldest = repository.oldest_rollup_at(project_id, MINUTE_BUCKET_SECONDS)
        if oldest is None:
            return None
        return floor_to_bucket(oldest, HOUR_BUCKET_SECONDS)
