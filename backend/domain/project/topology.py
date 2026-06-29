from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from backend.adapters.filesystem.resource_presence import is_reparse_point
from backend.adapters.git.urls import redact_remote_url


MAX_DISCOVERY_DEPTH = 8
_SKIP_DIR_NAMES = frozenset({".git", "node_modules", "__pycache__"})


class RepoKind(StrEnum):
    ROOT = "root"
    NESTED = "nested"
    LINKED_IN = "linked_in"


class StructureKind(StrEnum):
    SINGLE_REPO = "single_repo"
    MULTI_REPO_SUBFOLDERS = "multi_repo_subfolders"
    MULTI_REPO_LINKED = "multi_repo_linked"
    ASSEMBLY_NO_ROOT_REPO = "assembly_no_root_repo"
    PLAIN_NO_REPO = "plain_no_repo"


@dataclass(frozen=True, slots=True)
class DiscoveredRepo:
    path: str
    real_target: str
    kind: RepoKind
    branch: str | None
    remote_redacted: str | None
    is_junction: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "real_target": self.real_target,
            "kind": self.kind.value,
            "branch": self.branch,
            "remote_redacted": self.remote_redacted,
            "is_junction": self.is_junction,
        }


@dataclass(frozen=True, slots=True)
class ProjectRepoTopology:
    project_root: str
    root_is_repo: bool
    repos: tuple[DiscoveredRepo, ...]
    unowned_paths: tuple[str, ...]
    structure_kind: StructureKind

    def to_dict(self) -> dict[str, object]:
        return {
            "project_root": self.project_root,
            "root_is_repo": self.root_is_repo,
            "repos": [repo.to_dict() for repo in self.repos],
            "unowned_paths": list(self.unowned_paths),
            "structure_kind": self.structure_kind.value,
        }


def discover_project_repo_topology(project_root: Path) -> ProjectRepoTopology:
    root = project_root.expanduser().resolve()
    if not root.exists():
        return ProjectRepoTopology(
            project_root=str(root),
            root_is_repo=False,
            repos=(),
            unowned_paths=(),
            structure_kind=StructureKind.PLAIN_NO_REPO,
        )

    repos = _discover_repos(root)
    root_is_repo = any(_same_path(repo.real_target, root) for repo in repos)
    unowned_paths = _collect_unowned_root_entries(root, repos)
    structure_kind = _classify_structure(root_is_repo=root_is_repo, repos=repos)
    return ProjectRepoTopology(
        project_root=str(root),
        root_is_repo=root_is_repo,
        repos=repos,
        unowned_paths=unowned_paths,
        structure_kind=structure_kind,
    )


def resolve_path_owning_repo(project_root: Path, file_path: Path, topology: ProjectRepoTopology | None = None) -> str | None:
    """Return the as-seen repo path that owns file_path, or None when unowned/parent-level."""
    root = project_root.expanduser().resolve()
    target = file_path.expanduser().resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return None

    model = topology or discover_project_repo_topology(root)
    owner = _match_repo_for_resolved_path(target, model.repos)
    return owner.path if owner is not None else None


def resolve_path_owner_detail(
    project_root: Path,
    file_path: Path,
    topology: ProjectRepoTopology | None = None,
) -> dict[str, object]:
    root = project_root.expanduser().resolve()
    target = file_path.expanduser().resolve()
    model = topology or discover_project_repo_topology(root)
    owner = _match_repo_for_resolved_path(target, model.repos)
    if owner is None:
        return {"path": str(target), "owner": None, "owner_kind": "unowned"}
    return {
        "path": str(target),
        "owner": owner.path,
        "owner_kind": owner.kind.value,
        "owner_real_target": owner.real_target,
    }


def _discover_repos(project_root: Path) -> tuple[DiscoveredRepo, ...]:
    by_real_root: dict[str, DiscoveredRepo] = {}
    visited_scan: set[str] = set()

    def remember(as_seen: Path, worktree: Path, *, via_junction: bool) -> None:
        real_root = worktree.resolve()
        key = _path_key(real_root)
        kind = _repo_kind(project_root=project_root, as_seen=as_seen, via_junction=via_junction)
        entry = DiscoveredRepo(
            path=str(as_seen),
            real_target=str(real_root),
            kind=kind,
            branch=_read_branch(real_root),
            remote_redacted=redact_remote_url(_read_origin_url(real_root)),
            is_junction=via_junction,
        )
        existing = by_real_root.get(key)
        if existing is None or _prefer_repo_entry(entry, existing):
            by_real_root[key] = entry

    def scan(current: Path, as_seen: Path, depth: int, via_junction: bool) -> None:
        if depth > MAX_DISCOVERY_DEPTH:
            return
        scan_key = _path_key(as_seen)
        if scan_key in visited_scan:
            return
        visited_scan.add(scan_key)

        worktree = _git_worktree_root(current)
        if worktree is not None:
            remember(as_seen=as_seen, worktree=worktree, via_junction=via_junction)
            return

        if not current.is_dir():
            return

        try:
            children = list(current.iterdir())
        except OSError:
            return

        for child in children:
            if child.name in _SKIP_DIR_NAMES or child.name.startswith("."):
                continue
            child_as_seen = as_seen / child.name
            child_via_junction = via_junction or is_reparse_point(child)
            scan(child, child_as_seen, depth + 1, child_via_junction)

    scan(project_root, project_root, depth=0, via_junction=False)
    return tuple(sorted(by_real_root.values(), key=lambda item: item.path))


def _collect_unowned_root_entries(project_root: Path, repos: tuple[DiscoveredRepo, ...]) -> tuple[str, ...]:
    repo_real_roots = {_path_key(Path(repo.real_target)) for repo in repos}
    unowned: list[str] = []
    try:
        entries = list(project_root.iterdir())
    except OSError:
        return ()
    for entry in entries:
        if entry.name.startswith("."):
            continue
        resolved = entry.resolve()
        if _match_repo_for_resolved_path(resolved, repos) is not None:
            continue
        if entry.is_dir() and _path_key(resolved) in repo_real_roots:
            continue
        unowned.append(str(project_root / entry.name))
    return tuple(sorted(unowned))


def _classify_structure(*, root_is_repo: bool, repos: tuple[DiscoveredRepo, ...]) -> StructureKind:
    if not repos:
        return StructureKind.PLAIN_NO_REPO
    if len(repos) == 1 and root_is_repo:
        return StructureKind.SINGLE_REPO
    has_linked = any(repo.kind == RepoKind.LINKED_IN for repo in repos)
    if not root_is_repo:
        if has_linked:
            return StructureKind.MULTI_REPO_LINKED
        return StructureKind.ASSEMBLY_NO_ROOT_REPO
    if has_linked:
        return StructureKind.MULTI_REPO_LINKED
    if len(repos) > 1:
        return StructureKind.MULTI_REPO_SUBFOLDERS
    return StructureKind.SINGLE_REPO


def _repo_kind(*, project_root: Path, as_seen: Path, via_junction: bool) -> RepoKind:
    if _same_path(as_seen, project_root):
        return RepoKind.ROOT
    if via_junction:
        return RepoKind.LINKED_IN
    return RepoKind.NESTED


def _prefer_repo_entry(candidate: DiscoveredRepo, existing: DiscoveredRepo) -> bool:
    priority = {RepoKind.ROOT: 0, RepoKind.NESTED: 1, RepoKind.LINKED_IN: 2}
    if priority[candidate.kind] != priority[existing.kind]:
        return priority[candidate.kind] < priority[existing.kind]
    if candidate.is_junction != existing.is_junction:
        return not candidate.is_junction
    return len(candidate.path) < len(existing.path)


def _match_repo_for_resolved_path(resolved: Path, repos: tuple[DiscoveredRepo, ...]) -> DiscoveredRepo | None:
    best: DiscoveredRepo | None = None
    best_len = -1
    for repo in repos:
        repo_root = Path(repo.real_target).resolve()
        try:
            resolved.relative_to(repo_root)
        except ValueError:
            continue
        prefix_len = len(repo_root.parts)
        if prefix_len > best_len:
            best = repo
            best_len = prefix_len
    return best


def _git_worktree_root(path: Path) -> Path | None:
    dot_git = path / ".git"
    try:
        if dot_git.is_dir():
            return path
        if dot_git.is_file():
            git_dir = _resolve_gitdir_file(dot_git)
            if git_dir is None:
                return None
            if git_dir.name == ".git" and git_dir.parent != path:
                return git_dir.parent
            return path
    except OSError:
        return None
    return None


def _resolve_gitdir_file(dot_git_file: Path) -> Path | None:
    try:
        for line in dot_git_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("gitdir:"):
                raw = line.split(":", 1)[1].strip()
                return Path(raw).expanduser().resolve()
    except OSError:
        return None
    return None


def _read_branch(worktree: Path) -> str | None:
    git_dir = worktree / ".git"
    if git_dir.is_file():
        resolved = _resolve_gitdir_file(git_dir)
        if resolved is None:
            return None
        head_path = resolved / "HEAD"
    else:
        head_path = git_dir / "HEAD"
    try:
        content = head_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if content.startswith("ref: refs/heads/"):
        return content.removeprefix("ref: refs/heads/")
    return None


def _read_origin_url(worktree: Path) -> str | None:
    git_dir = worktree / ".git"
    if git_dir.is_file():
        resolved = _resolve_gitdir_file(git_dir)
        if resolved is None:
            return None
        config_path = resolved / "config"
    else:
        config_path = git_dir / "config"
    try:
        lines = config_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    in_origin = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_origin = stripped == '[remote "origin"]'
            continue
        if in_origin and stripped.startswith("url ="):
            return stripped.split("=", 1)[1].strip()
    return None


def _same_path(left: Path | str, right: Path | str) -> bool:
    return _path_key(left) == _path_key(right)


def _path_key(path: Path | str) -> str:
    resolved = Path(path).expanduser().resolve()
    text = str(resolved)
    if os.name == "nt":
        return text.casefold()
    return text
