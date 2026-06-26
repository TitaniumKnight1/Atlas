from __future__ import annotations

from backend.domain.shared_kernel import AggregateRef, DomainEventEnvelope, ProjectId


def git_repository_discovered(project_id: ProjectId, git_repository_id: str, role: str) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="GitRepositoryDiscovered",
        aggregate_ref=AggregateRef("GitRepository", git_repository_id),
        project_id=project_id,
        payload={"project_id": str(project_id), "git_repository_id": git_repository_id, "repository_role": role},
    )


def git_status_snapshot_captured(project_id: ProjectId, git_repository_id: str, is_dirty: bool) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="GitStatusSnapshotCaptured",
        aggregate_ref=AggregateRef("GitRepository", git_repository_id),
        project_id=project_id,
        payload={"project_id": str(project_id), "git_repository_id": git_repository_id, "is_dirty": is_dirty},
    )


def git_operation_started(project_id: ProjectId, git_repository_id: str, operation_type: str, operation_id: str) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="GitOperationStarted",
        aggregate_ref=AggregateRef("GitOperation", operation_id),
        project_id=project_id,
        payload={
            "project_id": str(project_id),
            "git_repository_id": git_repository_id,
            "operation_type": operation_type,
            "git_operation_id": operation_id,
        },
    )


def git_operation_completed(project_id: ProjectId, git_repository_id: str, operation_type: str, status: str, operation_id: str) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="GitOperationCompleted",
        aggregate_ref=AggregateRef("GitOperation", operation_id),
        project_id=project_id,
        payload={
            "project_id": str(project_id),
            "git_repository_id": git_repository_id,
            "operation_type": operation_type,
            "status": status,
            "git_operation_id": operation_id,
        },
    )


def git_commit_created(project_id: ProjectId, git_repository_id: str, commit_sha: str) -> DomainEventEnvelope:
    return DomainEventEnvelope.create(
        event_type="GitCommitCreated",
        aggregate_ref=AggregateRef("GitCommit", commit_sha),
        project_id=project_id,
        payload={"project_id": str(project_id), "git_repository_id": git_repository_id, "commit_sha": commit_sha},
    )
