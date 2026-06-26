from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select

from backend.adapters.persistence.models import MetricSampleRecord, MetricSeriesRecord, MetricSourceRecord
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

    def _ensure_project_scope(self, project_id: ProjectId) -> None:
        if self._project_id is not None and self._project_id != project_id:
            raise ProjectScopeRequired("Repository project_id does not match requested project_id")
