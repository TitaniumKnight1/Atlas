from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select

from backend.adapters.persistence.models import (
    MetricRollupRecord,
    MetricRollupWatermarkRecord,
    MetricSampleRecord,
    MetricSeriesRecord,
    MetricSourceRecord,
    MonitoringAlertEventRecord,
    MonitoringAlertRecord,
)
from backend.domain.monitoring.aggregation import HOUR_BUCKET_SECONDS, MINUTE_BUCKET_SECONDS, MetricAggregate, bucket_end
from backend.domain.shared_kernel import ProjectId, StableIdentifier
from backend.infrastructure.unit_of_work import ProjectScopeRequired, RepositoryContext


class MonitoringRepository:
    def __init__(self, context: RepositoryContext) -> None:
        self._session = context.session
        self._project_id = context.project_id

    def upsert_source(
        self,
        *,
        metric_source_id: StableIdentifier,
        project_id: ProjectId,
        source_type: str,
        source_ref: str | None,
        display_name: str,
        is_enabled: bool,
        metadata: dict[str, Any] | None = None,
        environment_id: str | None = None,
    ) -> MetricSourceRecord:
        self._ensure_project_scope(project_id)
        existing = self._session.execute(
            select(MetricSourceRecord).where(
                MetricSourceRecord.project_id == str(project_id),
                MetricSourceRecord.source_type == source_type,
                MetricSourceRecord.source_ref == source_ref,
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.display_name = display_name
            existing.is_enabled = 1 if is_enabled else 0
            existing.metadata_json = metadata or {}
            return existing
        record = MetricSourceRecord(
            metric_source_id=str(metric_source_id),
            project_id=str(project_id),
            environment_id=environment_id,
            source_type=source_type,
            source_ref=source_ref,
            display_name=display_name,
            is_enabled=1 if is_enabled else 0,
            metadata_json=metadata or {},
        )
        self._session.add(record)
        return record

    def list_sources(self, project_id: ProjectId) -> list[MetricSourceRecord]:
        self._ensure_project_scope(project_id)
        return list(
            self._session.execute(
                select(MetricSourceRecord)
                .where(MetricSourceRecord.project_id == str(project_id))
                .order_by(MetricSourceRecord.display_name)
            ).scalars()
        )

    def list_series(self, project_id: ProjectId) -> list[MetricSeriesRecord]:
        self._ensure_project_scope(project_id)
        return list(
            self._session.execute(
                select(MetricSeriesRecord)
                .join(MetricSourceRecord, MetricSourceRecord.metric_source_id == MetricSeriesRecord.metric_source_id)
                .where(MetricSourceRecord.project_id == str(project_id))
                .order_by(MetricSeriesRecord.metric_name)
            ).scalars()
        )

    def upsert_series(
        self,
        *,
        metric_series_id: StableIdentifier,
        metric_source_id: str,
        metric_name: str,
        unit: str,
        value_type: str,
        retention_class: str,
        created_at: datetime,
    ) -> MetricSeriesRecord:
        existing = self._session.execute(
            select(MetricSeriesRecord).where(
                MetricSeriesRecord.metric_source_id == metric_source_id,
                MetricSeriesRecord.metric_name == metric_name,
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.unit = unit
            existing.value_type = value_type
            existing.retention_class = retention_class
            return existing
        record = MetricSeriesRecord(
            metric_series_id=str(metric_series_id),
            metric_source_id=metric_source_id,
            metric_name=metric_name,
            unit=unit,
            value_type=value_type,
            retention_class=retention_class,
            created_at=created_at.isoformat(),
        )
        self._session.add(record)
        return record

    def add_samples(self, samples: list[dict[str, Any]]) -> int:
        for item in samples:
            self._session.add(
                MetricSampleRecord(
                    sample_id=item["sample_id"],
                    metric_series_id=item["metric_series_id"],
                    sampled_at=item["sampled_at"],
                    value_real=item.get("value_real"),
                    value_text=item.get("value_text"),
                    quality=item["quality"],
                )
            )
        return len(samples)

    def list_recent_samples(self, project_id: ProjectId, *, limit: int = 100) -> list[dict[str, Any]]:
        self._ensure_project_scope(project_id)
        rows = self._session.execute(
            select(MetricSampleRecord, MetricSeriesRecord, MetricSourceRecord)
            .join(MetricSeriesRecord, MetricSeriesRecord.metric_series_id == MetricSampleRecord.metric_series_id)
            .join(MetricSourceRecord, MetricSourceRecord.metric_source_id == MetricSeriesRecord.metric_source_id)
            .where(MetricSourceRecord.project_id == str(project_id))
            .order_by(MetricSampleRecord.sampled_at.desc())
            .limit(limit)
        ).all()
        return [
            {
                "sample_id": sample.sample_id,
                "metric_series_id": sample.metric_series_id,
                "metric_name": series.metric_name,
                "source_type": source.source_type,
                "source_ref": source.source_ref,
                "unit": series.unit,
                "value_real": sample.value_real,
                "value_text": sample.value_text,
                "quality": sample.quality,
                "sampled_at": sample.sampled_at,
            }
            for sample, series, source in rows
        ]

    def latest_samples(self, project_id: ProjectId) -> list[dict[str, Any]]:
        return self.list_recent_samples(project_id, limit=500)

    def latest_samples_per_series(self, project_id: ProjectId) -> list[dict[str, Any]]:
        self._ensure_project_scope(project_id)
        rows = self._session.execute(
            select(MetricSampleRecord, MetricSeriesRecord, MetricSourceRecord)
            .join(MetricSeriesRecord, MetricSeriesRecord.metric_series_id == MetricSampleRecord.metric_series_id)
            .join(MetricSourceRecord, MetricSourceRecord.metric_source_id == MetricSeriesRecord.metric_source_id)
            .where(MetricSourceRecord.project_id == str(project_id))
            .order_by(MetricSampleRecord.sampled_at.desc())
        ).all()
        latest: dict[str, dict[str, Any]] = {}
        for sample, series, source in rows:
            if sample.metric_series_id in latest:
                continue
            latest[sample.metric_series_id] = {
                "sample_id": sample.sample_id,
                "metric_series_id": sample.metric_series_id,
                "metric_name": series.metric_name,
                "source_type": source.source_type,
                "source_ref": source.source_ref,
                "unit": series.unit,
                "value_real": sample.value_real,
                "value_text": sample.value_text,
                "quality": sample.quality,
                "sampled_at": sample.sampled_at,
            }
        return list(latest.values())

    def list_numeric_series_ids(self, project_id: ProjectId) -> list[str]:
        self._ensure_project_scope(project_id)
        rows = self._session.execute(
            select(MetricSeriesRecord.metric_series_id)
            .join(MetricSourceRecord, MetricSourceRecord.metric_source_id == MetricSeriesRecord.metric_source_id)
            .where(
                MetricSourceRecord.project_id == str(project_id),
                MetricSeriesRecord.value_type.in_(("gauge", "counter")),
            )
        ).scalars()
        return list(rows)

    def list_raw_values_in_bucket(self, metric_series_id: str, bucket_start: datetime, bucket_size_seconds: int) -> list[float]:
        start_iso = bucket_start.isoformat()
        end_iso = bucket_end(bucket_start, bucket_size_seconds).isoformat()
        rows = self._session.execute(
            select(MetricSampleRecord.value_real).where(
                MetricSampleRecord.metric_series_id == metric_series_id,
                MetricSampleRecord.sampled_at >= start_iso,
                MetricSampleRecord.sampled_at < end_iso,
                MetricSampleRecord.quality.in_(("ok", "estimated")),
                MetricSampleRecord.value_real.is_not(None),
            )
        ).scalars()
        return [float(value) for value in rows if value is not None]

    def upsert_rollup(
        self,
        *,
        rollup_id: StableIdentifier,
        metric_series_id: str,
        project_id: ProjectId,
        aggregate: MetricAggregate,
        bucket_size_seconds: int,
    ) -> MetricRollupRecord:
        self._ensure_project_scope(project_id)
        existing = self._session.execute(
            select(MetricRollupRecord).where(
                MetricRollupRecord.metric_series_id == metric_series_id,
                MetricRollupRecord.bucket_start == aggregate.bucket_start.isoformat(),
                MetricRollupRecord.bucket_size_seconds == bucket_size_seconds,
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.min_value = aggregate.min_value
            existing.max_value = aggregate.max_value
            existing.sum_value = aggregate.sum_value
            existing.avg_value = aggregate.avg_value
            existing.sample_count = aggregate.sample_count
            existing.project_id = str(project_id)
            return existing
        record = MetricRollupRecord(
            rollup_id=str(rollup_id),
            project_id=str(project_id),
            metric_series_id=metric_series_id,
            bucket_start=aggregate.bucket_start.isoformat(),
            bucket_size_seconds=bucket_size_seconds,
            min_value=aggregate.min_value,
            max_value=aggregate.max_value,
            sum_value=aggregate.sum_value,
            avg_value=aggregate.avg_value,
            sample_count=aggregate.sample_count,
        )
        self._session.add(record)
        return record

    def list_rollup_aggregates_in_window(
        self,
        metric_series_id: str,
        window_start: datetime,
        window_size_seconds: int,
        source_bucket_size_seconds: int,
    ) -> list[MetricAggregate]:
        start_iso = window_start.isoformat()
        end_iso = bucket_end(window_start, window_size_seconds).isoformat()
        rows = self._session.execute(
            select(MetricRollupRecord).where(
                MetricRollupRecord.metric_series_id == metric_series_id,
                MetricRollupRecord.bucket_size_seconds == source_bucket_size_seconds,
                MetricRollupRecord.bucket_start >= start_iso,
                MetricRollupRecord.bucket_start < end_iso,
            )
        ).scalars()
        aggregates: list[MetricAggregate] = []
        for row in rows:
            start = datetime.fromisoformat(row.bucket_start)
            aggregates.append(
                MetricAggregate(
                    min_value=row.min_value,
                    max_value=row.max_value,
                    sum_value=row.sum_value or 0.0,
                    sample_count=row.sample_count,
                    bucket_start=start,
                    bucket_end=bucket_end(start, row.bucket_size_seconds),
                )
            )
        return aggregates

    def list_rollups_window(
        self,
        project_id: ProjectId,
        series_ids: list[str],
        bucket_size_seconds: int,
        start_at: datetime,
        end_at: datetime,
    ) -> list[dict[str, Any]]:
        self._ensure_project_scope(project_id)
        if not series_ids:
            return []
        rows = self._session.execute(
            select(MetricRollupRecord, MetricSeriesRecord)
            .join(MetricSeriesRecord, MetricSeriesRecord.metric_series_id == MetricRollupRecord.metric_series_id)
            .where(
                MetricRollupRecord.project_id == str(project_id),
                MetricRollupRecord.metric_series_id.in_(series_ids),
                MetricRollupRecord.bucket_size_seconds == bucket_size_seconds,
                MetricRollupRecord.bucket_start >= start_at.isoformat(),
                MetricRollupRecord.bucket_start < end_at.isoformat(),
            )
            .order_by(MetricRollupRecord.bucket_start)
        ).all()
        return [
            {
                "rollup_id": rollup.rollup_id,
                "metric_series_id": rollup.metric_series_id,
                "metric_name": series.metric_name,
                "bucket_start": rollup.bucket_start,
                "bucket_end": bucket_end(datetime.fromisoformat(rollup.bucket_start), rollup.bucket_size_seconds).isoformat(),
                "bucket_size_seconds": rollup.bucket_size_seconds,
                "min_value": rollup.min_value,
                "max_value": rollup.max_value,
                "avg_value": rollup.avg_value,
                "sum_value": rollup.sum_value,
                "sample_count": rollup.sample_count,
            }
            for rollup, series in rows
        ]

    def list_raw_samples_window(
        self,
        project_id: ProjectId,
        series_ids: list[str],
        start_at: datetime,
        end_at: datetime,
    ) -> list[dict[str, Any]]:
        self._ensure_project_scope(project_id)
        if not series_ids:
            return []
        rows = self._session.execute(
            select(MetricSampleRecord, MetricSeriesRecord)
            .join(MetricSeriesRecord, MetricSeriesRecord.metric_series_id == MetricSampleRecord.metric_series_id)
            .where(
                MetricSampleRecord.metric_series_id.in_(series_ids),
                MetricSampleRecord.sampled_at >= start_at.isoformat(),
                MetricSampleRecord.sampled_at < end_at.isoformat(),
            )
            .order_by(MetricSampleRecord.sampled_at)
        ).all()
        return [
            {
                "sample_id": sample.sample_id,
                "metric_series_id": sample.metric_series_id,
                "metric_name": series.metric_name,
                "value_real": sample.value_real,
                "value_text": sample.value_text,
                "quality": sample.quality,
                "sampled_at": sample.sampled_at,
            }
            for sample, series in rows
        ]

    def get_watermark(self, project_id: ProjectId, tier: str) -> datetime | None:
        self._ensure_project_scope(project_id)
        record = self._session.execute(
            select(MetricRollupWatermarkRecord).where(
                MetricRollupWatermarkRecord.project_id == str(project_id),
                MetricRollupWatermarkRecord.tier == tier,
            )
        ).scalar_one_or_none()
        if record is None:
            return None
        return datetime.fromisoformat(record.watermark_bucket_end)

    def set_watermark(self, project_id: ProjectId, tier: str, bucket_end_at: datetime) -> None:
        self._ensure_project_scope(project_id)
        now = datetime.now(UTC).isoformat()
        record = self._session.execute(
            select(MetricRollupWatermarkRecord).where(
                MetricRollupWatermarkRecord.project_id == str(project_id),
                MetricRollupWatermarkRecord.tier == tier,
            )
        ).scalar_one_or_none()
        if record is None:
            self._session.add(
                MetricRollupWatermarkRecord(
                    watermark_id=str(StableIdentifier.new()),
                    project_id=str(project_id),
                    tier=tier,
                    watermark_bucket_end=bucket_end_at.isoformat(),
                    updated_at=now,
                )
            )
            self._session.flush()
            return
        record.watermark_bucket_end = bucket_end_at.isoformat()
        record.updated_at = now

    def oldest_raw_sample_at(self, project_id: ProjectId) -> datetime | None:
        self._ensure_project_scope(project_id)
        value = self._session.execute(
            select(MetricSampleRecord.sampled_at)
            .join(MetricSeriesRecord, MetricSeriesRecord.metric_series_id == MetricSampleRecord.metric_series_id)
            .join(MetricSourceRecord, MetricSourceRecord.metric_source_id == MetricSeriesRecord.metric_source_id)
            .where(MetricSourceRecord.project_id == str(project_id))
            .order_by(MetricSampleRecord.sampled_at)
            .limit(1)
        ).scalar_one_or_none()
        return datetime.fromisoformat(value) if value else None

    def oldest_rollup_at(self, project_id: ProjectId, bucket_size_seconds: int) -> datetime | None:
        self._ensure_project_scope(project_id)
        value = self._session.execute(
            select(MetricRollupRecord.bucket_start)
            .where(
                MetricRollupRecord.project_id == str(project_id),
                MetricRollupRecord.bucket_size_seconds == bucket_size_seconds,
            )
            .order_by(MetricRollupRecord.bucket_start)
            .limit(1)
        ).scalar_one_or_none()
        return datetime.fromisoformat(value) if value else None

    def delete_raw_samples_before_rollup(self, project_id: ProjectId, cutoff: datetime) -> int:
        self._ensure_project_scope(project_id)
        cutoff_iso = cutoff.isoformat()
        rolled_buckets = select(MetricRollupRecord.metric_series_id, MetricRollupRecord.bucket_start).where(
            MetricRollupRecord.project_id == str(project_id),
            MetricRollupRecord.bucket_size_seconds == MINUTE_BUCKET_SECONDS,
        )
        rows = self._session.execute(rolled_buckets).all()
        deleted = 0
        for series_id, bucket_start in rows:
            bucket_start_dt = datetime.fromisoformat(bucket_start)
            bucket_end_dt = bucket_end(bucket_start_dt, MINUTE_BUCKET_SECONDS)
            if bucket_end_dt > cutoff:
                continue
            result = self._session.execute(
                delete(MetricSampleRecord).where(
                    MetricSampleRecord.metric_series_id == series_id,
                    MetricSampleRecord.sampled_at >= bucket_start,
                    MetricSampleRecord.sampled_at < bucket_end_dt.isoformat(),
                )
            )
            deleted += int(result.rowcount or 0)
        return deleted

    def delete_minute_rollups_before(self, project_id: ProjectId, cutoff: datetime) -> int:
        self._ensure_project_scope(project_id)
        covered_hours = {
            floor_to_hour(datetime.fromisoformat(row))
            for row in self._session.execute(
                select(MetricRollupRecord.bucket_start).where(
                    MetricRollupRecord.project_id == str(project_id),
                    MetricRollupRecord.bucket_size_seconds == HOUR_BUCKET_SECONDS,
                )
            ).scalars()
        }
        rows = self._session.execute(
            select(MetricRollupRecord.rollup_id, MetricRollupRecord.bucket_start).where(
                MetricRollupRecord.project_id == str(project_id),
                MetricRollupRecord.bucket_size_seconds == MINUTE_BUCKET_SECONDS,
                MetricRollupRecord.bucket_start < cutoff.isoformat(),
            )
        ).all()
        rollup_ids = [
            rollup_id
            for rollup_id, bucket_start in rows
            if floor_to_hour(datetime.fromisoformat(bucket_start)) in covered_hours
        ]
        if not rollup_ids:
            return 0
        result = self._session.execute(delete(MetricRollupRecord).where(MetricRollupRecord.rollup_id.in_(rollup_ids)))
        return int(result.rowcount or 0)

    def delete_hour_rollups_before(self, project_id: ProjectId, cutoff: datetime) -> int:
        self._ensure_project_scope(project_id)
        result = self._session.execute(
            delete(MetricRollupRecord).where(
                MetricRollupRecord.project_id == str(project_id),
                MetricRollupRecord.bucket_size_seconds == HOUR_BUCKET_SECONDS,
                MetricRollupRecord.bucket_start < cutoff.isoformat(),
            )
        )
        return int(result.rowcount or 0)

    def list_projects_with_metric_data(self) -> list[ProjectId]:
        rows = self._session.execute(select(MetricSourceRecord.project_id).distinct()).scalars()
        return [ProjectId(value) for value in rows]

    def create_alert(
        self,
        *,
        monitoring_alert_id: StableIdentifier,
        project_id: ProjectId,
        name: str,
        severity: str,
        condition_json: dict[str, Any],
        metric_series_id: str | None,
        is_enabled: bool,
        created_at: datetime,
    ) -> MonitoringAlertRecord:
        self._ensure_project_scope(project_id)
        record = MonitoringAlertRecord(
            monitoring_alert_id=str(monitoring_alert_id),
            project_id=str(project_id),
            metric_series_id=metric_series_id,
            name=name,
            severity=severity,
            condition_json=condition_json,
            is_enabled=1 if is_enabled else 0,
            runtime_state="ok",
            pending_since=None,
            created_at=created_at.isoformat(),
            updated_at=created_at.isoformat(),
        )
        self._session.add(record)
        return record

    def update_alert(
        self,
        *,
        project_id: ProjectId,
        monitoring_alert_id: str,
        name: str | None = None,
        severity: str | None = None,
        condition_json: dict[str, Any] | None = None,
        metric_series_id: str | None = None,
        is_enabled: bool | None = None,
        updated_at: datetime,
    ) -> MonitoringAlertRecord | None:
        self._ensure_project_scope(project_id)
        record = self._session.execute(
            select(MonitoringAlertRecord).where(
                MonitoringAlertRecord.project_id == str(project_id),
                MonitoringAlertRecord.monitoring_alert_id == monitoring_alert_id,
            )
        ).scalar_one_or_none()
        if record is None:
            return None
        if name is not None:
            record.name = name
        if severity is not None:
            record.severity = severity
        if condition_json is not None:
            record.condition_json = condition_json
        if metric_series_id is not None:
            record.metric_series_id = metric_series_id
        if is_enabled is not None:
            record.is_enabled = 1 if is_enabled else 0
        record.updated_at = updated_at.isoformat()
        return record

    def delete_alert(self, project_id: ProjectId, monitoring_alert_id: str) -> bool:
        self._ensure_project_scope(project_id)
        record = self._session.execute(
            select(MonitoringAlertRecord).where(
                MonitoringAlertRecord.project_id == str(project_id),
                MonitoringAlertRecord.monitoring_alert_id == monitoring_alert_id,
            )
        ).scalar_one_or_none()
        if record is None:
            return False
        self._session.delete(record)
        return True

    def get_alert(self, project_id: ProjectId, monitoring_alert_id: str) -> MonitoringAlertRecord | None:
        self._ensure_project_scope(project_id)
        return self._session.execute(
            select(MonitoringAlertRecord).where(
                MonitoringAlertRecord.project_id == str(project_id),
                MonitoringAlertRecord.monitoring_alert_id == monitoring_alert_id,
            )
        ).scalar_one_or_none()

    def list_alerts(self, project_id: ProjectId, *, enabled_only: bool = False) -> list[MonitoringAlertRecord]:
        self._ensure_project_scope(project_id)
        query = select(MonitoringAlertRecord).where(MonitoringAlertRecord.project_id == str(project_id))
        if enabled_only:
            query = query.where(MonitoringAlertRecord.is_enabled == 1)
        return list(self._session.execute(query.order_by(MonitoringAlertRecord.name)).scalars())

    def list_enabled_alerts(self, project_id: ProjectId | None = None) -> list[MonitoringAlertRecord]:
        query = select(MonitoringAlertRecord).where(MonitoringAlertRecord.is_enabled == 1)
        if project_id is not None:
            self._ensure_project_scope(project_id)
            query = query.where(MonitoringAlertRecord.project_id == str(project_id))
        return list(self._session.execute(query).scalars())

    def update_alert_runtime(
        self,
        *,
        monitoring_alert_id: str,
        runtime_state: str,
        pending_since: datetime | None,
        updated_at: datetime,
    ) -> None:
        record = self._session.execute(
            select(MonitoringAlertRecord).where(MonitoringAlertRecord.monitoring_alert_id == monitoring_alert_id)
        ).scalar_one_or_none()
        if record is None:
            return
        record.runtime_state = runtime_state
        record.pending_since = pending_since.isoformat() if pending_since else None
        record.updated_at = updated_at.isoformat()

    def add_alert_event(
        self,
        *,
        alert_event_id: StableIdentifier,
        monitoring_alert_id: str,
        project_id: ProjectId,
        status: str,
        triggered_at: datetime,
        resolved_at: datetime | None,
        details_json: dict[str, Any] | None,
    ) -> MonitoringAlertEventRecord:
        self._ensure_project_scope(project_id)
        record = MonitoringAlertEventRecord(
            alert_event_id=str(alert_event_id),
            monitoring_alert_id=monitoring_alert_id,
            project_id=str(project_id),
            status=status,
            triggered_at=triggered_at.isoformat(),
            resolved_at=resolved_at.isoformat() if resolved_at else None,
            incident_group_id=None,
            details_json=details_json or {},
        )
        self._session.add(record)
        return record

    def list_alert_events(self, project_id: ProjectId, *, limit: int = 100) -> list[dict[str, Any]]:
        self._ensure_project_scope(project_id)
        rows = self._session.execute(
            select(MonitoringAlertEventRecord, MonitoringAlertRecord)
            .join(MonitoringAlertRecord, MonitoringAlertRecord.monitoring_alert_id == MonitoringAlertEventRecord.monitoring_alert_id)
            .where(MonitoringAlertEventRecord.project_id == str(project_id))
            .order_by(MonitoringAlertEventRecord.triggered_at.desc())
            .limit(limit)
        ).all()
        return [
            {
                "alert_event_id": event.alert_event_id,
                "monitoring_alert_id": event.monitoring_alert_id,
                "alert_name": alert.name,
                "severity": alert.severity,
                "status": event.status,
                "triggered_at": event.triggered_at,
                "resolved_at": event.resolved_at,
                "details": event.details_json or {},
            }
            for event, alert in rows
        ]

    def latest_sample_value(self, metric_series_id: str) -> float | None:
        value = self._session.execute(
            select(MetricSampleRecord.value_real)
            .where(
                MetricSampleRecord.metric_series_id == metric_series_id,
                MetricSampleRecord.quality.in_(("ok", "estimated")),
                MetricSampleRecord.value_real.is_not(None),
            )
            .order_by(MetricSampleRecord.sampled_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        return float(value) if value is not None else None

    def recent_numeric_samples(
        self,
        metric_series_id: str,
        *,
        start_at: datetime,
        end_at: datetime,
    ) -> list[tuple[datetime, float]]:
        rows = self._session.execute(
            select(MetricSampleRecord.sampled_at, MetricSampleRecord.value_real).where(
                MetricSampleRecord.metric_series_id == metric_series_id,
                MetricSampleRecord.sampled_at >= start_at.isoformat(),
                MetricSampleRecord.sampled_at <= end_at.isoformat(),
                MetricSampleRecord.quality.in_(("ok", "estimated")),
                MetricSampleRecord.value_real.is_not(None),
            )
            .order_by(MetricSampleRecord.sampled_at)
        ).all()
        return [(datetime.fromisoformat(sampled_at), float(value)) for sampled_at, value in rows if value is not None]

    def _ensure_project_scope(self, project_id: ProjectId) -> None:
        if self._project_id is not None and self._project_id != project_id:
            raise ProjectScopeRequired("Repository project_id does not match requested project_id")


def floor_to_hour(timestamp: datetime) -> datetime:
    normalized = timestamp.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    return normalized
