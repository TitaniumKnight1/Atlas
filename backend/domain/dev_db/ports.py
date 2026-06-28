from __future__ import annotations

from typing import Protocol

from backend.domain.dev_db.types import DockerProbeResult


class DockerAvailabilityPort(Protocol):
    def probe(self) -> DockerProbeResult:
        """Return structured Docker CLI/daemon availability."""
