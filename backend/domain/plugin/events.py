from __future__ import annotations

from backend.domain.shared_kernel import AggregateRef, DomainEventEnvelope, ProjectId


def plugin_registered(plugin_id: str, *, version: str) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="PluginRegistered",
        aggregate_ref=AggregateRef("Plugin", plugin_id),
        project_id=None,
        payload={"plugin_id": plugin_id, "version": version},
    )


def capability_granted(plugin_id: str, *, capability: str, project_id: ProjectId | None) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="PluginCapabilityGranted",
        aggregate_ref=AggregateRef("Plugin", plugin_id),
        project_id=project_id,
        payload={"plugin_id": plugin_id, "capability": capability, "project_id": str(project_id) if project_id else None},
    )


def capability_revoked(plugin_id: str, *, capability: str, project_id: ProjectId | None) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="PluginCapabilityRevoked",
        aggregate_ref=AggregateRef("Plugin", plugin_id),
        project_id=project_id,
        payload={"plugin_id": plugin_id, "capability": capability, "project_id": str(project_id) if project_id else None},
    )


def plugin_disabled(plugin_id: str, *, reason: str | None = None) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="PluginDisabled",
        aggregate_ref=AggregateRef("Plugin", plugin_id),
        project_id=None,
        payload={"plugin_id": plugin_id, "reason": reason},
    )
