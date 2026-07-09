from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.domain.pathway2.commit_safety import GITIGNORE_OVERLAY_ENTRY, OVERLAY_FILENAME
from backend.domain.project.topology import (
    ProjectRepoTopology,
    discover_project_repo_topology,
    resolve_path_owning_repo,
)


def build_unowned_local_entries(
    *,
    project_root: Path,
    topology: ProjectRepoTopology,
) -> list[dict[str, str]]:
    """Parent-level / unowned paths that stay local — never committed by Atlas."""
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


def build_tracked_repo_entries(
    *,
    project_root: Path,
    topology: ProjectRepoTopology,
) -> list[dict[str, Any]]:
    """Discovered tracked repos — informational only; Atlas does not commit here."""
    entries: list[dict[str, Any]] = []
    for repo in topology.repos:
        try:
            repo_path = str(Path(repo.path).relative_to(project_root)).replace("\\", "/")
        except ValueError:
            repo_path = repo.path.replace("\\", "/")
        entries.append(
            {
                "repo_path": repo_path,
                "branch": repo.branch,
                "remote_redacted": repo.remote_redacted,
                "kind": repo.kind.value,
                "is_junction": repo.is_junction,
            }
        )
    return entries


def build_normalization_note(
    *,
    project_root: Path,
    topology: ProjectRepoTopology,
    server_cfg_rel: str | None,
    normalized: bool,
) -> str | None:
    if not normalized or not server_cfg_rel:
        return None
    absolute = (project_root / server_cfg_rel).resolve()
    owner = resolve_path_owning_repo(project_root, absolute, topology)
    if owner is None:
        return (
            f"Atlas normalized {server_cfg_rel} at the project root (local assembly file). "
            "Your dev secrets live in the gitignored overlay. Review any team-facing config changes with your own git tools."
        )
    try:
        owner_rel = str(Path(owner).relative_to(project_root)).replace("\\", "/")
    except ValueError:
        owner_rel = owner
    return (
        f"Atlas normalized tracked server.cfg in {owner_rel} to placeholders plus exec {OVERLAY_FILENAME}. "
        "If that normalization is a change in your repo, review and commit it with your own git tools — Atlas does not commit for you."
    )


def build_local_dev_boundary(
    *,
    project_root: Path,
    topology: ProjectRepoTopology | None = None,
    server_cfg_rel: str | None,
    normalized: bool,
    overlay_gitignored: bool,
) -> dict[str, Any]:
    """Topology-based local vs tracked boundary — information only, no commit set."""
    model = topology or discover_project_repo_topology(project_root)
    unowned_local = build_unowned_local_entries(project_root=project_root, topology=model)
    tracked_repos = build_tracked_repo_entries(project_root=project_root, topology=model)
    normalization_note = build_normalization_note(
        project_root=project_root,
        topology=model,
        server_cfg_rel=server_cfg_rel,
        normalized=normalized,
    )
    return {
        "structure_kind": model.structure_kind.value,
        "unowned_local_paths": unowned_local,
        "tracked_repos": tracked_repos,
        "overlay_gitignored": overlay_gitignored,
        "overlay_filename": OVERLAY_FILENAME,
        "gitignore_overlay_entry": GITIGNORE_OVERLAY_ENTRY,
        "normalization_note": normalization_note,
        "git_handoff_message": (
            "Make and commit your code changes with your own git tools (Cursor, etc.). "
            "Atlas manages your local dev environment and server — it does not commit to tracked repositories."
        ),
        "local_secrets_message": (
            f"Your dev secrets and {OVERLAY_FILENAME} stay local and are never committed or pushed by Atlas."
        ),
    }
