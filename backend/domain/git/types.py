from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class RepositoryRole(StrEnum):
    PROJECT = "project"
    RESOURCE = "resource"
    TEMPLATE = "template"
    UNKNOWN = "unknown"


class RefType(StrEnum):
    BRANCH = "branch"
    TAG = "tag"
    REMOTE = "remote"


class ChangeStatus(StrEnum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"
    UNTRACKED = "untracked"


class GitOperationType(StrEnum):
    CLONE = "clone"
    FETCH = "fetch"
    PULL = "pull"
    CHECKOUT = "checkout"
    COMMIT = "commit"
    DIFF = "diff"
    STATUS = "status"


class GitOperationStatus(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class GitRef:
    ref_name: str
    ref_type: RefType
    commit_sha: str | None
    is_current: bool = False


@dataclass(frozen=True, slots=True)
class FileChange:
    path: str
    change_status: ChangeStatus
    old_path: str | None = None
    insertions: int | None = None
    deletions: int | None = None


@dataclass(frozen=True, slots=True)
class WorktreeStatus:
    head_commit_sha: str | None
    branch_name: str | None
    is_dirty: bool
    ahead_count: int
    behind_count: int
    file_changes: list[FileChange] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CommitSummary:
    commit_sha: str
    parent_shas: list[str]
    author_name: str | None
    committed_at: str | None
    message_summary: str | None


@dataclass(frozen=True, slots=True)
class DiffSummary:
    base_ref: str
    head_ref: str
    files: list[FileChange]
    patch_stats: dict[str, Any] = field(default_factory=dict)
