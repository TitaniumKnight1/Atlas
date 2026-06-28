from __future__ import annotations

import subprocess
from dataclasses import dataclass

from backend.domain.dev_db.types import DockerAvailabilityState, DockerProbeResult


@dataclass(frozen=True, slots=True)
class CliDockerAvailabilityProbe:
    version_timeout_seconds: float = 5.0
    info_timeout_seconds: float = 10.0

    def probe(self) -> DockerProbeResult:
        try:
            version = subprocess.run(
                ["docker", "version", "--format", "{{.Client.Version}}"],
                capture_output=True,
                text=True,
                timeout=self.version_timeout_seconds,
            )
        except FileNotFoundError:
            return DockerProbeResult(state=DockerAvailabilityState.CLI_MISSING)
        except subprocess.TimeoutExpired:
            return DockerProbeResult(
                state=DockerAvailabilityState.ERROR,
                stderr="docker version timed out",
            )
        except OSError as error:
            return DockerProbeResult(
                state=DockerAvailabilityState.ERROR,
                stderr=str(error),
            )

        if version.returncode != 0:
            return DockerProbeResult(
                state=DockerAvailabilityState.CLI_MISSING,
                stderr=_stderr(version),
            )

        client_version = (version.stdout or "").strip() or None

        try:
            info = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=self.info_timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return DockerProbeResult(
                state=DockerAvailabilityState.ERROR,
                client_version=client_version,
                stderr="docker info timed out",
            )
        except OSError as error:
            return DockerProbeResult(
                state=DockerAvailabilityState.ERROR,
                client_version=client_version,
                stderr=str(error),
            )

        if info.returncode != 0:
            return DockerProbeResult(
                state=DockerAvailabilityState.DAEMON_UNREACHABLE,
                client_version=client_version,
                stderr=_stderr(info),
            )

        return DockerProbeResult(
            state=DockerAvailabilityState.AVAILABLE,
            client_version=client_version,
        )


def _stderr(result: subprocess.CompletedProcess[str]) -> str | None:
    combined = (result.stderr or result.stdout or "").strip()
    return combined or None
