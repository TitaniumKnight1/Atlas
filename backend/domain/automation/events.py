from __future__ import annotations

from backend.domain.shared_kernel import AggregateRef, DomainEventEnvelope, ProjectId


def automation_triggered(project_id: ProjectId, run_id: str, workflow_id: str, trigger_type: str) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="AutomationTriggered",
        aggregate_ref=AggregateRef("AutomationRun", run_id),
        project_id=project_id,
        payload={
            "project_id": str(project_id),
            "run_id": run_id,
            "workflow_id": workflow_id,
            "trigger_type": trigger_type,
        },
    )


def automation_run_completed(project_id: ProjectId, run_id: str, workflow_id: str) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="AutomationRunCompleted",
        aggregate_ref=AggregateRef("AutomationRun", run_id),
        project_id=project_id,
        payload={"project_id": str(project_id), "run_id": run_id, "workflow_id": workflow_id},
    )


def automation_run_failed(project_id: ProjectId, run_id: str, workflow_id: str, message: str) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="AutomationRunFailed",
        aggregate_ref=AggregateRef("AutomationRun", run_id),
        project_id=project_id,
        payload={"project_id": str(project_id), "run_id": run_id, "workflow_id": workflow_id, "message": message},
    )
