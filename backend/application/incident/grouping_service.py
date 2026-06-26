from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from backend.adapters.incident.signal_extractor import signals_from_timeline
from backend.adapters.persistence import IncidentRepository
from backend.domain.incident.fingerprint import FingerprintResult, compute_fingerprint, is_placeholder_fingerprint
from backend.domain.incident.grouping import ExistingIncidentGroup, decide_grouping
from backend.domain.shared_kernel import ProjectId


def migrate_placeholder_groups(uow: Any, project_id: ProjectId) -> dict[str, int]:
    """Re-fingerprint and re-group M7a placeholder rows idempotently without duplicating occurrences."""
    repository = uow.repository(IncidentRepository)
    placeholders = repository.list_placeholder_groups(project_id)
    if not placeholders:
        return {"groups_merged": 0, "occurrences_moved": 0, "groups_deleted": 0}

    plans: list[tuple[str, str, str, FingerprintResult]] = []
    for group in placeholders:
        for occurrence in repository.list_occurrences(project_id, group.incident_group_id):
            timeline = repository.get_timeline(project_id, occurrence.occurrence_id)
            signals = signals_from_timeline(
                message=occurrence.message,
                context_snapshots=timeline["context_snapshots"],
                stack_trace=timeline["stack_trace"],
            )
            plans.append(
                (
                    occurrence.occurrence_id,
                    group.incident_group_id,
                    group.first_seen_at,
                    compute_fingerprint(signals),
                )
            )

    buckets: dict[str, list[tuple[str, str, str, FingerprintResult]]] = defaultdict(list)
    for plan in plans:
        buckets[plan[3].fingerprint].append(plan)

    moved = 0
    deleted = 0
    merged = 0
    now = datetime.now(UTC)
    for fingerprint, items in buckets.items():
        existing = repository.get_group_by_fingerprint(project_id, fingerprint)
        if existing is not None and not is_placeholder_fingerprint(existing.fingerprint):
            target_id = existing.incident_group_id
        else:
            target_id = min(items, key=lambda item: item[2])[1]
            repository.update_group_fingerprint(incident_group_id=target_id, fingerprint=fingerprint)
            merged += 1

        repository.record_fingerprint(
            incident_group_id=target_id,
            fingerprint=fingerprint,
            algorithm_version=items[0][3].algorithm_version,
            components=items[0][3].components,
            created_at=now,
        )

        for occurrence_id, source_group_id, _, _ in items:
            if source_group_id != target_id:
                repository.move_occurrence(occurrence_id=occurrence_id, incident_group_id=target_id)
                moved += 1

        repository.recompute_group_aggregates(project_id, target_id)

        for source_group_id in {item[1] for item in items}:
            if source_group_id == target_id:
                continue
            if repository.count_occurrences_for_group(project_id, source_group_id) == 0:
                repository.delete_group(source_group_id)
                deleted += 1

    link_related_groups(repository, project_id)
    return {"groups_merged": merged, "occurrences_moved": moved, "groups_deleted": deleted}


def link_related_groups(repository: IncidentRepository, project_id: ProjectId) -> None:
    groups = repository.list_groups(project_id, limit=10_000)
    hints: dict[str, list[str]] = defaultdict(list)
    for group in groups:
        if is_placeholder_fingerprint(group.fingerprint):
            continue
        components = repository.get_active_fingerprint_components(group.incident_group_id) or {}
        hint = components.get("resource_hint")
        if isinstance(hint, str) and hint:
            hints[hint].append(group.incident_group_id)

    now = datetime.now(UTC)
    for group_ids in hints.values():
        if len(group_ids) < 2:
            continue
        fingerprints = {
            repository.get_group(project_id, group_id).fingerprint
            for group_id in group_ids
            if repository.get_group(project_id, group_id) is not None
        }
        if len(fingerprints) < 2:
            continue
        for index, source_id in enumerate(group_ids):
            for target_id in group_ids[index + 1 :]:
                repository.link_related_groups(
                    source_group_id=source_id,
                    target_group_id=target_id,
                    relation_type="same_root_cause",
                    confidence=0.6,
                    created_at=now,
                )


def grouping_existing_group(record: Any) -> ExistingIncidentGroup:
    return ExistingIncidentGroup(
        incident_group_id=record.incident_group_id,
        fingerprint=record.fingerprint,
        occurrence_count=int(record.occurrence_count),
        first_seen_at=record.first_seen_at,
        last_seen_at=record.last_seen_at,
    )


def compare_groups(group_payloads: list[dict[str, Any]]) -> dict[str, Any]:
    if len(group_payloads) < 2:
        return {"groups": group_payloads, "shared": {}, "differences": []}

    fingerprints = {item["incident_group_id"]: item.get("fingerprint") for item in group_payloads}
    shared_fingerprint = len(set(fingerprints.values())) == 1
    fields = ("severity", "category", "status", "occurrence_count")
    differences: list[dict[str, Any]] = []
    for field in fields:
        values = {item["incident_group_id"]: item.get(field) for item in group_payloads}
        if len(set(values.values())) > 1:
            differences.append({"field": field, "values": values})

    component_keys = ("exit_code", "log_signature", "resource_hint")
    component_maps = {item["incident_group_id"]: item.get("fingerprint_components") or {} for item in group_payloads}
    for key in component_keys:
        values = {group_id: component_maps.get(group_id, {}).get(key) for group_id in fingerprints}
        if len({value for value in values.values()}) > 1:
            differences.append({"field": key, "values": values})

    return {
        "groups": group_payloads,
        "shared": {"fingerprint": shared_fingerprint},
        "differences": differences,
    }
