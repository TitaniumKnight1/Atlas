from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.adapters.persistence import AuditRepository, IncidentRepository, ProjectRepository
from backend.domain.incident.export_sanitizer import ExportSanitizationResult, sanitize_export_markdown
from backend.domain.incident.report_builder import IncidentExportReport, OccurrenceExportSection, build_incident_markdown_report
from backend.domain.incident.types import ContextSnapshotType
from backend.domain.shared_kernel import ProjectId, StableIdentifier


def assemble_export_report(
    *,
    project_id: ProjectId,
    group: dict[str, Any],
    occurrences: list[dict[str, Any]],
    timelines: dict[str, dict[str, Any]],
    related_groups: list[dict[str, Any]],
    fingerprint_components: dict[str, Any] | None,
    exported_at: datetime,
) -> IncidentExportReport:
    occurrence_sections: list[OccurrenceExportSection] = []
    shared_runtime: dict[str, Any] = {}
    resources: dict[str, Any] = {}
    startup_order: dict[str, Any] = {}
    config_excerpt: dict[str, Any] = {}
    environment: dict[str, Any] = {}

    for occurrence in occurrences:
        timeline = timelines[occurrence["occurrence_id"]]
        snapshots = {item["context_type"]: item.get("snapshot_json") or {} for item in timeline.get("context_snapshots", [])}
        runtime = snapshots.get(ContextSnapshotType.RUNTIME.value, {})
        logs = snapshots.get(ContextSnapshotType.LOGS.value, {})
        if not shared_runtime and runtime:
            shared_runtime = runtime
        if not resources:
            resources = snapshots.get(ContextSnapshotType.RESOURCES.value, {})
        if not startup_order:
            startup_order = snapshots.get(ContextSnapshotType.STARTUP_ORDER.value, {})
        if not config_excerpt:
            config_excerpt = snapshots.get(ContextSnapshotType.CONFIG_EXCERPT.value, {})
        if not environment:
            environment = snapshots.get(ContextSnapshotType.ENVIRONMENT.value, {})
        occurrence_sections.append(
            OccurrenceExportSection(
                occurrence_id=occurrence["occurrence_id"],
                occurred_at=occurrence["occurred_at"],
                message=occurrence["message"],
                source_type=occurrence["source_type"],
                runtime=runtime,
                logs=logs,
                fingerprint_components=fingerprint_components,
            )
        )

    return IncidentExportReport(
        project_id=str(project_id),
        incident_group_id=group["incident_group_id"],
        title=group["title"],
        severity=group["severity"],
        category=group["category"],
        status=group["status"],
        fingerprint=group["fingerprint"],
        fingerprint_components=fingerprint_components or {},
        occurrence_count=int(group["occurrence_count"]),
        first_seen_at=group["first_seen_at"],
        last_seen_at=group["last_seen_at"],
        related_groups=related_groups,
        occurrences=tuple(occurrence_sections),
        shared_runtime=shared_runtime,
        resources=resources,
        startup_order=startup_order,
        config_excerpt=config_excerpt,
        environment=environment,
        exported_at=exported_at.isoformat(),
    )


def export_incident_markdown(
    *,
    uow: Any,
    project_id: ProjectId,
    incident_group_id: str,
    occurrence_id: str | None,
    redaction_profile: str,
    exports_dir: Path,
    repository: IncidentRepository,
) -> dict[str, Any]:
    group_record = repository.get_group(project_id, incident_group_id)
    if group_record is None:
        raise ValueError(f"Incident not found: {incident_group_id}")

    group = _group_dict(group_record)
    all_occurrences = repository.list_occurrences(project_id, incident_group_id)
    if occurrence_id is not None:
        all_occurrences = [item for item in all_occurrences if item.occurrence_id == occurrence_id]
        if not all_occurrences:
            raise ValueError(f"Occurrence not found: {occurrence_id}")

    occurrence_payloads = [_occurrence_dict(item) for item in all_occurrences]
    timelines = {item.occurrence_id: repository.get_timeline(project_id, item.occurrence_id) for item in all_occurrences}
    related = repository.list_related_groups(project_id, incident_group_id)
    components = repository.get_active_fingerprint_components(incident_group_id)
    now = datetime.now(UTC)

    report = assemble_export_report(
        project_id=project_id,
        group=group,
        occurrences=occurrence_payloads,
        timelines=timelines,
        related_groups=related,
        fingerprint_components=components,
        exported_at=now,
    )
    raw_markdown = build_incident_markdown_report(report)
    sanitized = sanitize_export_markdown(raw_markdown)

    export_id = str(StableIdentifier.new())
    exports_dir.mkdir(parents=True, exist_ok=True)
    export_path = exports_dir / f"{export_id}.md"
    export_path.write_text(sanitized.sanitized_markdown, encoding="utf-8")

    content_hash = hashlib.sha256(sanitized.sanitized_markdown.encode("utf-8")).hexdigest()
    repository.create_export_record(
        incident_export_id=export_id,
        incident_group_id=incident_group_id,
        occurrence_id=occurrence_id,
        export_format="markdown",
        redaction_profile=redaction_profile,
        content_hash=content_hash,
        local_file_path=str(export_path),
        warning_json=_warning_payload(sanitized),
        created_at=now,
    )

    from backend.domain.incident.events import incident_markdown_exported

    event = incident_markdown_exported(project_id, incident_group_id, export_id)
    uow.repository(AuditRepository).record_domain_event(event, published_at=now)
    uow.collect_event(event)

    return {
        "incident_export_id": export_id,
        "incident_group_id": incident_group_id,
        "occurrence_id": occurrence_id,
        "export_format": "markdown",
        "redaction_profile": redaction_profile,
        "content_hash": content_hash,
        "local_file_path": str(export_path),
        "markdown": sanitized.sanitized_markdown,
        "redaction_summary": _warning_payload(sanitized),
        "sanitized": True,
    }


def _warning_payload(result: ExportSanitizationResult) -> dict[str, Any]:
    return {
        "redaction_count": result.redaction_count,
        "categories": result.categories,
        "rules_applied": list(result.rules_applied),
        "policy": "redact_in_place",
        "note": "Export sanitizer is unproven until independent adversarial audit (ADR-0005 family).",
    }


def _group_dict(record: Any) -> dict[str, Any]:
    return {
        "incident_group_id": record.incident_group_id,
        "title": record.title,
        "severity": record.severity,
        "category": record.category,
        "status": record.status,
        "fingerprint": record.fingerprint,
        "occurrence_count": record.occurrence_count,
        "first_seen_at": record.first_seen_at,
        "last_seen_at": record.last_seen_at,
    }


def _occurrence_dict(record: Any) -> dict[str, Any]:
    return {
        "occurrence_id": record.occurrence_id,
        "occurred_at": record.occurred_at,
        "message": record.message,
        "source_type": record.source_type,
    }
