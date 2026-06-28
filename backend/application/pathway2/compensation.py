from __future__ import annotations

import uuid
from pathlib import Path

from backend.application.commands.compensation import RestorePathFromSnapshotCompensation
from backend.application.config.service import RestoreConfigFileCompensation
from backend.domain.shared_kernel import ProjectId


def snapshot_config_compensation(
    *,
    undo_root: Path,
    absolute_path: Path,
    prior_content: str | None,
    filesystem,
) -> RestoreConfigFileCompensation | RestorePathFromSnapshotCompensation:
    """Persist prior config content in app-data snapshots so audit rows never store raw secrets."""
    if prior_content is None:
        return RestoreConfigFileCompensation(str(absolute_path), None, filesystem)
    snapshot_dir = undo_root / str(uuid.uuid4())
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = snapshot_dir / f"{absolute_path.name}.snapshot"
    snapshot_path.write_text(prior_content, encoding="utf-8")
    return RestorePathFromSnapshotCompensation(str(snapshot_path), str(absolute_path))


def pathway2_undo_root(app_data_dir: Path, project_id: ProjectId) -> Path:
    root = app_data_dir / "pathway2-undo" / str(project_id)
    root.mkdir(parents=True, exist_ok=True)
    return root
