from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlparse

from backend.domain.pathway2.substitution import AUTO_LOCAL_DB_DEFAULT


class DockerAvailabilityState(StrEnum):
    AVAILABLE = "available"
    CLI_MISSING = "cli_missing"
    DAEMON_UNREACHABLE = "daemon_unreachable"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class DockerProbeResult:
    state: DockerAvailabilityState
    client_version: str | None = None
    stderr: str | None = None


def dev_db_connection_string() -> str:
    return AUTO_LOCAL_DB_DEFAULT


def dev_db_host() -> str:
    parsed = urlparse(AUTO_LOCAL_DB_DEFAULT)
    return parsed.hostname or "127.0.0.1"


def dev_db_port() -> int:
    parsed = urlparse(AUTO_LOCAL_DB_DEFAULT)
    return parsed.port or 3306


def bring_your_own_mysql_message(*, prefix: str) -> str:
    return f"{prefix} use your own MySQL at {AUTO_LOCAL_DB_DEFAULT}"
