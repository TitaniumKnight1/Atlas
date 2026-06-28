from __future__ import annotations

from unittest.mock import patch

from backend.domain.dev_db.checks import (
    build_dev_db_port_available_check,
    build_dev_db_reachable_check,
    build_docker_available_check,
)
from backend.domain.dev_db.types import DockerAvailabilityState, DockerProbeResult
from backend.domain.pathway2.substitution import AUTO_LOCAL_DB_DEFAULT


def test_docker_available_pass_when_daemon_reachable() -> None:
    check = build_docker_available_check(
        DockerProbeResult(state=DockerAvailabilityState.AVAILABLE, client_version="29.0.0"),
    )

    assert check["check_key"] == "docker_available"
    assert check["category"] == "binary"
    assert check["status"] == "pass"
    assert "available" in check["message"]


def test_docker_unavailable_includes_bring_your_own_connection_string() -> None:
    for state in (
        DockerAvailabilityState.CLI_MISSING,
        DockerAvailabilityState.DAEMON_UNREACHABLE,
        DockerAvailabilityState.ERROR,
    ):
        check = build_docker_available_check(DockerProbeResult(state=state, stderr="probe detail"))
        assert check["status"] == "warning"
        assert check["status"] != "fail"
        assert AUTO_LOCAL_DB_DEFAULT in check["message"]


def test_dev_db_port_available_pass_when_port_free() -> None:
    with patch("backend.domain.dev_db.checks.is_tcp_port_listening", return_value=False):
        check = build_dev_db_port_available_check("127.0.0.1", 3306)

    assert check["check_key"] == "dev_db_port_available"
    assert check["category"] == "network"
    assert check["status"] == "pass"
    assert "free" in check["message"]


def test_dev_db_port_available_warn_when_port_in_use() -> None:
    with patch("backend.domain.dev_db.checks.is_tcp_port_listening", return_value=True):
        check = build_dev_db_port_available_check("127.0.0.1", 3306)

    assert check["status"] == "warning"
    assert "already in use" in check["message"]


def test_dev_db_reachable_pass_when_listener_present() -> None:
    with patch("backend.domain.dev_db.checks.is_tcp_port_listening", return_value=True):
        check = build_dev_db_reachable_check("127.0.0.1", 3306)

    assert check["check_key"] == "dev_db_reachable"
    assert check["category"] == "database"
    assert check["status"] == "pass"
    assert "reachable" in check["message"]


def test_dev_db_reachable_warn_when_not_listening() -> None:
    with patch("backend.domain.dev_db.checks.is_tcp_port_listening", return_value=False):
        check = build_dev_db_reachable_check("127.0.0.1", 3306)

    assert check["status"] == "warning"
    assert check["status"] != "fail"
    assert "M2" in check["message"]
    assert check["details"]["connection_string"] == AUTO_LOCAL_DB_DEFAULT
