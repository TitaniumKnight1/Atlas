from __future__ import annotations

from backend.domain.shared_kernel.events import AggregateRef, DomainEventEnvelope
from backend.domain.shared_kernel.identifiers import ProjectId


def config_inventory_changed(project_id: ProjectId, changed_count: int) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="ConfigInventoryChanged",
        aggregate_ref=AggregateRef("ConfigInventory", str(project_id)),
        project_id=project_id,
        payload={"project_id": str(project_id), "changed_count": changed_count},
    )


def config_change_planned(project_id: ProjectId, config_file_id: str, risk: str) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="ConfigChangePlanned",
        aggregate_ref=AggregateRef("ConfigFile", config_file_id),
        project_id=project_id,
        payload={"project_id": str(project_id), "config_file_id": config_file_id, "risk": risk},
    )


def config_changed(project_id: ProjectId, change_set_id: str, config_file_id: str) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="ConfigChanged",
        aggregate_ref=AggregateRef("ConfigChangeSet", change_set_id),
        project_id=project_id,
        payload={"project_id": str(project_id), "config_change_set_id": change_set_id, "config_file_id": config_file_id},
    )


def config_validation_failed(project_id: ProjectId, validator_id: str, severity: str) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="ConfigValidationFailed",
        aggregate_ref=AggregateRef("ConfigValidation", validator_id),
        project_id=project_id,
        payload={"project_id": str(project_id), "validator_id": validator_id, "severity": severity},
    )


def secret_scan_finding_detected(project_id: ProjectId, secret_finding_id: str, severity: str, secret_type: str) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="SecretScanFindingDetected",
        aggregate_ref=AggregateRef("SecretScanFinding", secret_finding_id),
        project_id=project_id,
        payload={"project_id": str(project_id), "secret_finding_id": secret_finding_id, "severity": severity, "secret_type": secret_type},
    )
