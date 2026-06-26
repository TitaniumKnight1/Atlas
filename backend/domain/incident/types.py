from __future__ import annotations

from enum import StrEnum


class IncidentSeverity(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    FATAL = "fatal"


class IncidentCategory(StrEnum):
    CRASH = "crash"
    STARTUP = "startup"
    RESOURCE = "resource"
    VALIDATION = "validation"
    DATABASE = "database"
    AUTOMATION = "automation"
    PLUGIN = "plugin"
    ATLAS = "atlas"


class IncidentSourceType(StrEnum):
    LOG = "log"
    PROCESS = "process"
    VALIDATION = "validation"
    AUTOMATION = "automation"
    PLUGIN = "plugin"
    MANUAL = "manual"


class IncidentGroupStatus(StrEnum):
    UNRESOLVED = "unresolved"
    RESOLVED = "resolved"
    IGNORED = "ignored"
    MUTED = "muted"


class ContextSnapshotType(StrEnum):
    ENVIRONMENT = "environment"
    RUNTIME = "runtime"
    RESOURCES = "resources"
    STARTUP_ORDER = "startup_order"
    CONFIG_EXCERPT = "config_excerpt"
    LOGS = "logs"
    DATABASE = "database"
    SYSTEM = "system"


class RedactionState(StrEnum):
    RAW_LOCAL = "raw_local"
    REDACTED = "redacted"
    EXPORT_SAFE = "export_safe"
    BLOCKED = "blocked"


# M3b supervisor deque maxlen — honest log availability marker for snapshots.
BOUNDED_LOG_TAIL_LIMIT = 200
