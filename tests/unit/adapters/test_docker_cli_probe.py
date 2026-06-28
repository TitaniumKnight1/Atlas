from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from backend.adapters.docker.cli_probe import CliDockerAvailabilityProbe
from backend.domain.dev_db.types import DockerAvailabilityState


def _completed(returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_probe_available_when_version_and_info_succeed() -> None:
    probe = CliDockerAvailabilityProbe()
    with patch(
        "backend.adapters.docker.cli_probe.subprocess.run",
        side_effect=[
            _completed(stdout="29.0.0\n"),
            _completed(returncode=0),
        ],
    ):
        result = probe.probe()

    assert result.state == DockerAvailabilityState.AVAILABLE
    assert result.client_version == "29.0.0"
    assert result.stderr is None


def test_probe_cli_missing_when_docker_not_found() -> None:
    probe = CliDockerAvailabilityProbe()
    with patch("backend.adapters.docker.cli_probe.subprocess.run", side_effect=FileNotFoundError):
        result = probe.probe()

    assert result.state == DockerAvailabilityState.CLI_MISSING


def test_probe_cli_missing_when_version_fails() -> None:
    probe = CliDockerAvailabilityProbe()
    with patch(
        "backend.adapters.docker.cli_probe.subprocess.run",
        return_value=_completed(returncode=1, stderr="docker: command failed"),
    ):
        result = probe.probe()

    assert result.state == DockerAvailabilityState.CLI_MISSING
    assert result.stderr == "docker: command failed"


def test_probe_daemon_unreachable_when_info_fails() -> None:
    probe = CliDockerAvailabilityProbe()
    with patch(
        "backend.adapters.docker.cli_probe.subprocess.run",
        side_effect=[
            _completed(stdout="29.0.0\n"),
            _completed(returncode=1, stderr="Cannot connect to the Docker daemon"),
        ],
    ):
        result = probe.probe()

    assert result.state == DockerAvailabilityState.DAEMON_UNREACHABLE
    assert result.client_version == "29.0.0"
    assert "Docker daemon" in (result.stderr or "")


def test_probe_error_when_version_times_out() -> None:
    probe = CliDockerAvailabilityProbe()
    with patch("backend.adapters.docker.cli_probe.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["docker"], timeout=5)):
        result = probe.probe()

    assert result.state == DockerAvailabilityState.ERROR
    assert result.stderr == "docker version timed out"


def test_probe_error_when_info_times_out() -> None:
    probe = CliDockerAvailabilityProbe()
    with patch(
        "backend.adapters.docker.cli_probe.subprocess.run",
        side_effect=[
            _completed(stdout="29.0.0\n"),
            subprocess.TimeoutExpired(cmd=["docker"], timeout=10),
        ],
    ):
        result = probe.probe()

    assert result.state == DockerAvailabilityState.ERROR
    assert result.client_version == "29.0.0"
    assert result.stderr == "docker info timed out"
