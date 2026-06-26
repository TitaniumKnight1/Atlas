from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError
from git.remote import RemoteProgress

from backend.domain.git import (
    ChangeStatus,
    CommitSummary,
    DiffSummary,
    FileChange,
    GitRef,
    ProgressCallback,
    RefType,
    WorktreeStatus,
)


class _GitPythonProgress(RemoteProgress):
    def __init__(self, callback: ProgressCallback) -> None:
        super().__init__()
        self._callback = callback

    def update(self, op_code: int, cur_count: str | float, max_count: str | float | None = None, message: str = "") -> None:
        try:
            current = int(cur_count)
        except (TypeError, ValueError):
            current = 0
        total = None
        if max_count is not None:
            try:
                total = int(max_count)
            except (TypeError, ValueError):
                total = None
        self._callback(
            {
                "op_code": op_code,
                "bytes_received": current,
                "total_bytes": total,
                "message": message or self._op_code_to_string(op_code),
            }
        )


class GitPythonProvider:
    def discover_repositories(self, roots: list[Path]) -> list[dict[str, Any]]:
        discovered: list[dict[str, Any]] = []
        seen: set[str] = set()
        for root in roots:
            resolved = root.expanduser().resolve()
            if not resolved.exists():
                continue
            candidates = [resolved]
            if resolved.is_dir():
                candidates.extend(path.parent for path in resolved.rglob(".git") if path.is_dir())
            for candidate in candidates:
                git_dir = candidate / ".git"
                if not git_dir.exists():
                    continue
                key = str(candidate.resolve())
                if key in seen:
                    continue
                seen.add(key)
                try:
                    repo = Repo(str(candidate))
                except InvalidGitRepositoryError:
                    continue
                discovered.append(
                    {
                        "local_path": key,
                        "default_branch": _default_branch(repo),
                        "remote_url": _origin_url(repo),
                    }
                )
        return discovered

    def clone(self, *, remote_url: str, destination: Path, progress: ProgressCallback | None = None) -> Path:
        destination = destination.expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        progress_obj = _GitPythonProgress(progress) if progress is not None else None
        Repo.clone_from(remote_url, str(destination), progress=progress_obj)
        return destination

    def fetch(self, *, repo_path: Path, progress: ProgressCallback | None = None) -> dict[str, Any]:
        repo = Repo(str(repo_path))
        progress_obj = _GitPythonProgress(progress) if progress is not None else None
        for remote in repo.remotes:
            remote.fetch(progress=progress_obj)
        return {"fetched_remotes": [remote.name for remote in repo.remotes]}

    def pull(self, *, repo_path: Path, progress: ProgressCallback | None = None) -> dict[str, Any]:
        repo = Repo(str(repo_path))
        if not repo.remotes:
            return {"updated_refs": []}
        progress_obj = _GitPythonProgress(progress) if progress is not None else None
        remote = repo.remotes.origin if "origin" in [item.name for item in repo.remotes] else repo.remotes[0]
        pull_info = remote.pull(progress=progress_obj)
        updated = []
        for item in pull_info:
            if getattr(item, "flags", 0) & getattr(item, "FAST_FORWARD", 0):
                updated.append(item.ref.name)
        return {"updated_refs": updated}

    def list_refs(self, *, repo_path: Path) -> list[GitRef]:
        repo = Repo(str(repo_path))
        refs: list[GitRef] = []
        active = repo.active_branch.name if not repo.head.is_detached else None
        for branch in repo.branches:
            refs.append(GitRef(ref_name=branch.name, ref_type=RefType.BRANCH, commit_sha=branch.commit.hexsha, is_current=branch.name == active))
        for tag in repo.tags:
            refs.append(GitRef(ref_name=tag.name, ref_type=RefType.TAG, commit_sha=tag.commit.hexsha, is_current=False))
        for remote in repo.remotes:
            for ref in remote.refs:
                refs.append(GitRef(ref_name=ref.name, ref_type=RefType.REMOTE, commit_sha=ref.commit.hexsha, is_current=False))
        return refs

    def create_branch(self, *, repo_path: Path, branch_name: str, start_point: str | None = None) -> GitRef:
        repo = Repo(str(repo_path))
        branch = repo.create_head(branch_name, start_point, force=False) if start_point else repo.create_head(branch_name)
        return GitRef(ref_name=branch.name, ref_type=RefType.BRANCH, commit_sha=branch.commit.hexsha, is_current=False)

    def checkout(self, *, repo_path: Path, ref_name: str) -> dict[str, Any]:
        repo = Repo(str(repo_path))
        prior = repo.head.commit.hexsha
        repo.git.checkout(ref_name)
        return {"prior_head_sha": prior, "current_head_sha": repo.head.commit.hexsha, "ref_name": ref_name}

    def delete_branch(self, *, repo_path: Path, branch_name: str) -> None:
        repo = Repo(str(repo_path))
        repo.delete_head(branch_name, force=False)

    def commit(self, *, repo_path: Path, message: str, paths: list[str] | None = None) -> CommitSummary:
        repo = Repo(str(repo_path))
        if paths:
            repo.index.add(paths)
        else:
            repo.git.add(A=True)
        commit = repo.index.commit(message)
        return _commit_summary(commit)

    def status(self, *, repo_path: Path) -> WorktreeStatus:
        repo = Repo(str(repo_path))
        return _worktree_status(repo)

    def diff_summary(self, *, repo_path: Path, base_ref: str, head_ref: str, path_filter: str | None = None) -> DiffSummary:
        repo = Repo(str(repo_path))
        if path_filter:
            diff_index = repo.commit(base_ref).diff(repo.commit(head_ref), paths=[path_filter], create_patch=False)
            stat_lines = repo.git.diff("--stat", base_ref, head_ref, "--", path_filter).splitlines()
        else:
            diff_index = repo.commit(base_ref).diff(repo.commit(head_ref), create_patch=False)
            stat_lines = repo.git.diff("--stat", base_ref, head_ref).splitlines()
        files = [_file_change_from_diff(item) for item in diff_index]
        return DiffSummary(base_ref=base_ref, head_ref=head_ref, files=files, patch_stats={"stat_lines": stat_lines[-3:] if stat_lines else []})

    def compare_commits(self, *, repo_path: Path, base_ref: str, head_ref: str, limit: int = 20) -> list[CommitSummary]:
        repo = Repo(str(repo_path))
        commits = list(repo.iter_commits(f"{base_ref}..{head_ref}", max_count=limit))
        return [_commit_summary(commit) for commit in commits]

    def reset_soft(self, *, repo_path: Path, commit_sha: str) -> None:
        repo = Repo(str(repo_path))
        repo.git.reset("--soft", commit_sha)


def _default_branch(repo: Repo) -> str | None:
    try:
        return repo.active_branch.name
    except (TypeError, GitCommandError):
        return None


def _origin_url(repo: Repo) -> str | None:
    if not repo.remotes:
        return None
    for remote in repo.remotes:
        if remote.name == "origin" and remote.urls:
            return next(iter(remote.urls), None)
    if repo.remotes[0].urls:
        return next(iter(repo.remotes[0].urls), None)
    return None


def _worktree_status(repo: Repo) -> WorktreeStatus:
    branch_name = None
    head_sha = repo.head.commit.hexsha if repo.head.is_valid() else None
    try:
        branch_name = repo.active_branch.name
    except TypeError:
        branch_name = None
    changes: list[FileChange] = []
    for item in repo.index.diff(None):
        changes.append(_file_change_from_diff(item))
    for path in repo.untracked_files:
        changes.append(FileChange(path=path, change_status=ChangeStatus.UNTRACKED))
    ahead = behind = 0
    if branch_name and repo.active_branch.tracking_branch():
        tracking = repo.active_branch.tracking_branch()
        ahead, behind = repo.iter_commits(f"{tracking.name}..{branch_name}"), repo.iter_commits(f"{branch_name}..{tracking.name}")
        ahead = sum(1 for _ in ahead)
        behind = sum(1 for _ in behind)
    return WorktreeStatus(
        head_commit_sha=head_sha,
        branch_name=branch_name,
        is_dirty=repo.is_dirty(untracked_files=True),
        ahead_count=ahead,
        behind_count=behind,
        file_changes=changes,
        summary={"untracked_count": len(repo.untracked_files)},
    )


def _file_change_from_diff(item: Any) -> FileChange:
    if item.new_file:
        status = ChangeStatus.ADDED
    elif item.deleted_file:
        status = ChangeStatus.DELETED
    elif item.renamed_file:
        status = ChangeStatus.RENAMED
    else:
        status = ChangeStatus.MODIFIED
    return FileChange(
        path=item.b_path or item.a_path or "unknown",
        change_status=status,
        old_path=item.a_path if item.renamed_file else None,
        insertions=getattr(item, "insertions", None),
        deletions=getattr(item, "deletions", None),
    )


def _commit_summary(commit: Any) -> CommitSummary:
    parents = [parent.hexsha for parent in commit.parents]
    author_name = commit.author.name if commit.author else None
    return CommitSummary(
        commit_sha=commit.hexsha,
        parent_shas=parents,
        author_name=author_name,
        committed_at=commit.committed_datetime.isoformat() if commit.committed_datetime else None,
        message_summary=(commit.message or "").strip().splitlines()[0] if commit.message else None,
    )


def author_email_hash(email: str | None) -> str | None:
    if not email:
        return None
    return hashlib.sha256(email.encode("utf-8")).hexdigest()[:16]
