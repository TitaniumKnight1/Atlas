from __future__ import annotations

from pathlib import Path
from typing import Protocol

from backend.domain.project.types import DetectedProjectPath


class ProjectFilesystemInspectionPort(Protocol):
    def inspect_root(self, root_path: Path) -> list[DetectedProjectPath]:
        """Inspect candidate project paths without mutating the filesystem."""
