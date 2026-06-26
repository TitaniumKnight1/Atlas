from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class ArtifactPlatform(StrEnum):
    WINDOWS = "windows"
    LINUX = "linux"


class ArtifactChannel(StrEnum):
    RECOMMENDED = "recommended"
    LATEST = "latest"
    OPTIONAL = "optional"
    PINNED = "pinned"


class SetupRunStatus(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DependencyCategory(StrEnum):
    BINARY = "binary"
    DATABASE = "database"
    CONFIG = "config"
    NETWORK = "network"
    FILESYSTEM = "filesystem"


class DependencyStatus(StrEnum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class ArtifactVersion:
    artifact_version_id: str
    platform: ArtifactPlatform
    channel: ArtifactChannel
    build_number: str
    download_url: str | None = None
    sha256: str | None = None
    size_bytes: int | None = None
    released_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DownloadProgress:
    operation_id: str
    bytes_received: int
    total_bytes: int | None
    message: str


@dataclass(frozen=True, slots=True)
class ArtifactInstallPlan:
    artifact: ArtifactVersion
    download_path: Path
    extract_path: Path
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ServerConfigPlan:
    server_data_path: Path
    server_cfg_path: Path
    content: str
    prior_content: str | None
    warnings: list[str] = field(default_factory=list)
