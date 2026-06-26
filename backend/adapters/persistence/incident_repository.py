from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select, update

from backend.adapters.persistence.models import (
    IncidentBreadcrumbRecord,
    IncidentContextSnapshotRecord,
    IncidentFingerprintRecord,
    IncidentGroupRecord,
    IncidentOccurrenceRecord,
    IncidentRelatedGroupRecord,
    IncidentStackTraceRecord,
)
from backend.domain.shared_kernel import ProjectId, StableIdentifier
from backend.infrastructure.unit_of_work import ProjectScopeRequired, RepositoryContext


class IncidentRepository:
    def __init__(self, context: RepositoryContext) -> None:
        self._session = context.session
        self._project_id = context.project_id

    def create_group(
        self,
        *,
        incident_group_id: StableIdentifier,
        project_id: ProjectId,
        fingerprint: str,
        title: str,
        severity: str,
        category: str,
        status: str,
        first_seen_at: datetime,
        last_seen_at: datetime,
        occurrence_count: int = 1,
    ) -> IncidentGroupRecord:
        self._ensure_project_scope(project_id)
        record = IncidentGroupRecord(
            incident_group_id=str(incident_group_id),
            project_id=str(project_id),
            fingerprint=fingerprint,
            title=title,
            severity=severity,
            category=category,
            status=status,
            first_seen_at=first_seen_at.isoformat(),
            last_seen_at=last_seen_at.isoformat(),
            occurrence_count=occurrence_count,
            assigned_to=None,
        )
        self._session.add(record)
        return record

    def create_occurrence(
        self,
        *,
        occurrence_id: StableIdentifier,
        incident_group_id: str,
        project_id: ProjectId,
        occurred_at: datetime,
        source_type: str,
        message: str,
        raw_message_hash: str | None = None,
        resource_id: str | None = None,
    ) -> IncidentOccurrenceRecord:
        self._ensure_project_scope(project_id)
        record = IncidentOccurrenceRecord(
            occurrence_id=str(occurrence_id),
            incident_group_id=incident_group_id,
            project_id=str(project_id),
            environment_id=None,
            occurred_at=occurred_at.isoformat(),
            source_type=source_type,
            message=message,
            raw_message_hash=raw_message_hash,
            artifact_version_id=None,
            git_status_snapshot_id=None,
            automation_run_id=None,
            resource_id=resource_id,
        )
        self._session.add(record)
        return record

    def add_breadcrumbs(self, occurrence_id: str, breadcrumbs: list[dict[str, Any]]) -> int:
        for item in breadcrumbs:
            self._session.add(
                IncidentBreadcrumbRecord(
                    breadcrumb_id=str(StableIdentifier.new()),
                    occurrence_id=occurrence_id,
                    timestamp=item["timestamp"],
                    category=item["category"],
                    level=item["level"],
                    message=item["message"],
                    data_json=item.get("data"),
                    sort_order=int(item["sort_order"]),
                )
            )
        return len(breadcrumbs)

    def add_context_snapshots(self, occurrence_id: str, snapshots: list[dict[str, Any]]) -> int:
        for item in snapshots:
            self._session.add(
                IncidentContextSnapshotRecord(
                    context_snapshot_id=str(StableIdentifier.new()),
                    occurrence_id=occurrence_id,
                    context_type=item["context_type"],
                    content_hash=None,
                    local_file_id=None,
                    snapshot_json=item["snapshot_json"],
                    redaction_state=item["redaction_state"],
                    captured_at=item["captured_at"],
                )
            )
        return len(snapshots)

    def add_stack_trace(self, occurrence_id: str, stack_trace: dict[str, Any]) -> IncidentStackTraceRecord:
        record = IncidentStackTraceRecord(
            stack_trace_id=str(StableIdentifier.new()),
            occurrence_id=occurrence_id,
            exception_type=stack_trace.get("exception_type"),
            exception_value=stack_trace.get("exception_value"),
            language=stack_trace.get("language"),
            thread_name=None,
            is_primary=1,
        )
        self._session.add(record)
        return record

    def record_fingerprint(
        self,
        *,
        incident_group_id: str,
        fingerprint: str,
        algorithm_version: str,
        components: dict[str, object],
        created_at: datetime,
    ) -> IncidentFingerprintRecord:
        existing = self._session.execute(
            select(IncidentFingerprintRecord).where(
                IncidentFingerprintRecord.incident_group_id == incident_group_id,
                IncidentFingerprintRecord.fingerprint == fingerprint,
                IncidentFingerprintRecord.algorithm_version == algorithm_version,
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.is_active = 1
            existing.components_json = components
            return existing
        record = IncidentFingerprintRecord(
            incident_fingerprint_id=str(StableIdentifier.new()),
            incident_group_id=incident_group_id,
            fingerprint=fingerprint,
            algorithm_version=algorithm_version,
            components_json=components,
            is_active=1,
            created_at=created_at.isoformat(),
        )
        self._session.add(record)
        return record

    def get_group(self, project_id: ProjectId, incident_group_id: str) -> IncidentGroupRecord | None:
        self._ensure_project_scope(project_id)
        return self._session.execute(
            select(IncidentGroupRecord).where(
                IncidentGroupRecord.project_id == str(project_id),
                IncidentGroupRecord.incident_group_id == incident_group_id,
            )
        ).scalar_one_or_none()

    def get_group_by_fingerprint(self, project_id: ProjectId, fingerprint: str) -> IncidentGroupRecord | None:
        self._ensure_project_scope(project_id)
        return self._session.execute(
            select(IncidentGroupRecord).where(
                IncidentGroupRecord.project_id == str(project_id),
                IncidentGroupRecord.fingerprint == fingerprint,
            )
        ).scalar_one_or_none()

    def list_groups(self, project_id: ProjectId, *, limit: int = 100) -> list[IncidentGroupRecord]:
        self._ensure_project_scope(project_id)
        return list(
            self._session.execute(
                select(IncidentGroupRecord)
                .where(IncidentGroupRecord.project_id == str(project_id))
                .order_by(IncidentGroupRecord.last_seen_at.desc())
                .limit(limit)
            ).scalars()
        )

    def list_placeholder_groups(self, project_id: ProjectId) -> list[IncidentGroupRecord]:
        self._ensure_project_scope(project_id)
        return list(
            self._session.execute(
                select(IncidentGroupRecord)
                .where(
                    IncidentGroupRecord.project_id == str(project_id),
                    IncidentGroupRecord.fingerprint.like("capture:%"),
                )
                .order_by(IncidentGroupRecord.first_seen_at)
            ).scalars()
        )

    def update_group_aggregates(
        self,
        *,
        incident_group_id: str,
        first_seen_at: str,
        last_seen_at: str,
        occurrence_count: int,
    ) -> None:
        self._session.execute(
            update(IncidentGroupRecord)
            .where(IncidentGroupRecord.incident_group_id == incident_group_id)
            .values(first_seen_at=first_seen_at, last_seen_at=last_seen_at, occurrence_count=occurrence_count)
        )

    def update_group_fingerprint(self, *, incident_group_id: str, fingerprint: str) -> None:
        self._session.execute(
            update(IncidentGroupRecord).where(IncidentGroupRecord.incident_group_id == incident_group_id).values(fingerprint=fingerprint)
        )

    def append_occurrence_to_group(
        self,
        *,
        project_id: ProjectId,
        incident_group_id: str,
        occurred_at: datetime,
    ) -> IncidentGroupRecord:
        group = self.get_group(project_id, incident_group_id)
        if group is None:
            raise ValueError(f"group not found: {incident_group_id}")
        occurred_iso = occurred_at.isoformat()
        first_seen = group.first_seen_at if group.first_seen_at <= occurred_iso else occurred_iso
        last_seen = group.last_seen_at if group.last_seen_at >= occurred_iso else occurred_iso
        count = int(group.occurrence_count) + 1
        self.update_group_aggregates(
            incident_group_id=incident_group_id,
            first_seen_at=first_seen,
            last_seen_at=last_seen,
            occurrence_count=count,
        )
        group.first_seen_at = first_seen
        group.last_seen_at = last_seen
        group.occurrence_count = count
        return group

    def move_occurrence(self, *, occurrence_id: str, incident_group_id: str) -> None:
        self._session.execute(
            update(IncidentOccurrenceRecord)
            .where(IncidentOccurrenceRecord.occurrence_id == occurrence_id)
            .values(incident_group_id=incident_group_id)
        )

    def delete_group(self, incident_group_id: str) -> None:
        self._session.execute(delete(IncidentGroupRecord).where(IncidentGroupRecord.incident_group_id == incident_group_id))

    def count_occurrences_for_group(self, project_id: ProjectId, incident_group_id: str) -> int:
        self._ensure_project_scope(project_id)
        return int(
            self._session.scalar(
                select(func.count())
                .select_from(IncidentOccurrenceRecord)
                .where(
                    IncidentOccurrenceRecord.project_id == str(project_id),
                    IncidentOccurrenceRecord.incident_group_id == incident_group_id,
                )
            )
            or 0
        )

    def recompute_group_aggregates(self, project_id: ProjectId, incident_group_id: str) -> None:
        occurrences = self.list_occurrences(project_id, incident_group_id)
        if not occurrences:
            return
        timestamps = [item.occurred_at for item in occurrences]
        self.update_group_aggregates(
            incident_group_id=incident_group_id,
            first_seen_at=min(timestamps),
            last_seen_at=max(timestamps),
            occurrence_count=len(occurrences),
        )

    def get_occurrence(self, project_id: ProjectId, occurrence_id: str) -> IncidentOccurrenceRecord | None:
        self._ensure_project_scope(project_id)
        return self._session.execute(
            select(IncidentOccurrenceRecord).where(
                IncidentOccurrenceRecord.project_id == str(project_id),
                IncidentOccurrenceRecord.occurrence_id == occurrence_id,
            )
        ).scalar_one_or_none()

    def list_occurrences(self, project_id: ProjectId, incident_group_id: str) -> list[IncidentOccurrenceRecord]:
        self._ensure_project_scope(project_id)
        return list(
            self._session.execute(
                select(IncidentOccurrenceRecord)
                .where(
                    IncidentOccurrenceRecord.project_id == str(project_id),
                    IncidentOccurrenceRecord.incident_group_id == incident_group_id,
                )
                .order_by(IncidentOccurrenceRecord.occurred_at.desc())
            ).scalars()
        )

    def list_all_occurrences(self, project_id: ProjectId) -> list[IncidentOccurrenceRecord]:
        self._ensure_project_scope(project_id)
        return list(
            self._session.execute(
                select(IncidentOccurrenceRecord)
                .where(IncidentOccurrenceRecord.project_id == str(project_id))
                .order_by(IncidentOccurrenceRecord.occurred_at)
            ).scalars()
        )

    def get_timeline(self, project_id: ProjectId, occurrence_id: str) -> dict[str, Any]:
        self._ensure_project_scope(project_id)
        breadcrumbs = list(
            self._session.execute(
                select(IncidentBreadcrumbRecord)
                .where(IncidentBreadcrumbRecord.occurrence_id == occurrence_id)
                .order_by(IncidentBreadcrumbRecord.sort_order)
            ).scalars()
        )
        contexts = list(
            self._session.execute(
                select(IncidentContextSnapshotRecord).where(IncidentContextSnapshotRecord.occurrence_id == occurrence_id)
            ).scalars()
        )
        stack = self._session.execute(
            select(IncidentStackTraceRecord).where(IncidentStackTraceRecord.occurrence_id == occurrence_id)
        ).scalar_one_or_none()
        return {
            "breadcrumbs": [_breadcrumb_data(item) for item in breadcrumbs],
            "context_snapshots": [_context_data(item) for item in contexts],
            "stack_trace": _stack_data(stack) if stack is not None else None,
        }

    def get_group_timeline(self, project_id: ProjectId, incident_group_id: str) -> list[dict[str, Any]]:
        occurrences = self.list_occurrences(project_id, incident_group_id)
        return [
            {
                "occurrence_id": item.occurrence_id,
                "occurred_at": item.occurred_at,
                "message": item.message,
                "source_type": item.source_type,
            }
            for item in occurrences
        ]

    def link_related_groups(
        self,
        *,
        source_group_id: str,
        target_group_id: str,
        relation_type: str,
        confidence: float,
        created_at: datetime,
    ) -> IncidentRelatedGroupRecord | None:
        if source_group_id == target_group_id:
            return None
        ordered = sorted([source_group_id, target_group_id])
        source, target = ordered[0], ordered[1]
        existing = self._session.execute(
            select(IncidentRelatedGroupRecord).where(
                IncidentRelatedGroupRecord.source_group_id == source,
                IncidentRelatedGroupRecord.target_group_id == target,
                IncidentRelatedGroupRecord.relation_type == relation_type,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        record = IncidentRelatedGroupRecord(
            incident_relation_id=str(StableIdentifier.new()),
            source_group_id=source,
            target_group_id=target,
            relation_type=relation_type,
            confidence=confidence,
            created_at=created_at.isoformat(),
        )
        self._session.add(record)
        return record

    def list_related_groups(self, project_id: ProjectId, incident_group_id: str) -> list[dict[str, Any]]:
        self._ensure_project_scope(project_id)
        rows = list(
            self._session.execute(
                select(IncidentRelatedGroupRecord).where(
                    (IncidentRelatedGroupRecord.source_group_id == incident_group_id)
                    | (IncidentRelatedGroupRecord.target_group_id == incident_group_id)
                )
            ).scalars()
        )
        results: list[dict[str, Any]] = []
        for row in rows:
            other_id = row.target_group_id if row.source_group_id == incident_group_id else row.source_group_id
            other = self.get_group(project_id, other_id)
            if other is None:
                continue
            results.append(
                {
                    "incident_relation_id": row.incident_relation_id,
                    "related_group_id": other.incident_group_id,
                    "relation_type": row.relation_type,
                    "confidence": row.confidence,
                    "title": other.title,
                    "fingerprint": other.fingerprint,
                }
            )
        return results

    def get_active_fingerprint_components(self, incident_group_id: str) -> dict[str, object] | None:
        record = self._session.execute(
            select(IncidentFingerprintRecord)
            .where(
                IncidentFingerprintRecord.incident_group_id == incident_group_id,
                IncidentFingerprintRecord.is_active == 1,
            )
            .order_by(IncidentFingerprintRecord.created_at.desc())
        ).scalar_one_or_none()
        return dict(record.components_json or {}) if record is not None else None

    def has_placeholder_groups(self, project_id: ProjectId) -> bool:
        return bool(self.list_placeholder_groups(project_id))

    def _ensure_project_scope(self, project_id: ProjectId) -> None:
        if self._project_id is not None and self._project_id != project_id:
            raise ProjectScopeRequired("Repository project_id does not match requested project_id")


def _breadcrumb_data(record: IncidentBreadcrumbRecord) -> dict[str, Any]:
    return {
        "breadcrumb_id": record.breadcrumb_id,
        "timestamp": record.timestamp,
        "category": record.category,
        "level": record.level,
        "message": record.message,
        "data": record.data_json or {},
        "sort_order": record.sort_order,
    }


def _context_data(record: IncidentContextSnapshotRecord) -> dict[str, Any]:
    return {
        "context_snapshot_id": record.context_snapshot_id,
        "context_type": record.context_type,
        "snapshot_json": record.snapshot_json or {},
        "redaction_state": record.redaction_state,
        "captured_at": record.captured_at,
    }


def _stack_data(record: IncidentStackTraceRecord) -> dict[str, Any]:
    return {
        "stack_trace_id": record.stack_trace_id,
        "exception_type": record.exception_type,
        "exception_value": record.exception_value,
        "language": record.language,
        "is_primary": bool(record.is_primary),
    }