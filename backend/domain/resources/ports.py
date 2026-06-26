from __future__ import annotations

from pathlib import Path
from typing import Protocol

from backend.domain.resources.types import DiscoveredResource


class ResourceFilesystemPort(Protocol):
    def read_text(self, path: Path) -> str | None: ...

    def discover_resources(self, roots: list[Path]) -> list[DiscoveredResource]: ...
