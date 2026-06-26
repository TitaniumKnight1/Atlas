from __future__ import annotations

from backend.domain.shared_kernel import AggregateRef, DomainEventEnvelope, ProjectId


def resources_scanned(project_id: ProjectId, changed_count: int) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="ResourcesScanned",
        aggregate_ref=AggregateRef("ResourceInventory", str(project_id)),
        project_id=project_id,
        payload={"project_id": str(project_id), "changed_count": changed_count},
    )


def resource_inventory_changed(project_id: ProjectId, added: int, removed: int, changed: int) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="ResourceInventoryChanged",
        aggregate_ref=AggregateRef("ResourceInventory", str(project_id)),
        project_id=project_id,
        payload={"project_id": str(project_id), "added": added, "removed": removed, "changed": changed},
    )


def dependency_issue_detected(project_id: ProjectId, finding_type: str, nodes: list[str]) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="DependencyIssueDetected",
        aggregate_ref=AggregateRef("ResourceDependencyGraph", str(project_id)),
        project_id=project_id,
        payload={"project_id": str(project_id), "finding_type": finding_type, "nodes": nodes},
    )
