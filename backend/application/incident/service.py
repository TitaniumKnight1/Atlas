from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from backend.adapters.incident.snapshot_assembler import IncidentSnapshotAssembler
from backend.adapters.persistence import AuditRepository, IncidentRepository, ProjectRepository
from backend.domain.incident import (
    IncidentCategory,
    IncidentGroupStatus,
    IncidentSeverity,
    IncidentSourceType,
    incident_captured,
)
from backend.domain.shared_kernel import ErrorCode, ProjectId, StableIdentifier
from backend.domain.shared_kernel.events import DomainEventEnvelope


class IncidentApplicationError(RuntimeError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


class IncidentApplicationService:
    """M7a local incident capture and snapshot assembly — no export, no fingerprinting, no actions."""

    def __init__(self, *, container: Any) -> None:
        self._container = container
        self._assembler = IncidentSnapshotAssembler(container)

    def register_crash_subscriber(self) -> None:
        self._container.event_bus.register("ServerCrashed", self._on_server_crashed)

    def _on_server_crashed(self, event: DomainEventEnvelope) -> None:
        if event.project_id is None:
            return
        payload = event.payload
        process_run_id = str(payload.get("process_run_id", ""))
        exit_code = payload.get("exit_code")
        if not process_run_id:
            return
        self.capture_server_crash(event.project_id, process_run_id=process_run_id, exit_code=exit_code)

    def capture_server_crash(self, project_id: ProjectId, *, process_run_id: str, exit_code: int | None) -> dict[str, Any]:
        now = datetime.now(UTC)
        assembled = self._assembler.assemble(project_id, process_run_id=process_run_id, exit_code=exit_code)
        group_id = StableIdentifier.new()
        occurrence_id = StableIdentifier.new()
        fingerprint = f"capture:{occurrence_id}"
        message_hash = hashlib.sha256(assembled.message.encode("utf-8")).hexdigest()
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            self._require_project(uow.repository(ProjectRepository), project_id)
            repository = uow.repository(IncidentRepository)
            repository.create_group(
                incident_group_id=group_id,
                project_id=project_id,
                fingerprint=fingerprint,
                title=assembled.message,
                severity=IncidentSeverity.FATAL.value,
                category=IncidentCategory.CRASH.value,
                status=IncidentGroupStatus.UNRESOLVED.value,
                first_seen_at=now,
                last_seen_at=now,
            )
            repository.create_occurrence(
                occurrence_id=occurrence_id,
                incident_group_id=str(group_id),
                project_id=project_id,
                occurred_at=now,
                source_type=IncidentSourceType.PROCESS.value,
                message=assembled.message,
                raw_message_hash=message_hash,
            )
            uow.session.flush()
            repository.add_breadcrumbs(str(occurrence_id), assembled.breadcrumbs)
            repository.add_context_snapshots(str(occurrence_id), assembled.context_snapshots)
            if assembled.stack_trace is not None:
                repository.add_stack_trace(str(occurrence_id), assembled.stack_trace)
            captured_event = incident_captured(
                project_id,
                str(group_id),
                str(occurrence_id),
                IncidentSeverity.FATAL.value,
                IncidentCategory.CRASH.value,
            )
            uow.repository(AuditRepository).record_domain_event(captured_event, published_at=now)
            uow.collect_event(captured_event)
            uow.commit()
        return {
            "incident_group_id": str(group_id),
            "occurrence_id": str(occurrence_id),
            "severity": IncidentSeverity.FATAL.value,
            "category": IncidentCategory.CRASH.value,
            "message": assembled.message,
        }

    def list_incidents(self, project_id: ProjectId, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext

            records = IncidentRepository(RepositoryContext(session=session, project_id=project_id)).list_groups(project_id, limit=limit)
        return [_group_data(record) for record in records]

    def get_incident(self, project_id: ProjectId, incident_group_id: str) -> dict[str, Any]:
        with self._container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext

            repository = IncidentRepository(RepositoryContext(session=session, project_id=project_id))
            group = repository.get_group(project_id, incident_group_id)
            if group is None:
                raise IncidentApplicationError(ErrorCode.NOT_FOUND, f"Incident not found: {incident_group_id}")
            occurrences = repository.list_occurrences(project_id, incident_group_id)
        return {
            **_group_data(group),
            "occurrences": [_occurrence_data(item) for item in occurrences],
        }

    def get_occurrence_timeline(self, project_id: ProjectId, occurrence_id: str) -> dict[str, Any]:
        with self._container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext

            repository = IncidentRepository(RepositoryContext(session=session, project_id=project_id))
            occurrence = repository.get_occurrence(project_id, occurrence_id)
            if occurrence is None:
                raise IncidentApplicationError(ErrorCode.NOT_FOUND, f"Occurrence not found: {occurrence_id}")
            timeline = repository.get_timeline(project_id, occurrence_id)
        return {"occurrence": _occurrence_data(occurrence), **timeline}

    def _require_project(self, repository: ProjectRepository, project_id: ProjectId) -> None:
        if repository.get_project(project_id) is None:
            raise IncidentApplicationError(ErrorCode.NOT_FOUND, f"Project not found: {project_id}")


def _group_data(record: Any) -> dict[str, Any]:
    return {
        "incident_group_id": record.incident_group_id,
        "project_id": record.project_id,
        "fingerprint": record.fingerprint,
        "title": record.title,
        "severity": record.severity,
        "category": record.category,
        "status": record.status,
        "first_seen_at": record.first_seen_at,
        "last_seen_at": record.last_seen_at,
        "occurrence_count": record.occurrence_count,
    }


def _occurrence_data(record: Any) -> dict[str, Any]:
    return {
        "occurrence_id": record.occurrence_id,
        "incident_group_id": record.incident_group_id,
        "project_id": record.project_id,
        "occurred_at": record.occurred_at,
        "source_type": record.source_type,
        "message": record.message,
    }
