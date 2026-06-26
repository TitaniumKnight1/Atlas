from __future__ import annotations

from pathlib import Path

from backend.domain.project import DetectedProjectPath, ProjectPathRole


class LocalProjectFilesystemInspector:
    """Read-only project path detection for ImportProject preview/dry-run."""

    def inspect_root(self, root_path: Path) -> list[DetectedProjectPath]:
        resolved = root_path.expanduser().resolve()
        candidates = [
            (ProjectPathRole.ROOT, resolved),
            (ProjectPathRole.RESOURCES, resolved / "resources"),
            (ProjectPathRole.TXDATA, resolved / "txData"),
            (ProjectPathRole.LOGS, resolved / "logs"),
            (ProjectPathRole.BACKUPS, resolved / "backups"),
            (ProjectPathRole.ARTIFACTS, resolved / "artifacts"),
        ]
        return [
            DetectedProjectPath(role=role, absolute_path=str(path), exists=path.exists())
            for role, path in candidates
            if role is ProjectPathRole.ROOT or path.exists()
        ]
