from __future__ import annotations

from backend.domain.shared_kernel import AggregateRef, DomainEventEnvelope, ProjectId


def automation_approval_requested(
    project_id: ProjectId, run_id: str, approval_id: str, preview: dict
) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="AutomationApprovalRequested",
        aggregate_ref=AggregateRef("AutomationApproval", approval_id),
        project_id=project_id,
        payload={"project_id": str(project_id), "run_id": run_id, "approval_id": approval_id, "preview": preview},
    )


def automation_approval_granted(project_id: ProjectId, run_id: str, approval_id: str) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="AutomationApprovalGranted",
        aggregate_ref=AggregateRef("AutomationApproval", approval_id),
        project_id=project_id,
        payload={"project_id": str(project_id), "run_id": run_id, "approval_id": approval_id},
    )


def automation_approval_rejected(project_id: ProjectId, run_id: str, approval_id: str, reason: str) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="AutomationApprovalRejected",
        aggregate_ref=AggregateRef("AutomationApproval", approval_id),
        project_id=project_id,
        payload={"project_id": str(project_id), "run_id": run_id, "approval_id": approval_id, "reason": reason},
    )


def recipe_run_halted(project_id: ProjectId, run_id: str, *, failed_step: int, message: str) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="RecipeRunHalted",
        aggregate_ref=AggregateRef("AutomationRun", run_id),
        project_id=project_id,
        payload={"project_id": str(project_id), "run_id": run_id, "failed_step": failed_step, "message": message},
    )


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
