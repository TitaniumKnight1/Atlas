from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from backend.adapters.incident.signal_extractor import signals_from_assembled
from backend.adapters.incident.snapshot_assembler import IncidentSnapshotAssembler
from backend.adapters.persistence import AuditRepository, IncidentRepository, ProjectRepository
from backend.application.incident.export_service import export_incident_markdown
from backend.application.incident.grouping_service import (
    compare_groups,
    grouping_existing_group,
    link_related_groups,
    migrate_placeholder_groups,
)
from backend.domain.incident import (
    IncidentCategory,
    IncidentGroupStatus,
    IncidentSeverity,
    IncidentSourceType,
    incident_captured,
    incident_grouped,
    new_incident_group_created,
    occurrence_deduplicated,
)
from backend.domain.incident.fingerprint import compute_fingerprint
from backend.domain.incident.grouping import GroupingAction, decide_grouping
from backend.domain.shared_kernel import ErrorCode, ProjectId, StableIdentifier
from backend.domain.shared_kernel.events import DomainEventEnvelope


class IncidentApplicationError(RuntimeError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


class IncidentApplicationService:
    """M7a capture + M7b fingerprinting, deduplication, and grouping."""

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

    def ensure_grouping_ready(self, project_id: ProjectId) -> None:
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(IncidentRepository)
            if not repository.has_placeholder_groups(project_id):
                uow.commit()
                return
            migrate_placeholder_groups(uow, project_id)
            uow.commit()

    def migrate_placeholder_incidents(self, project_id: ProjectId) -> dict[str, int]:
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            self._require_project(uow.repository(ProjectRepository), project_id)
            result = migrate_placeholder_groups(uow, project_id)
            uow.commit()
        return result

    def capture_server_crash(self, project_id: ProjectId, *, process_run_id: str, exit_code: int | None) -> dict[str, Any]:
        self.ensure_grouping_ready(project_id)
        now = datetime.now(UTC)
        assembled = self._assembler.assemble(project_id, process_run_id=process_run_id, exit_code=exit_code)
        signals = signals_from_assembled(
            message=assembled.message,
            context_snapshots=assembled.context_snapshots,
            stack_trace=assembled.stack_trace,
        )
        fingerprint_result = compute_fingerprint(signals)
        occurrence_id = StableIdentifier.new()
        message_hash = hashlib.sha256(assembled.message.encode("utf-8")).hexdigest()
        resource_id = fingerprint_result.components.get("resource_hint")

        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            self._require_project(uow.repository(ProjectRepository), project_id)
            repository = uow.repository(IncidentRepository)
            existing = repository.get_group_by_fingerprint(project_id, fingerprint_result.fingerprint)
            decision = decide_grouping(
                fingerprint_result.fingerprint,
                grouping_existing_group(existing) if existing is not None else None,
            )

            if decision.action == GroupingAction.MATCH_EXISTING:
                group_id = decision.incident_group_id
                assert group_id is not None
                repository.create_occurrence(
                    occurrence_id=occurrence_id,
                    incident_group_id=group_id,
                    project_id=project_id,
                    occurred_at=now,
                    source_type=IncidentSourceType.PROCESS.value,
                    message=assembled.message,
                    raw_message_hash=message_hash,
                    resource_id=str(resource_id) if isinstance(resource_id, str) else None,
                )
                uow.session.flush()
                repository.add_breadcrumbs(str(occurrence_id), assembled.breadcrumbs)
                repository.add_context_snapshots(str(occurrence_id), assembled.context_snapshots)
                if assembled.stack_trace is not None:
                    repository.add_stack_trace(str(occurrence_id), assembled.stack_trace)
                group = repository.append_occurrence_to_group(
                    project_id=project_id,
                    incident_group_id=group_id,
                    occurred_at=now,
                )
                repository.record_fingerprint(
                    incident_group_id=group_id,
                    fingerprint=fingerprint_result.fingerprint,
                    algorithm_version=fingerprint_result.algorithm_version,
                    components=fingerprint_result.components,
                    created_at=now,
                )
                deduped = occurrence_deduplicated(project_id, group_id, str(occurrence_id), fingerprint_result.fingerprint)
                grouped = incident_grouped(project_id, group_id, fingerprint_result.fingerprint, int(group.occurrence_count))
                uow.repository(AuditRepository).record_domain_event(deduped, published_at=now)
                uow.repository(AuditRepository).record_domain_event(grouped, published_at=now)
                uow.collect_event(deduped)
                uow.collect_event(grouped)
            else:
                group_id = str(StableIdentifier.new())
                repository.create_group(
                    incident_group_id=StableIdentifier(group_id),
                    project_id=project_id,
                    fingerprint=fingerprint_result.fingerprint,
                    title=assembled.message,
                    severity=IncidentSeverity.FATAL.value,
                    category=IncidentCategory.CRASH.value,
                    status=IncidentGroupStatus.UNRESOLVED.value,
                    first_seen_at=now,
                    last_seen_at=now,
                    occurrence_count=1,
                )
                repository.create_occurrence(
                    occurrence_id=occurrence_id,
                    incident_group_id=group_id,
                    project_id=project_id,
                    occurred_at=now,
                    source_type=IncidentSourceType.PROCESS.value,
                    message=assembled.message,
                    raw_message_hash=message_hash,
                    resource_id=str(resource_id) if isinstance(resource_id, str) else None,
                )
                uow.session.flush()
                repository.add_breadcrumbs(str(occurrence_id), assembled.breadcrumbs)
                repository.add_context_snapshots(str(occurrence_id), assembled.context_snapshots)
                if assembled.stack_trace is not None:
                    repository.add_stack_trace(str(occurrence_id), assembled.stack_trace)
                repository.record_fingerprint(
                    incident_group_id=group_id,
                    fingerprint=fingerprint_result.fingerprint,
                    algorithm_version=fingerprint_result.algorithm_version,
                    components=fingerprint_result.components,
                    created_at=now,
                )
                created = new_incident_group_created(project_id, group_id, str(occurrence_id), fingerprint_result.fingerprint)
                uow.repository(AuditRepository).record_domain_event(created, published_at=now)
                uow.collect_event(created)

            captured = incident_captured(
                project_id,
                group_id,
                str(occurrence_id),
                IncidentSeverity.FATAL.value,
                IncidentCategory.CRASH.value,
            )
            uow.repository(AuditRepository).record_domain_event(captured, published_at=now)
            uow.collect_event(captured)
            link_related_groups(repository, project_id)
            uow.commit()

        return {
            "incident_group_id": group_id,
            "occurrence_id": str(occurrence_id),
            "fingerprint": fingerprint_result.fingerprint,
            "severity": IncidentSeverity.FATAL.value,
            "category": IncidentCategory.CRASH.value,
            "message": assembled.message,
            "deduplicated": decision.action == GroupingAction.MATCH_EXISTING,
        }

    def list_incidents(self, project_id: ProjectId, *, limit: int = 100) -> list[dict[str, Any]]:
        self.ensure_grouping_ready(project_id)
        with self._container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext

            records = IncidentRepository(RepositoryContext(session=session, project_id=project_id)).list_groups(project_id, limit=limit)
        return [_group_data(record) for record in records]

    def get_incident(self, project_id: ProjectId, incident_group_id: str) -> dict[str, Any]:
        self.ensure_grouping_ready(project_id)
        with self._container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext

            repository = IncidentRepository(RepositoryContext(session=session, project_id=project_id))
            group = repository.get_group(project_id, incident_group_id)
            if group is None:
                raise IncidentApplicationError(ErrorCode.NOT_FOUND, f"Incident not found: {incident_group_id}")
            occurrences = repository.list_occurrences(project_id, incident_group_id)
            related = repository.list_related_groups(project_id, incident_group_id)
            components = repository.get_active_fingerprint_components(incident_group_id)
        return {
            **_group_data(group),
            "fingerprint_components": components,
            "occurrences": [_occurrence_data(item) for item in occurrences],
            "related_groups": related,
        }

    def get_group_timeline(self, project_id: ProjectId, incident_group_id: str) -> dict[str, Any]:
        self.ensure_grouping_ready(project_id)
        with self._container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext

            repository = IncidentRepository(RepositoryContext(session=session, project_id=project_id))
            group = repository.get_group(project_id, incident_group_id)
            if group is None:
                raise IncidentApplicationError(ErrorCode.NOT_FOUND, f"Incident not found: {incident_group_id}")
            timeline = repository.get_group_timeline(project_id, incident_group_id)
        return {"incident_group_id": incident_group_id, "timeline": timeline}

    def get_occurrence_timeline(self, project_id: ProjectId, occurrence_id: str) -> dict[str, Any]:
        with self._container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext

            repository = IncidentRepository(RepositoryContext(session=session, project_id=project_id))
            occurrence = repository.get_occurrence(project_id, occurrence_id)
            if occurrence is None:
                raise IncidentApplicationError(ErrorCode.NOT_FOUND, f"Occurrence not found: {occurrence_id}")
            timeline = repository.get_timeline(project_id, occurrence_id)
        return {"occurrence": _occurrence_data(occurrence), **timeline}

    def compare_incidents(self, project_id: ProjectId, *, incident_group_ids: list[str]) -> dict[str, Any]:
        self.ensure_grouping_ready(project_id)
        if len(incident_group_ids) < 2:
            raise IncidentApplicationError(ErrorCode.VALIDATION_FAILED, "At least two incident groups are required")
        payloads: list[dict[str, Any]] = []
        with self._container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext

            repository = IncidentRepository(RepositoryContext(session=session, project_id=project_id))
            for group_id in incident_group_ids:
                group = repository.get_group(project_id, group_id)
                if group is None:
                    raise IncidentApplicationError(ErrorCode.NOT_FOUND, f"Incident not found: {group_id}")
                payloads.append(
                    {
                        **_group_data(group),
                        "fingerprint_components": repository.get_active_fingerprint_components(group_id),
                    }
                )
        return compare_groups(payloads)

    def export_incident_markdown(
        self,
        project_id: ProjectId,
        *,
        incident_group_id: str,
        occurrence_id: str | None = None,
        redaction_profile: str = "default",
    ) -> dict[str, Any]:
        """Single sanitized export path — always redacts before returning Markdown."""
        self.ensure_grouping_ready(project_id)
        exports_dir = self._container.app_data_dir / "exports" / str(project_id)
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            self._require_project(uow.repository(ProjectRepository), project_id)
            try:
                result = export_incident_markdown(
                    uow=uow,
                    project_id=project_id,
                    incident_group_id=incident_group_id,
                    occurrence_id=occurrence_id,
                    redaction_profile=redaction_profile,
                    exports_dir=exports_dir,
                    repository=uow.repository(IncidentRepository),
                )
            except ValueError as error:
                raise IncidentApplicationError(ErrorCode.NOT_FOUND, str(error)) from error
            uow.commit()
        return result

    def list_incident_exports(self, project_id: ProjectId, incident_group_id: str) -> list[dict[str, Any]]:
        self.ensure_grouping_ready(project_id)
        with self._container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext

            repository = IncidentRepository(RepositoryContext(session=session, project_id=project_id))
            if repository.get_group(project_id, incident_group_id) is None:
                raise IncidentApplicationError(ErrorCode.NOT_FOUND, f"Incident not found: {incident_group_id}")
            records = repository.list_exports(project_id, incident_group_id)
        return [_export_data(record) for record in records]

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


def _export_data(record: Any) -> dict[str, Any]:
    return {
        "incident_export_id": record.incident_export_id,
        "incident_group_id": record.incident_group_id,
        "occurrence_id": record.occurrence_id,
        "export_format": record.export_format,
        "redaction_profile": record.redaction_profile,
        "content_hash": record.content_hash,
        "local_file_path": record.local_file_path,
        "created_at": record.created_at,
        "redaction_summary": record.warning_json or {},
    }
