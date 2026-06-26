from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from backend.domain.setup.types import (
    ArtifactChannel,
    ArtifactPlatform,
    ArtifactVersion,
    DownloadProgress,
    ProcessLaunchPlan,
    ServerProcessStatus,
)


class FiveMArtifactPort(Protocol):
    def discover(self, platform: ArtifactPlatform, channel: ArtifactChannel | None = None) -> list[ArtifactVersion]:
        """Discover FXServer artifacts from the configured source."""

    def download(
        self,
        artifact: ArtifactVersion,
        destination: Path,
        progress: Callable[[DownloadProgress], None] | None = None,
        operation_id: str | None = None,
    ) -> Path:
        """Download an artifact archive to destination."""


class SetupFilesystemPort(Protocol):
    def ensure_directory(self, path: Path) -> None:
        """Create a setup-owned directory."""

    def extract_zip(self, archive_path: Path, destination: Path) -> list[Path]:
        """Extract a zip archive and return extracted paths."""

    def remove_path(self, path: Path) -> None:
        """Remove a setup-created file or directory."""

    def read_text(self, path: Path) -> str | None:
        """Read text if a file exists."""

    def write_text(self, path: Path, content: str) -> None:
        """Write text to a setup-owned path."""

    def touch_file(self, path: Path) -> bool:
        """Create a file if absent. Returns True when created."""


class TxAdminPort(Protocol):
    def detect(self, server_data_path: Path) -> dict[str, object] | None:
        """Read local txAdmin metadata without contacting a process."""


class ProcessPort(Protocol):
    def start(self, process_run_id: str, project_id: str, plan: ProcessLaunchPlan) -> ServerProcessStatus:
        """Start a supervised setup-related process."""

    def stop(self, process_run_id: str, timeout_seconds: float = 5.0) -> ServerProcessStatus:
        """Stop a process and its full child tree."""

    def status(self, process_run_id: str) -> ServerProcessStatus | None:
        """Return current process status when known."""
