from __future__ import annotations

from backend.domain.shared_kernel import AggregateRef, DomainEventEnvelope, ProjectId


def incident_captured(project_id: ProjectId, incident_group_id: str, occurrence_id: str, severity: str, category: str) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="IncidentCaptured",
        aggregate_ref=AggregateRef("IncidentOccurrence", occurrence_id),
        project_id=project_id,
        payload={
            "project_id": str(project_id),
            "incident_group_id": incident_group_id,
            "occurrence_id": occurrence_id,
            "severity": severity,
            "category": category,
        },
    )
