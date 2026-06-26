from __future__ import annotations

from backend.domain.shared_kernel import AggregateRef, DomainEventEnvelope, ProjectId


def project_imported(project_id: ProjectId, paths: list[dict[str, object]]) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="ProjectImported",
        aggregate_ref=AggregateRef("Project", str(project_id)),
        project_id=project_id,
        payload={"project_id": str(project_id), "paths": paths, "detected_features": []},
    )


def project_opened(project_id: ProjectId) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="ProjectOpened",
        aggregate_ref=AggregateRef("Project", str(project_id)),
        project_id=project_id,
        payload={"project_id": str(project_id)},
    )


def project_settings_updated(project_id: ProjectId, changed_keys: list[str]) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="ProjectSettingsUpdated",
        aggregate_ref=AggregateRef("Project", str(project_id)),
        project_id=project_id,
        payload={"project_id": str(project_id), "changed_keys": changed_keys},
    )


def environment_profile_created(project_id: ProjectId, environment_id: str, name: str) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="EnvironmentProfileCreated",
        aggregate_ref=AggregateRef("EnvironmentProfile", environment_id),
        project_id=project_id,
        payload={"project_id": str(project_id), "environment_id": environment_id, "name": name},
    )


def environment_profile_updated(project_id: ProjectId, environment_id: str) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="EnvironmentProfileUpdated",
        aggregate_ref=AggregateRef("EnvironmentProfile", environment_id),
        project_id=project_id,
        payload={"project_id": str(project_id), "environment_id": environment_id},
    )


def workspace_trust_changed(project_id: ProjectId, scope: str, trust_state: str) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="WorkspaceTrustChanged",
        aggregate_ref=AggregateRef("Project", str(project_id)),
        project_id=project_id,
        payload={"project_id": str(project_id), "scope": scope, "trust_state": trust_state},
    )


def project_archived(project_id: ProjectId, reason: str) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="ProjectArchived",
        aggregate_ref=AggregateRef("Project", str(project_id)),
        project_id=project_id,
        payload={"project_id": str(project_id), "reason": reason},
    )
