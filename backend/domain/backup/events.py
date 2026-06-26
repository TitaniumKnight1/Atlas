from __future__ import annotations

from backend.domain.shared_kernel import AggregateRef, DomainEventEnvelope, ProjectId


def backup_completed(project_id: ProjectId, backup_run_id: str, *, total_bytes: int, checksum: str) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="BackupCompleted",
        aggregate_ref=AggregateRef("BackupRun", backup_run_id),
        project_id=project_id,
        payload={"project_id": str(project_id), "backup_run_id": backup_run_id, "total_bytes": total_bytes, "checksum": checksum},
    )


def backup_failed(project_id: ProjectId, backup_run_id: str, reason: str) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="BackupFailed",
        aggregate_ref=AggregateRef("BackupRun", backup_run_id),
        project_id=project_id,
        payload={"project_id": str(project_id), "backup_run_id": backup_run_id, "reason": reason},
    )


def restore_completed(project_id: ProjectId, restore_run_id: str, backup_run_id: str) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="RestoreCompleted",
        aggregate_ref=AggregateRef("BackupRestoreRun", restore_run_id),
        project_id=project_id,
        payload={"project_id": str(project_id), "restore_run_id": restore_run_id, "backup_run_id": backup_run_id},
    )


def backup_pruned(project_id: ProjectId, backup_run_id: str, reason: str) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="BackupPruned",
        aggregate_ref=AggregateRef("BackupRun", backup_run_id),
        project_id=project_id,
        payload={"project_id": str(project_id), "backup_run_id": backup_run_id, "reason": reason},
    )
