from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ConfigFileType(StrEnum):
    SERVER_CFG = "server_cfg"
    RESOURCE = "resource"
    TXADMIN = "txadmin"
    DATABASE = "database"
    UNKNOWN = "unknown"


class SnapshotKind(StrEnum):
    BEFORE = "before"
    AFTER = "after"
    MANUAL = "manual"
    VALIDATION = "validation"


class ChangeSetStatus(StrEnum):
    PLANNED = "planned"
    APPLIED = "applied"
    REVERTED = "reverted"
    FAILED = "failed"


class ValidationStatus(StrEnum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"
    ERROR = "error"


class FindingSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class SecretFindingStatus(StrEnum):
    OPEN = "open"
    IGNORED = "ignored"
    RESOLVED = "resolved"


@dataclass(frozen=True, slots=True)
class ConfigFileRef:
    config_file_id: str
    project_id: str
    path: str
    config_type: ConfigFileType
    absolute_path: str


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    rule_id: str
    severity: FindingSeverity
    message: str
    path: str | None = None
    line: int | None = None
    column: int | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SecretFinding:
    detector_id: str
    severity: FindingSeverity
    path: str | None
    line: int | None
    redacted_preview: str
    secret_type: str
