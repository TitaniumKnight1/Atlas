from __future__ import annotations

from backend.domain.shared_kernel import AggregateRef, DomainEventEnvelope, ProjectId


def telemetry_preferences_updated(project_id: ProjectId | None, changed_keys: list[str]) -> DomainEventEnvelope:
    aggregate_id = str(project_id) if project_id else "global"
    return DomainEventEnvelope.create(
        event_type="TelemetryPreferencesUpdated",
        aggregate_ref=AggregateRef("TelemetryPreferences", aggregate_id),
        project_id=project_id,
        payload={"project_id": str(project_id) if project_id else None, "changed_keys": changed_keys},
    )


def telemetry_event_queued(event_id: str, subsystem: str, severity: str) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="TelemetryEventQueued",
        aggregate_ref=AggregateRef("TelemetryEvent", event_id),
        payload={"telemetry_event_id": event_id, "subsystem": subsystem, "severity": severity},
    )


def telemetry_rejected(reason: str, subsystem: str, project_id: ProjectId | None = None) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="TelemetryRejected",
        aggregate_ref=AggregateRef("TelemetryRejection", reason),
        project_id=project_id,
        payload={"reason": reason, "subsystem": subsystem, "project_id": str(project_id) if project_id else None},
    )


def telemetry_event_delivered(event_id: str, attempt_number: int) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="TelemetryEventDelivered",
        aggregate_ref=AggregateRef("TelemetryEvent", event_id),
        payload={"telemetry_event_id": event_id, "attempt_number": attempt_number},
    )
