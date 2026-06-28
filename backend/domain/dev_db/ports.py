from __future__ import annotations

from typing import Any, Protocol

from backend.domain.dev_db.types import DevDatabasePlan, DevDatabaseRuntimeStatus, DockerProbeResult


class DockerAvailabilityPort(Protocol):
    def probe(self) -> DockerProbeResult:
        """Return structured Docker CLI/daemon availability."""


class DevDatabasePort(Protocol):
    def build_plan(self, project_id: str) -> DevDatabasePlan:
        """Build the engine-specific dev database plan for a project."""

    def inspect(self, plan: DevDatabasePlan) -> DevDatabaseRuntimeStatus:
        """Reconcile runtime status from Docker reality."""

    def pull_image(self, plan: DevDatabasePlan) -> None:
        """Pull the container image."""

    def provision(self, plan: DevDatabasePlan, *, root_password: str) -> DevDatabaseRuntimeStatus:
        """Create volume and start the dev database container."""

    def start(self, plan: DevDatabasePlan) -> DevDatabaseRuntimeStatus:
        """Start an existing stopped container."""

    def stop(self, plan: DevDatabasePlan) -> DevDatabaseRuntimeStatus:
        """Stop a running container."""

    def remove(self, plan: DevDatabasePlan, *, remove_volume: bool) -> dict[str, Any]:
        """Remove container and optionally the named volume."""
