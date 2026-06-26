from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete, select

from backend.adapters.persistence.models import (
    GitCommitRecord,
    GitFileChangeRecord,
    GitOperationRecord,
    GitRefRecord,
    GitRepositoryRecord,
    GitWorktreeStatusSnapshotRecord,
)
from backend.domain.shared_kernel import ProjectId, StableIdentifier
from backend.infrastructure.unit_of_work import ProjectScopeRequired, RepositoryContext


class GitRepository:
    def __init__(self, context: RepositoryContext) -> None:
        self._session = context.session
        self._project_id = context.project_id

    def upsert_repository(
        self,
        *,
        git_repository_id: StableIdentifier,
        project_id: ProjectId,
        local_path: str,
        remote_url: str | None,
        default_branch: str | None,
        repository_role: str,
        resource_id: str | None,
        scanned_at: datetime,
    ) -> GitRepositoryRecord:
        self._ensure_project_scope(project_id)
        existing = self._session.execute(
            select(GitRepositoryRecord).where(
                GitRepositoryRecord.project_id == str(project_id),
                GitRepositoryRecord.local_path == local_path,
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = GitRepositoryRecord(
                git_repository_id=str(git_repository_id),
                project_id=str(project_id),
                local_path=local_path,
                remote_url=remote_url,
                default_branch=default_branch,
                repository_role=repository_role,
                resource_id=resource_id,
                last_scanned_at=scanned_at.isoformat(),
            )
            self._session.add(existing)
            return existing
        existing.remote_url = remote_url
        existing.default_branch = default_branch
        existing.repository_role = repository_role
        existing.last_scanned_at = scanned_at.isoformat()
        return existing

    def list_repositories(self, project_id: ProjectId, role: str | None = None) -> list[GitRepositoryRecord]:
        self._ensure_project_scope(project_id)
        query = select(GitRepositoryRecord).where(GitRepositoryRecord.project_id == str(project_id))
        if role is not None:
            query = query.where(GitRepositoryRecord.repository_role == role)
        return list(self._session.execute(query.order_by(GitRepositoryRecord.local_path)).scalars())

    def get_repository(self, project_id: ProjectId, git_repository_id: StableIdentifier) -> GitRepositoryRecord | None:
        self._ensure_project_scope(project_id)
        record = self._session.get(GitRepositoryRecord, str(git_repository_id))
        if record is None or record.project_id != str(project_id):
            return None
        return record

    def replace_refs(self, *, git_repository_id: str, refs: list[dict[str, Any]], detected_at: datetime) -> None:
        self._session.execute(delete(GitRefRecord).where(GitRefRecord.git_repository_id == git_repository_id))
        for item in refs:
            self._session.add(
                GitRefRecord(
                    git_ref_id=str(StableIdentifier.new()),
                    git_repository_id=git_repository_id,
                    ref_name=item["ref_name"],
                    ref_type=item["ref_type"],
                    commit_sha=item.get("commit_sha"),
                    is_current=1 if item.get("is_current") else 0,
                    detected_at=detected_at.isoformat(),
                )
            )

    def list_refs(self, git_repository_id: str) -> list[GitRefRecord]:
        return list(
            self._session.execute(
                select(GitRefRecord).where(GitRefRecord.git_repository_id == git_repository_id).order_by(GitRefRecord.ref_name)
            ).scalars()
        )

    def upsert_commit(self, *, git_repository_id: str, commit: dict[str, Any]) -> GitCommitRecord:
        existing = self._session.execute(
            select(GitCommitRecord).where(
                GitCommitRecord.git_repository_id == git_repository_id,
                GitCommitRecord.commit_sha == commit["commit_sha"],
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        record = GitCommitRecord(
            git_commit_id=str(StableIdentifier.new()),
            git_repository_id=git_repository_id,
            commit_sha=commit["commit_sha"],
            parent_shas_json=commit.get("parent_shas"),
            author_name=commit.get("author_name"),
            author_email_hash=commit.get("author_email_hash"),
            committed_at=commit.get("committed_at"),
            message_summary=commit.get("message_summary"),
        )
        self._session.add(record)
        return record

    def add_status_snapshot(
        self,
        *,
        snapshot_id: StableIdentifier,
        git_repository_id: str,
        status: dict[str, Any],
        captured_at: datetime,
        file_changes: list[dict[str, Any]],
    ) -> GitWorktreeStatusSnapshotRecord:
        record = GitWorktreeStatusSnapshotRecord(
            git_status_snapshot_id=str(snapshot_id),
            git_repository_id=git_repository_id,
            head_commit_sha=status.get("head_commit_sha"),
            branch_name=status.get("branch_name"),
            is_dirty=1 if status.get("is_dirty") else 0,
            ahead_count=status.get("ahead_count"),
            behind_count=status.get("behind_count"),
            captured_at=captured_at.isoformat(),
            summary_json=status.get("summary") or {},
        )
        self._session.add(record)
        self._session.flush()
        for item in file_changes:
            self._session.add(
                GitFileChangeRecord(
                    git_file_change_id=str(StableIdentifier.new()),
                    git_status_snapshot_id=str(snapshot_id),
                    path=item["path"],
                    change_status=item["change_status"],
                    old_path=item.get("old_path"),
                    insertions=item.get("insertions"),
                    deletions=item.get("deletions"),
                )
            )
        return record

    def create_operation(
        self,
        *,
        operation_id: StableIdentifier,
        git_repository_id: str,
        operation_type: str,
        status: str,
        started_at: datetime,
        command_execution_id: str | None = None,
        result_json: dict[str, Any] | None = None,
    ) -> GitOperationRecord:
        record = GitOperationRecord(
            git_operation_id=str(operation_id),
            git_repository_id=git_repository_id,
            operation_type=operation_type,
            status=status,
            command_execution_id=command_execution_id,
            started_at=started_at.isoformat(),
            finished_at=None,
            result_json=result_json,
        )
        self._session.add(record)
        return record

    def finish_operation(self, operation_id: StableIdentifier, *, status: str, finished_at: datetime, result_json: dict[str, Any] | None) -> None:
        record = self._session.get(GitOperationRecord, str(operation_id))
        if record is None:
            return
        record.status = status
        record.finished_at = finished_at.isoformat()
        record.result_json = result_json

    def list_operations(self, project_id: ProjectId, git_repository_id: str | None = None) -> list[GitOperationRecord]:
        self._ensure_project_scope(project_id)
        query = (
            select(GitOperationRecord)
            .join(GitRepositoryRecord, GitOperationRecord.git_repository_id == GitRepositoryRecord.git_repository_id)
            .where(GitRepositoryRecord.project_id == str(project_id))
        )
        if git_repository_id is not None:
            query = query.where(GitOperationRecord.git_repository_id == git_repository_id)
        return list(self._session.execute(query.order_by(GitOperationRecord.started_at.desc())).scalars())

    def _ensure_project_scope(self, project_id: ProjectId) -> None:
        if self._project_id is not None and self._project_id != project_id:
            raise ProjectScopeRequired("Repository project_id does not match requested project_id")
