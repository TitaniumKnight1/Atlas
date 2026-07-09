from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.domain.pathway2.commit_safety import (
    build_normalization_path_candidates,
    classify_commit_scope,
    evaluate_commit_safety,
    load_staged_files,
    select_default_return_commit_paths,
    server_cfg_eligible_for_return_commit,
)
from backend.domain.project.topology import (
    DiscoveredRepo,
    ProjectRepoTopology,
    resolve_path_owning_repo,
)

"""
Repo-aware return-path grouping (Stage 2).

Groups worktree changes by owning repo using Stage 1 topology.
Each repo is evaluated against its own .git baseline — never a phantom parent.
Unowned / parent-level assembly files stay local and are never committed.
"""


@dataclass(frozen=True, slots=True)
class RepoReturnSlice:
    repo_path: str
    real_target: str
    branch_name: str | None
    remote_redacted: str | None
    git_repository_id: str | None
    default_commit_paths: tuple[str, ...]
    commit_scope: dict[str, Any]
    contamination_report: dict[str, Any]
    gitignore_contains_overlay: bool
    is_dirty: bool
    has_changes: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_path": self.repo_path,
            "real_target": self.real_target,
            "branch_name": self.branch_name,
            "remote_redacted": self.remote_redacted,
            "git_repository_id": self.git_repository_id,
            "default_commit_paths": list(self.default_commit_paths),
            "commit_scope": self.commit_scope,
            "contamination_report": self.contamination_report,
            "gitignore_contains_overlay": self.gitignore_contains_overlay,
            "is_dirty": self.is_dirty,
            "has_changes": self.has_changes,
        }


def match_registered_repo(
    *,
    discovered: DiscoveredRepo,
    registered_repos: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Match a topology repo to a registered git_repository by local_path."""
    targets = {_path_key(discovered.real_target), _path_key(discovered.path)}
    for repo in registered_repos:
        local = repo.get("local_path")
        if local and _path_key(local) in targets:
            return repo
    return None


def build_unowned_local_entries(
    *,
    project_root: Path,
    topology: ProjectRepoTopology,
) -> list[dict[str, str]]:
    """Parent-level / unowned paths that stay local — never in any return commit."""
    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in topology.unowned_paths:
        path = Path(raw)
        if not path.exists():
            continue
        try:
            rel = str(path.relative_to(project_root)).replace("\\", "/")
        except ValueError:
            rel = path.name
        key = rel.casefold()
        if key in seen:
            continue
        seen.add(key)
        owner = resolve_path_owning_repo(project_root, path, topology)
        if owner is not None:
            continue
        entries.append(
            {
                "path": rel,
                "reason": "stays local (not tracked by any repo)",
            }
        )
    return entries


def build_repo_return_slice(
    *,
    project_root: Path,
    discovered: DiscoveredRepo,
    registered: dict[str, Any] | None,
    file_changes: list[Any],
    branch_name: str | None,
    is_dirty: bool,
    server_cfg_rel: str | None,
    read_text: Any,
    scanner: Any,
    overlay_gitignored: bool,
    include_server_cfg: bool | None = None,
    paths: list[str] | None = None,
    has_git_baseline: bool = True,
) -> RepoReturnSlice:
    """Build one repo's return-path slice against that repo's own baseline."""
    repo_root = Path(discovered.real_target).resolve()
    normalization_paths = _repo_scoped_normalization_paths(
        project_root=project_root,
        repo_root=repo_root,
        server_cfg_rel=server_cfg_rel,
        topology_owner_path=discovered.path,
    )
    if include_server_cfg is None:
        include_server_cfg = server_cfg_eligible_for_return_commit(
            file_changes=file_changes,
            project_root=repo_root,
            read_text=read_text,
            normalization_paths=normalization_paths,
        )
    default_paths = paths or select_default_return_commit_paths(
        file_changes=file_changes,
        include_server_cfg=include_server_cfg,
        normalization_paths=normalization_paths,
        # Real per-repo baseline → genuine untracked additions are in scope.
        # No baseline (empty repo) → keep flood guard (normalization-only untracked).
        include_untracked_additions=has_git_baseline,
    )
    staged_files = load_staged_files(repo_root=repo_root, paths=default_paths, read_text=read_text)
    safety = evaluate_commit_safety(staged_files=staged_files, scanner=scanner)
    commit_scope = classify_commit_scope(paths=default_paths, normalization_paths=normalization_paths)
    has_changes = len(default_paths) > 0
    return RepoReturnSlice(
        repo_path=_display_repo_path(project_root, discovered),
        real_target=str(repo_root),
        branch_name=branch_name or discovered.branch,
        remote_redacted=discovered.remote_redacted,
        git_repository_id=registered["git_repository_id"] if registered else None,
        default_commit_paths=tuple(default_paths),
        commit_scope=commit_scope,
        contamination_report=safety.to_report(),
        gitignore_contains_overlay=overlay_gitignored,
        is_dirty=bool(is_dirty),
        has_changes=has_changes,
    )


def aggregate_return_gate(repos: list[RepoReturnSlice]) -> dict[str, Any]:
    """Overall gate summary. Per-repo commits stay independent — one blocked repo does not block others."""
    changed = [repo for repo in repos if repo.has_changes]
    if not changed:
        empty = evaluate_commit_safety(staged_files=[], scanner=_NullScanner()).to_report()
        empty["summary_lines"] = ["No dev changes to return across discovered repos"]
        empty["allowed"] = True
        empty["gate_status"] = "PASS"
        return empty
    findings: list[dict[str, Any]] = []
    blocked_paths: list[str] = []
    staged_paths: list[str] = []
    blocked_repos = 0
    allowed_repos = 0
    server_cfg_placeholder_only: bool | None = None
    for repo in changed:
        report = repo.contamination_report
        staged_paths.extend(f"{repo.repo_path}/{path}" for path in report.get("staged_paths") or [])
        findings.extend(report.get("findings") or [])
        blocked_paths.extend(report.get("blocked_paths") or [])
        if report.get("allowed", False):
            allowed_repos += 1
        else:
            blocked_repos += 1
        placeholder = report.get("server_cfg_placeholder_only")
        if placeholder is not None:
            server_cfg_placeholder_only = placeholder if server_cfg_placeholder_only is None else (
                server_cfg_placeholder_only and placeholder
            )
    # Step-level allowed when at least one changed repo can commit (or none blocked entirely).
    allowed = blocked_repos == 0 or allowed_repos > 0
    gate_status = "PASS" if blocked_repos == 0 else ("BLOCKED" if allowed_repos == 0 else "PARTIAL")
    summary_lines = [
        f"Repos with changes: {len(changed)}",
        f"Secret scan: {gate_status}",
    ]
    if blocked_repos:
        summary_lines.append(
            f"{blocked_repos} repo(s) blocked — fix flagged files in those repos; other repos can still commit."
        )
    return {
        "gate_status": gate_status,
        "allowed": allowed,
        "staged_paths": staged_paths,
        "overlay_excluded": True,
        "server_cfg_placeholder_only": server_cfg_placeholder_only,
        "findings": findings,
        "blocked_paths": list(dict.fromkeys(blocked_paths)),
        "summary_lines": summary_lines,
        "push_seam": (
            "evaluate_commit_safety is reusable for a future guarded PushBranch; "
            "Atlas remains commit-only per ADR-0010."
        ),
        "manual_push_message": (
            "Return-path commits are per-repo and use explicit paths only — never blanket git add. "
            "Commit each repo locally when ready, then push with your git tool — Atlas does not push."
        ),
    }


def _repo_scoped_normalization_paths(
    *,
    project_root: Path,
    repo_root: Path,
    server_cfg_rel: str | None,
    topology_owner_path: str,
) -> set[str]:
    """Normalization candidates relative to this repo — only if server.cfg is owned here."""
    candidates = build_normalization_path_candidates(server_cfg_rel=None)
    if not server_cfg_rel:
        return candidates
    absolute = (project_root / server_cfg_rel).resolve()
    try:
        absolute.relative_to(repo_root)
    except ValueError:
        return candidates
    owner = resolve_path_owning_repo(project_root, absolute)
    if owner is None or _path_key(owner) != _path_key(topology_owner_path):
        # Unowned or owned by another repo — do not treat as this repo's normalization set.
        return candidates
    rel_in_repo = str(absolute.relative_to(repo_root)).replace("\\", "/")
    return build_normalization_path_candidates(server_cfg_rel=rel_in_repo)


def _display_repo_path(project_root: Path, discovered: DiscoveredRepo) -> str:
    as_seen = Path(discovered.path)
    try:
        return str(as_seen.relative_to(project_root)).replace("\\", "/")
    except ValueError:
        return discovered.path.replace("\\", "/")


def _path_key(path: Path | str) -> str:
    import os

    text = str(Path(path).expanduser().resolve())
    if os.name == "nt":
        return text.casefold()
    return text


class _NullScanner:
    def scan(self, *, path: str, content: str) -> list[Any]:
        return []
