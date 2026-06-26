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


def resource_installed(project_id: ProjectId, resource_id: str, resource_name: str) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="ResourceInstalled",
        aggregate_ref=AggregateRef("Resource", resource_id),
        project_id=project_id,
        payload={"project_id": str(project_id), "resource_id": resource_id, "resource_name": resource_name},
    )


def resource_updated(project_id: ProjectId, resource_id: str, version_label: str | None) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="ResourceUpdated",
        aggregate_ref=AggregateRef("Resource", resource_id),
        project_id=project_id,
        payload={"project_id": str(project_id), "resource_id": resource_id, "version_label": version_label},
    )


def resource_enabled_state_changed(project_id: ProjectId, resource_id: str, enabled_state: str) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="ResourceEnabledStateChanged",
        aggregate_ref=AggregateRef("Resource", resource_id),
        project_id=project_id,
        payload={"project_id": str(project_id), "resource_id": resource_id, "enabled_state": enabled_state},
    )


def resource_deleted(project_id: ProjectId, resource_id: str, resource_name: str) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="ResourceDeleted",
        aggregate_ref=AggregateRef("Resource", resource_id),
        project_id=project_id,
        payload={"project_id": str(project_id), "resource_id": resource_id, "resource_name": resource_name},
    )


def resource_rolled_back(project_id: ProjectId, resource_id: str, resource_name: str, rollback_run_id: str) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="ResourceRolledBack",
        aggregate_ref=AggregateRef("ResourceRollbackRun", rollback_run_id),
        project_id=project_id,
        payload={
            "project_id": str(project_id),
            "resource_id": resource_id,
            "resource_name": resource_name,
            "rollback_run_id": rollback_run_id,
        },
    )


def resource_rollback_failed(
    project_id: ProjectId, resource_id: str, resource_name: str, rollback_run_id: str, error: str
) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="ResourceRollbackFailed",
        aggregate_ref=AggregateRef("ResourceRollbackRun", rollback_run_id),
        project_id=project_id,
        payload={
            "project_id": str(project_id),
            "resource_id": resource_id,
            "resource_name": resource_name,
            "rollback_run_id": rollback_run_id,
            "error": error,
        },
    )


def rollback_batch_completed(project_id: ProjectId, rollback_run_id: str, succeeded_count: int) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="RollbackBatchCompleted",
        aggregate_ref=AggregateRef("ResourceRollbackRun", rollback_run_id),
        project_id=project_id,
        payload={"project_id": str(project_id), "rollback_run_id": rollback_run_id, "succeeded_count": succeeded_count},
    )


def rollback_batch_halted(project_id: ProjectId, rollback_run_id: str, failed_resource_name: str) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="RollbackBatchHalted",
        aggregate_ref=AggregateRef("ResourceRollbackRun", rollback_run_id),
        project_id=project_id,
        payload={
            "project_id": str(project_id),
            "rollback_run_id": rollback_run_id,
            "failed_resource_name": failed_resource_name,
        },
    )
