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


class DevDatabaseEngine(StrEnum):
    MYSQL = "mysql"
    POSTGRES = "postgres"


class DevDatabaseLifecycleStatus(StrEnum):
    ABSENT = "absent"
    PROVISIONING = "provisioning"
    RUNNING = "running"
    STOPPED = "stopped"
    REACHABLE = "reachable"
    ERROR = "error"


DEV_DB_USER = "atlas_dev"
DEV_DB_PASSWORD = "atlas_dev"
DEV_DB_DATABASE = "atlas_dev"
MYSQL_IMAGE = "mysql:8.0"


@dataclass(frozen=True, slots=True)
class DevDatabasePlan:
    project_id: str
    engine: DevDatabaseEngine
    image: str
    container_name: str
    volume_name: str
    host: str
    port: int
    database: str
    user: str
    password: str
    connection_string: str
    publish_host_port: str


@dataclass(frozen=True, slots=True)
class DevDatabaseRuntimeStatus:
    lifecycle: DevDatabaseLifecycleStatus
    engine: DevDatabaseEngine
    container_id: str | None = None
    container_name: str | None = None
    volume_name: str | None = None
    docker_state: str | None = None
    container_running: bool = False
    mysql_reachable: bool = False
    connection_string: str = AUTO_LOCAL_DB_DEFAULT
    message: str | None = None
    stderr: str | None = None


class DevDatabaseAdapterError(RuntimeError):
    def __init__(self, message: str, *, stderr: str | None = None) -> None:
        self.stderr = stderr
        super().__init__(message)
