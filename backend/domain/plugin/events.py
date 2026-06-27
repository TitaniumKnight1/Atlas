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


def plugin_started(plugin_id: str, *, runtime_id: str, project_id: ProjectId, pid: int) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="PluginStarted",
        aggregate_ref=AggregateRef("PluginRuntime", runtime_id),
        project_id=project_id,
        payload={"plugin_id": plugin_id, "runtime_id": runtime_id, "project_id": str(project_id), "pid": pid},
    )


def plugin_stopped(plugin_id: str, *, runtime_id: str, project_id: ProjectId) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="PluginStopped",
        aggregate_ref=AggregateRef("PluginRuntime", runtime_id),
        project_id=project_id,
        payload={"plugin_id": plugin_id, "runtime_id": runtime_id, "project_id": str(project_id)},
    )


def plugin_capability_call_denied(plugin_id: str, *, capability: str, project_id: ProjectId, reason: str) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="PluginCapabilityCallDenied",
        aggregate_ref=AggregateRef("Plugin", plugin_id),
        project_id=project_id,
        payload={"plugin_id": plugin_id, "capability": capability, "project_id": str(project_id), "reason": reason},
    )


def plugin_failed(plugin_id: str, *, runtime_id: str, project_id: ProjectId, summary: str) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="PluginFailed",
        aggregate_ref=AggregateRef("PluginRuntime", runtime_id),
        project_id=project_id,
        payload={"plugin_id": plugin_id, "runtime_id": runtime_id, "project_id": str(project_id), "summary": summary},
    )


def plugin_contribution_registered(
    plugin_id: str,
    *,
    contribution_id: str,
    contribution_point: str,
    identifier: str,
    project_id: ProjectId,
) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="PluginContributionRegistered",
        aggregate_ref=AggregateRef("PluginContribution", contribution_id),
        project_id=project_id,
        payload={
            "plugin_id": plugin_id,
            "contribution_id": contribution_id,
            "contribution_point": contribution_point,
            "identifier": identifier,
            "project_id": str(project_id),
        },
    )


def plugin_contribution_invoked(
    plugin_id: str,
    *,
    contribution_id: str,
    contribution_point: str,
    project_id: ProjectId,
) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="PluginContributionInvoked",
        aggregate_ref=AggregateRef("PluginContribution", contribution_id),
        project_id=project_id,
        payload={
            "plugin_id": plugin_id,
            "contribution_id": contribution_id,
            "contribution_point": contribution_point,
            "project_id": str(project_id),
        },
    )


def plugin_contribution_failed(
    plugin_id: str,
    *,
    contribution_id: str,
    contribution_point: str,
    project_id: ProjectId,
    reason: str,
) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="PluginContributionFailed",
        aggregate_ref=AggregateRef("PluginContribution", contribution_id),
        project_id=project_id,
        payload={
            "plugin_id": plugin_id,
            "contribution_id": contribution_id,
            "contribution_point": contribution_point,
            "project_id": str(project_id),
            "reason": reason,
        },
    )
