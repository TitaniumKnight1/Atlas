from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import os
import stat
import time

from sqlalchemy import select

from backend.adapters.git import GitPythonProvider, redact_remote_url, sanitize_git_payload
from backend.adapters.persistence import GitRepository, ProjectRepository
from backend.adapters.persistence.models import ProjectPathRecord
from backend.application.commands import CommandContext, CommandExecutionResult, CommandPreview, DryRunResult, RiskLevel, UndoPlan
from backend.application.commands.recorder import CommandAuditRecorder
from backend.domain.git import (
    GitOperationType,
    GitProviderPort,
    RepositoryRole,
    git_commit_created,
    git_operation_completed,
    git_operation_started,
    git_repository_discovered,
    git_status_snapshot_captured,
)
from backend.domain.shared_kernel import ErrorCode, ProjectId, StableIdentifier
from backend.infrastructure.unit_of_work import RepositoryContext


class GitApplicationError(RuntimeError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class RemoveClonedRepositoryCompensation:
    local_path: str
    action_type: str = "remove_cloned_repository"

    def describe(self) -> dict[str, Any]:
        return {"action_type": self.action_type, "local_path": self.local_path}

    def apply(self, context: CommandContext) -> dict[str, Any]:
        import gc

        gc.collect()
        path = Path(self.local_path)
        if path.exists():
            _remove_tree(path)
        return {"removed_path": str(path)}


@dataclass(frozen=True, slots=True)
class RevertGitCommitCompensation:
    repo_path: str
    parent_sha: str
    provider: GitProviderPort
    action_type: str = "revert_git_commit"

    def describe(self) -> dict[str, Any]:
        return {"action_type": self.action_type, "repo_path": self.repo_path, "parent_sha": self.parent_sha}

    def apply(self, context: CommandContext) -> dict[str, Any]:
        self.provider.reset_soft(repo_path=Path(self.repo_path), commit_sha=self.parent_sha)
        return {"repo_path": self.repo_path, "reset_to": self.parent_sha}


@dataclass(frozen=True, slots=True)
class RestoreGitCheckoutCompensation:
    repo_path: str
    prior_ref: str
    provider: GitProviderPort
    action_type: str = "restore_git_checkout"

    def describe(self) -> dict[str, Any]:
        return {"action_type": self.action_type, "repo_path": self.repo_path, "prior_ref": self.prior_ref}

    def apply(self, context: CommandContext) -> dict[str, Any]:
        self.provider.checkout(repo_path=Path(self.repo_path), ref_name=self.prior_ref)
        return {"repo_path": self.repo_path, "restored_ref": self.prior_ref}


class GitApplicationService:
    def __init__(self, *, container: Any, provider: GitProviderPort, stream_publisher: Any | None = None) -> None:
        self._container = container
        self._provider = provider
        self._stream_publisher = stream_publisher
        self._recorder = CommandAuditRecorder()

    def execute_discover_git_repositories(self, *, project_id: ProjectId, path_filters: list[str] | None = None) -> dict[str, Any]:
        now = datetime.now(UTC)
        roots = [Path(item) for item in (path_filters or self._project_roots(project_id))]
        discovered = self._provider.discover_repositories(roots)
        changed = 0
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            self._require_project(uow.repository(ProjectRepository), project_id)
            repository = uow.repository(GitRepository)
            for item in discovered:
                repo_id = StableIdentifier.new()
                existing = repository.upsert_repository(
                    git_repository_id=repo_id,
                    project_id=project_id,
                    local_path=item["local_path"],
                    remote_url=redact_remote_url(item.get("remote_url")),
                    default_branch=item.get("default_branch"),
                    repository_role=RepositoryRole.PROJECT.value,
                    resource_id=None,
                    scanned_at=now,
                )
                uow.session.flush()
                refs = self._provider.list_refs(repo_path=Path(existing.local_path))
                repository.replace_refs(
                    git_repository_id=existing.git_repository_id,
                    refs=[_ref_data(ref) for ref in refs],
                    detected_at=now,
                )
                uow.collect_event(git_repository_discovered(project_id, existing.git_repository_id, existing.repository_role))
                changed += 1
            uow.commit()
        return {"project_id": str(project_id), "changed_count": changed, "repositories": [_repo_data(item) for item in discovered]}

    def list_git_repositories(self, project_id: ProjectId, role: str | None = None) -> list[dict[str, Any]]:
        with self._container.session_factory() as session:
            records = GitRepository(RepositoryContext(session=session, project_id=project_id)).list_repositories(project_id, role)
            return [_repository_record_data(record) for record in records]

    def get_git_repository(self, project_id: ProjectId, git_repository_id: str) -> dict[str, Any]:
        record = self._get_repository(project_id, git_repository_id)
        return _repository_record_data(record)

    def preview_clone_repository(
        self,
        *,
        project_id: ProjectId,
        remote_url: str,
        destination_path: str,
        repository_role: str = RepositoryRole.RESOURCE.value,
    ) -> CommandPreview:
        destination = Path(destination_path).expanduser().resolve()
        warnings: list[str] = []
        if destination.exists():
            warnings.append("Destination path already exists; clone may fail unless empty.")
        return CommandPreview(
            "CloneRepository",
            f"Clone repository into {destination}",
            sanitize_git_payload(
                {
                    "project_id": str(project_id),
                    "remote_url": remote_url,
                    "redacted_remote_url": redact_remote_url(remote_url),
                    "destination_path": str(destination),
                    "repository_role": repository_role,
                    "reversible": True,
                    "compensation": "remove_cloned_directory",
                }
            ),
            warnings=warnings,
            risk_level=RiskLevel.HIGH,
        )

    def execute_clone_repository(
        self,
        *,
        project_id: ProjectId,
        remote_url: str,
        destination_path: str,
        repository_role: str = RepositoryRole.RESOURCE.value,
        idempotency_key: str | None = None,
    ) -> CommandExecutionResult:
        preview = self.preview_clone_repository(
            project_id=project_id,
            remote_url=remote_url,
            destination_path=destination_path,
            repository_role=repository_role,
        )
        destination = Path(destination_path).expanduser().resolve()
        operation_id = StableIdentifier.new()
        repo_id = StableIdentifier.new()
        now = datetime.now(UTC)
        compensation = RemoveClonedRepositoryCompensation(str(destination))

        def progress(update: dict[str, Any]) -> None:
            self._publish_progress(project_id, str(operation_id), update.get("message", "Cloning"), update.get("bytes_received"), update.get("total_bytes"))

        self._publish_progress(project_id, str(operation_id), "Starting clone", 0, None)
        self._provider.clone(remote_url=remote_url, destination=destination, progress=progress)
        self._publish_progress(project_id, str(operation_id), "Clone complete", None, None)
        refs = self._provider.list_refs(repo_path=destination)
        default_branch = next((ref.ref_name for ref in refs if ref.is_current), None)
        result = sanitize_git_payload(
            {
                "project_id": str(project_id),
                "git_repository_id": str(repo_id),
                "local_path": str(destination),
                "remote_url": redact_remote_url(remote_url),
                "default_branch": default_branch,
                "git_operation_id": str(operation_id),
            }
        )
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(GitRepository)
            record = repository.upsert_repository(
                git_repository_id=repo_id,
                project_id=project_id,
                local_path=str(destination),
                remote_url=redact_remote_url(remote_url),
                default_branch=default_branch,
                repository_role=repository_role,
                resource_id=None,
                scanned_at=now,
            )
            uow.session.flush()
            repository.replace_refs(git_repository_id=record.git_repository_id, refs=[_ref_data(ref) for ref in refs], detected_at=now)
            events = [
                git_operation_started(project_id, record.git_repository_id, GitOperationType.CLONE.value, str(operation_id)),
                git_repository_discovered(project_id, record.git_repository_id, repository_role),
            ]
            execution = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="GitRepository",
                entity_id=record.git_repository_id,
                summary=f"Cloned repository to {destination}",
                result=result,
                events=events,
                undo_plan=UndoPlan(
                    "UndoCloneRepository",
                    f"Remove cloned repository at {destination}",
                    compensation,
                    {**compensation.describe(), "project_id": str(project_id)},
                ),
                idempotency_key=idempotency_key,
            )
            repository.create_operation(
                operation_id=operation_id,
                git_repository_id=record.git_repository_id,
                operation_type=GitOperationType.CLONE.value,
                status="succeeded",
                started_at=now,
                command_execution_id=str(execution.command_execution_id),
                result_json=result,
            )
            repository.finish_operation(operation_id, status="succeeded", finished_at=datetime.now(UTC), result_json=result)
            uow.collect_event(git_operation_completed(project_id, record.git_repository_id, GitOperationType.CLONE.value, "succeeded", str(operation_id)))
            uow.commit()
            return execution

    def preview_fetch_repository(self, *, project_id: ProjectId, git_repository_id: str) -> CommandPreview:
        record = self._get_repository(project_id, git_repository_id)
        return CommandPreview(
            "FetchRepository",
            f"Fetch remote refs for {record.local_path}",
            {
                "project_id": str(project_id),
                "git_repository_id": git_repository_id,
                "local_path": record.local_path,
                "reversible": False,
                "note": "Fetch updates remote-tracking refs only; no working-tree undo.",
            },
            risk_level=RiskLevel.MEDIUM,
        )

    def execute_fetch_repository(self, *, project_id: ProjectId, git_repository_id: str, idempotency_key: str | None = None) -> CommandExecutionResult:
        preview = self.preview_fetch_repository(project_id=project_id, git_repository_id=git_repository_id)
        record = self._get_repository(project_id, git_repository_id)
        operation_id = StableIdentifier.new()
        now = datetime.now(UTC)

        def progress(update: dict[str, Any]) -> None:
            self._publish_progress(project_id, str(operation_id), update.get("message", "Fetching"), update.get("bytes_received"), update.get("total_bytes"))

        fetch_result = self._provider.fetch(repo_path=Path(record.local_path), progress=progress)
        refs = self._provider.list_refs(repo_path=Path(record.local_path))
        result = sanitize_git_payload({"git_operation_id": str(operation_id), **fetch_result})
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(GitRepository)
            repository.replace_refs(git_repository_id=record.git_repository_id, refs=[_ref_data(ref) for ref in refs], detected_at=now)
            uow.session.flush()
            events = [
                git_operation_started(project_id, record.git_repository_id, GitOperationType.FETCH.value, str(operation_id)),
            ]
            execution = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="GitOperation",
                entity_id=str(operation_id),
                summary="Fetched remote refs",
                result=result,
                events=events,
                undo_plan=None,
                idempotency_key=idempotency_key,
            )
            repository.create_operation(
                operation_id=operation_id,
                git_repository_id=record.git_repository_id,
                operation_type=GitOperationType.FETCH.value,
                status="succeeded",
                started_at=now,
                command_execution_id=str(execution.command_execution_id),
                result_json=result,
            )
            repository.finish_operation(operation_id, status="succeeded", finished_at=datetime.now(UTC), result_json=result)
            uow.collect_event(git_operation_completed(project_id, record.git_repository_id, GitOperationType.FETCH.value, "succeeded", str(operation_id)))
            uow.commit()
            return execution

    def preview_pull_repository(self, *, project_id: ProjectId, git_repository_id: str) -> CommandPreview:
        record = self._get_repository(project_id, git_repository_id)
        status = self._provider.status(repo_path=Path(record.local_path))
        warnings: list[str] = []
        risk = RiskLevel.MEDIUM
        reversible = True
        if status.is_dirty:
            warnings.append("Working tree has local modifications; pull may merge or conflict and cannot be cleanly undone.")
            risk = RiskLevel.HIGH
            reversible = False
        return CommandPreview(
            "PullRepository",
            f"Pull updates for {record.local_path}",
            {
                "project_id": str(project_id),
                "git_repository_id": git_repository_id,
                "is_dirty": status.is_dirty,
                "head_commit_sha": status.head_commit_sha,
                "reversible": reversible,
            },
            warnings=warnings,
            risk_level=risk,
        )

    def execute_pull_repository(self, *, project_id: ProjectId, git_repository_id: str, idempotency_key: str | None = None) -> CommandExecutionResult:
        preview = self.preview_pull_repository(project_id=project_id, git_repository_id=git_repository_id)
        record = self._get_repository(project_id, git_repository_id)
        prior_head = self._provider.status(repo_path=Path(record.local_path)).head_commit_sha
        operation_id = StableIdentifier.new()
        now = datetime.now(UTC)

        def progress(update: dict[str, Any]) -> None:
            self._publish_progress(project_id, str(operation_id), update.get("message", "Pulling"), update.get("bytes_received"), update.get("total_bytes"))

        pull_result = self._provider.pull(repo_path=Path(record.local_path), progress=progress)
        result = sanitize_git_payload({"git_operation_id": str(operation_id), "prior_head_sha": prior_head, **pull_result})
        undo_plan = None
        if preview.preview.get("reversible") and prior_head:
            undo_plan = UndoPlan(
                "UndoPullRepository",
                "Reset to prior HEAD before pull",
                RevertGitCommitCompensation(record.local_path, prior_head, self._provider),
                {"project_id": str(project_id), "git_repository_id": git_repository_id, "parent_sha": prior_head},
            )
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(GitRepository)
            events = [
                git_operation_started(project_id, record.git_repository_id, GitOperationType.PULL.value, str(operation_id)),
            ]
            execution = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="GitOperation",
                entity_id=str(operation_id),
                summary="Pulled repository updates",
                result=result,
                events=events,
                undo_plan=undo_plan,
                idempotency_key=idempotency_key,
            )
            repository.create_operation(
                operation_id=operation_id,
                git_repository_id=record.git_repository_id,
                operation_type=GitOperationType.PULL.value,
                status="succeeded",
                started_at=now,
                command_execution_id=str(execution.command_execution_id),
                result_json=result,
            )
            repository.finish_operation(operation_id, status="succeeded", finished_at=datetime.now(UTC), result_json=result)
            uow.collect_event(git_operation_completed(project_id, record.git_repository_id, GitOperationType.PULL.value, "succeeded", str(operation_id)))
            uow.commit()
            return execution

    def list_refs(self, project_id: ProjectId, git_repository_id: str) -> list[dict[str, Any]]:
        record = self._get_repository(project_id, git_repository_id)
        refs = self._provider.list_refs(repo_path=Path(record.local_path))
        return [_ref_data(ref) for ref in refs]

    def preview_create_branch(self, *, project_id: ProjectId, git_repository_id: str, branch_name: str) -> CommandPreview:
        return CommandPreview(
            "CreateBranch",
            f"Create branch {branch_name}",
            {"project_id": str(project_id), "git_repository_id": git_repository_id, "branch_name": branch_name, "reversible": True},
            risk_level=RiskLevel.LOW,
        )

    def execute_create_branch(
        self,
        *,
        project_id: ProjectId,
        git_repository_id: str,
        branch_name: str,
        idempotency_key: str | None = None,
    ) -> CommandExecutionResult:
        preview = self.preview_create_branch(project_id=project_id, git_repository_id=git_repository_id, branch_name=branch_name)
        record = self._get_repository(project_id, git_repository_id)
        ref = self._provider.create_branch(repo_path=Path(record.local_path), branch_name=branch_name)
        result = {"branch_name": ref.ref_name, "commit_sha": ref.commit_sha}
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            uow.repository(GitRepository).replace_refs(
                git_repository_id=record.git_repository_id,
                refs=[_ref_data(item) for item in self._provider.list_refs(repo_path=Path(record.local_path))],
                detected_at=datetime.now(UTC),
            )
            execution = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="GitRef",
                entity_id=branch_name,
                summary=f"Created branch {branch_name}",
                result=result,
                events=[],
                undo_plan=None,
                idempotency_key=idempotency_key,
            )
            uow.commit()
            return execution

    def preview_checkout_ref(self, *, project_id: ProjectId, git_repository_id: str, ref_name: str) -> CommandPreview:
        record = self._get_repository(project_id, git_repository_id)
        status = self._provider.status(repo_path=Path(record.local_path))
        warnings = []
        if status.is_dirty:
            warnings.append("Working tree is dirty; checkout may fail or overwrite uncommitted changes.")
        return CommandPreview(
            "CheckoutRef",
            f"Checkout {ref_name}",
            {"project_id": str(project_id), "git_repository_id": git_repository_id, "ref_name": ref_name, "reversible": True},
            warnings=warnings,
            risk_level=RiskLevel.MEDIUM,
        )

    def execute_checkout_ref(
        self,
        *,
        project_id: ProjectId,
        git_repository_id: str,
        ref_name: str,
        idempotency_key: str | None = None,
    ) -> CommandExecutionResult:
        preview = self.preview_checkout_ref(project_id=project_id, git_repository_id=git_repository_id, ref_name=ref_name)
        record = self._get_repository(project_id, git_repository_id)
        prior = self._provider.status(repo_path=Path(record.local_path)).branch_name or "HEAD"
        checkout = self._provider.checkout(repo_path=Path(record.local_path), ref_name=ref_name)
        compensation = RestoreGitCheckoutCompensation(record.local_path, prior, self._provider)
        result = sanitize_git_payload(checkout)
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            execution = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="GitRepository",
                entity_id=record.git_repository_id,
                summary=f"Checked out {ref_name}",
                result=result,
                events=[],
                undo_plan=UndoPlan(
                    "UndoCheckoutRef",
                    f"Restore checkout to {prior}",
                    compensation,
                    {**compensation.describe(), "project_id": str(project_id), "git_repository_id": git_repository_id},
                ),
                idempotency_key=idempotency_key,
            )
            uow.commit()
            return execution

    def preview_delete_branch(self, *, project_id: ProjectId, git_repository_id: str, branch_name: str) -> CommandPreview:
        return CommandPreview(
            "DeleteBranch",
            f"Delete branch {branch_name}",
            {
                "project_id": str(project_id),
                "git_repository_id": git_repository_id,
                "branch_name": branch_name,
                "reversible": False,
                "warning": "Deleted branches with unique commits cannot be restored.",
            },
            warnings=["Branch deletion may be irreversible if commits are not reachable from other refs."],
            risk_level=RiskLevel.HIGH,
        )

    def execute_delete_branch(
        self,
        *,
        project_id: ProjectId,
        git_repository_id: str,
        branch_name: str,
        idempotency_key: str | None = None,
    ) -> CommandExecutionResult:
        preview = self.preview_delete_branch(project_id=project_id, git_repository_id=git_repository_id, branch_name=branch_name)
        record = self._get_repository(project_id, git_repository_id)
        self._provider.delete_branch(repo_path=Path(record.local_path), branch_name=branch_name)
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            uow.repository(GitRepository).replace_refs(
                git_repository_id=record.git_repository_id,
                refs=[_ref_data(item) for item in self._provider.list_refs(repo_path=Path(record.local_path))],
                detected_at=datetime.now(UTC),
            )
            execution = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="GitRef",
                entity_id=branch_name,
                summary=f"Deleted branch {branch_name}",
                result={"branch_name": branch_name},
                events=[],
                undo_plan=None,
                idempotency_key=idempotency_key,
            )
            uow.commit()
            return execution

    def preview_create_commit(self, *, project_id: ProjectId, git_repository_id: str, message: str, paths: list[str] | None = None) -> CommandPreview:
        return CommandPreview(
            "CreateCommit",
            "Create local commit",
            {"project_id": str(project_id), "git_repository_id": git_repository_id, "message": message, "paths": paths, "reversible": True},
            risk_level=RiskLevel.MEDIUM,
        )

    def execute_create_commit(
        self,
        *,
        project_id: ProjectId,
        git_repository_id: str,
        message: str,
        paths: list[str] | None = None,
        idempotency_key: str | None = None,
    ) -> CommandExecutionResult:
        preview = self.preview_create_commit(project_id=project_id, git_repository_id=git_repository_id, message=message, paths=paths)
        record = self._get_repository(project_id, git_repository_id)
        prior_head = self._provider.status(repo_path=Path(record.local_path)).head_commit_sha
        commit = self._provider.commit(repo_path=Path(record.local_path), message=message, paths=paths)
        parent_sha = commit.parent_shas[0] if commit.parent_shas else prior_head
        compensation = RevertGitCommitCompensation(record.local_path, parent_sha or "", self._provider) if parent_sha else None
        result = sanitize_git_payload(
            {
                "commit_sha": commit.commit_sha,
                "message_summary": commit.message_summary,
                "parent_sha": parent_sha,
            }
        )
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(GitRepository)
            repository.upsert_commit(
                git_repository_id=record.git_repository_id,
                commit={
                    "commit_sha": commit.commit_sha,
                    "parent_shas": commit.parent_shas,
                    "author_name": commit.author_name,
                    "committed_at": commit.committed_at,
                    "message_summary": commit.message_summary,
                },
            )
            undo_plan = None
            if compensation is not None:
                undo_plan = UndoPlan(
                    "UndoCreateCommit",
                    "Soft-reset to parent commit",
                    compensation,
                    {**compensation.describe(), "project_id": str(project_id), "git_repository_id": git_repository_id},
                )
            execution = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="GitCommit",
                entity_id=commit.commit_sha,
                summary="Created commit",
                result=result,
                events=[git_commit_created(project_id, record.git_repository_id, commit.commit_sha)],
                undo_plan=undo_plan,
                idempotency_key=idempotency_key,
            )
            uow.commit()
            return execution

    def get_worktree_status(self, project_id: ProjectId, git_repository_id: str) -> dict[str, Any]:
        record = self._get_repository(project_id, git_repository_id)
        status = self._provider.status(repo_path=Path(record.local_path))
        return _status_data(status)

    def execute_capture_git_status_snapshot(self, *, project_id: ProjectId, git_repository_id: str) -> dict[str, Any]:
        record = self._get_repository(project_id, git_repository_id)
        status = self._provider.status(repo_path=Path(record.local_path))
        snapshot_id = StableIdentifier.new()
        now = datetime.now(UTC)
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            uow.repository(GitRepository).add_status_snapshot(
                snapshot_id=snapshot_id,
                git_repository_id=record.git_repository_id,
                status=_status_data(status),
                captured_at=now,
                file_changes=[_file_change_data(item) for item in status.file_changes],
            )
            uow.collect_event(git_status_snapshot_captured(project_id, record.git_repository_id, status.is_dirty))
            uow.commit()
        return {"git_status_snapshot_id": str(snapshot_id), "status": _status_data(status)}

    def get_diff_summary(
        self,
        project_id: ProjectId,
        git_repository_id: str,
        base_ref: str,
        head_ref: str,
        path_filter: str | None = None,
    ) -> dict[str, Any]:
        record = self._get_repository(project_id, git_repository_id)
        diff = self._provider.diff_summary(repo_path=Path(record.local_path), base_ref=base_ref, head_ref=head_ref, path_filter=path_filter)
        return {
            "base_ref": diff.base_ref,
            "head_ref": diff.head_ref,
            "files": [_file_change_data(item) for item in diff.files],
            "patch_stats": diff.patch_stats,
        }

    def compare_commits(self, project_id: ProjectId, git_repository_id: str, base_ref: str, head_ref: str, limit: int = 20) -> list[dict[str, Any]]:
        record = self._get_repository(project_id, git_repository_id)
        commits = self._provider.compare_commits(repo_path=Path(record.local_path), base_ref=base_ref, head_ref=head_ref, limit=limit)
        return [_commit_data(item) for item in commits]

    def list_git_operations(self, project_id: ProjectId, git_repository_id: str | None = None) -> list[dict[str, Any]]:
        with self._container.session_factory() as session:
            records = GitRepository(RepositoryContext(session=session, project_id=project_id)).list_operations(project_id, git_repository_id)
            return [_operation_data(record) for record in records]

    def undo(self, undo_plan: UndoPlan) -> CommandExecutionResult:
        project_id_value = undo_plan.payload.get("project_id")
        project_id = ProjectId(str(project_id_value)) if project_id_value else None
        preview = CommandPreview(undo_plan.command_type, undo_plan.summary, {"undo": undo_plan.payload}, risk_level=RiskLevel.HIGH)
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            action_result = undo_plan.action.apply(CommandContext(uow=uow))
            execution = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="GitUndo",
                entity_id=str(project_id) if project_id else "global",
                summary=undo_plan.summary,
                result=sanitize_git_payload(action_result),
                events=[],
                undo_plan=None,
            )
            uow.commit()
            return execution

    def _publish_progress(
        self,
        project_id: ProjectId,
        operation_id: str,
        message: str,
        bytes_received: int | None,
        total_bytes: int | None,
    ) -> None:
        if self._stream_publisher is None:
            return
        self._stream_publisher.publish_operation_progress(
            project_id=project_id,
            operation_id=operation_id,
            message=message,
            bytes_received=bytes_received,
            total_bytes=total_bytes,
        )

    def _project_roots(self, project_id: ProjectId) -> list[str]:
        with self._container.session_factory() as session:
            paths = session.execute(select(ProjectPathRecord).where(ProjectPathRecord.project_id == str(project_id))).scalars()
            return [record.absolute_path for record in paths if record.path_role == "root"]

    def _get_repository(self, project_id: ProjectId, git_repository_id: str):
        with self._container.session_factory() as session:
            record = GitRepository(RepositoryContext(session=session, project_id=project_id)).get_repository(project_id, StableIdentifier(git_repository_id))
            if record is None:
                raise GitApplicationError(ErrorCode.NOT_FOUND, f"Git repository not found: {git_repository_id}")
            return record

    def _require_project(self, repository: ProjectRepository, project_id: ProjectId) -> None:
        if repository.get_project(project_id) is None:
            raise GitApplicationError(ErrorCode.NOT_FOUND, f"Project not found: {project_id}")


def _repository_record_data(record: Any) -> dict[str, Any]:
    return {
        "git_repository_id": record.git_repository_id,
        "project_id": record.project_id,
        "local_path": record.local_path,
        "remote_url": record.remote_url,
        "default_branch": record.default_branch,
        "repository_role": record.repository_role,
        "last_scanned_at": record.last_scanned_at,
    }


def _repo_data(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "local_path": item["local_path"],
        "remote_url": redact_remote_url(item.get("remote_url")),
        "default_branch": item.get("default_branch"),
    }


def _ref_data(ref: Any) -> dict[str, Any]:
    return {
        "ref_name": ref.ref_name,
        "ref_type": ref.ref_type.value if hasattr(ref.ref_type, "value") else ref.ref_type,
        "commit_sha": ref.commit_sha,
        "is_current": ref.is_current,
    }


def _status_data(status: Any) -> dict[str, Any]:
    return {
        "head_commit_sha": status.head_commit_sha,
        "branch_name": status.branch_name,
        "is_dirty": status.is_dirty,
        "ahead_count": status.ahead_count,
        "behind_count": status.behind_count,
        "file_changes": [_file_change_data(item) for item in status.file_changes],
        "summary": status.summary,
    }


def _file_change_data(item: Any) -> dict[str, Any]:
    return {
        "path": item.path,
        "change_status": item.change_status.value if hasattr(item.change_status, "value") else item.change_status,
        "old_path": item.old_path,
        "insertions": item.insertions,
        "deletions": item.deletions,
    }


def _commit_data(item: Any) -> dict[str, Any]:
    return {
        "commit_sha": item.commit_sha,
        "parent_shas": item.parent_shas,
        "author_name": item.author_name,
        "committed_at": item.committed_at,
        "message_summary": item.message_summary,
    }


def _operation_data(record: Any) -> dict[str, Any]:
    return {
        "git_operation_id": record.git_operation_id,
        "git_repository_id": record.git_repository_id,
        "operation_type": record.operation_type,
        "status": record.status,
        "started_at": record.started_at,
        "finished_at": record.finished_at,
        "result": sanitize_git_payload(record.result_json or {}),
    }


def _remove_tree(path: Path) -> None:
    def _onexc(func, target, exc) -> None:  # type: ignore[no-untyped-def]
        if isinstance(exc, PermissionError):
            try:
                os.chmod(target, stat.S_IWRITE)
            except OSError:
                pass
            func(target)
            return
        raise exc

    last_error: PermissionError | None = None
    for _ in range(10):
        try:
            shutil.rmtree(path, onexc=_onexc)
            return
        except PermissionError as error:
            last_error = error
            time.sleep(0.1)
    if last_error is not None:
        raise last_error
