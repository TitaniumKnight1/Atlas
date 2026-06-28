from __future__ import annotations

import socket
from typing import Any

from backend.domain.dev_db.types import (
    DockerAvailabilityState,
    DockerProbeResult,
    bring_your_own_mysql_message,
    dev_db_connection_string,
    dev_db_host,
    dev_db_port,
)


def is_tcp_port_listening(host: str, port: int, *, timeout_seconds: float = 1.0) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout_seconds)
    try:
        return sock.connect_ex((host, port)) == 0
    finally:
        sock.close()


def build_docker_available_check(result: DockerProbeResult) -> dict[str, Any]:
    connection_string = dev_db_connection_string()
    details: dict[str, Any] = {
        "docker_state": result.state.value,
        "connection_string": connection_string,
    }
    if result.client_version:
        details["client_version"] = result.client_version
    if result.stderr:
        details["stderr"] = _truncate(result.stderr)

    if result.state == DockerAvailabilityState.AVAILABLE:
        message = "Docker CLI and daemon are available."
        if result.client_version:
            message = f"Docker CLI and daemon are available (client {result.client_version})."
        return _check("docker_available", "binary", "pass", message, details)

    if result.state == DockerAvailabilityState.CLI_MISSING:
        message = bring_your_own_mysql_message(prefix="Docker CLI not found — install Docker Desktop, or")
        return _check("docker_available", "binary", "warning", message, details)

    if result.state == DockerAvailabilityState.DAEMON_UNREACHABLE:
        message = bring_your_own_mysql_message(
            prefix="Docker is installed but the daemon is not running — start Docker Desktop, or",
        )
        return _check("docker_available", "binary", "warning", message, details)

    message = bring_your_own_mysql_message(prefix="Docker probe failed — retry after fixing Docker, or")
    return _check("docker_available", "binary", "warning", message, details)


def build_dev_db_port_available_check(host: str | None = None, port: int | None = None) -> dict[str, Any]:
    resolved_host = host or dev_db_host()
    resolved_port = port or dev_db_port()
    details = {
        "host": resolved_host,
        "port": resolved_port,
        "connection_string": dev_db_connection_string(),
    }
    if is_tcp_port_listening(resolved_host, resolved_port):
        message = (
            f"{resolved_host}:{resolved_port} is already in use — "
            "this may be host MySQL or a stale container."
        )
        return _check("dev_db_port_available", "network", "warning", message, details)

    message = f"{resolved_host}:{resolved_port} is free for dev DB provisioning."
    return _check("dev_db_port_available", "network", "pass", message, details)


def build_dev_db_reachable_check(host: str | None = None, port: int | None = None) -> dict[str, Any]:
    resolved_host = host or dev_db_host()
    resolved_port = port or dev_db_port()
    details = {
        "host": resolved_host,
        "port": resolved_port,
        "connection_string": dev_db_connection_string(),
    }
    if is_tcp_port_listening(resolved_host, resolved_port):
        message = f"MySQL listener reachable at {resolved_host}:{resolved_port}."
        return _check("dev_db_reachable", "database", "pass", message, details)

    message = (
        f"No MySQL listener at {resolved_host}:{resolved_port} yet — "
        "expected before dev DB provisioning (M2)."
    )
    return _check("dev_db_reachable", "database", "warning", message, details)


def _check(
    check_key: str,
    category: str,
    status: str,
    message: str,
    details: dict[str, Any],
) -> dict[str, Any]:
    return {
        "check_key": check_key,
        "category": category,
        "status": status,
        "message": message,
        "details": details,
    }


def _truncate(value: str, limit: int = 500) -> str:
    stripped = value.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[: limit - 3] + "..."
