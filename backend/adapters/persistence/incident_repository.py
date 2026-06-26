from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select

from backend.adapters.persistence.models import (
    IncidentBreadcrumbRecord,
    IncidentContextSnapshotRecord,
    IncidentGroupRecord,
    IncidentOccurrenceRecord,
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
            occurrence_count=1,
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
            resource_id=None,
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

    def get_group(self, project_id: ProjectId, incident_group_id: str) -> IncidentGroupRecord | None:
        self._ensure_project_scope(project_id)
        return self._session.execute(
            select(IncidentGroupRecord).where(
                IncidentGroupRecord.project_id == str(project_id),
                IncidentGroupRecord.incident_group_id == incident_group_id,
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
