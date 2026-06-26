from __future__ import annotations

from enum import StrEnum


class BackupScope(StrEnum):
    FULL = "full"
    CONFIG = "config"
    RESOURCES = "resources"
    DATABASE = "database"
    CUSTOM = "custom"


class BackupRunStatus(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PRUNED = "pruned"


class BackupTriggerType(StrEnum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    PRE_CHANGE = "pre_change"
    AUTOMATION = "automation"


class BackupItemType(StrEnum):
    CONFIG = "config"
    RESOURCE = "resource"
    DATABASE = "database"
    SNAPSHOT = "snapshot"
    ARTIFACT_METADATA = "artifact_metadata"
    LOG = "log"


class RestoreRunStatus(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RetentionEventType(StrEnum):
    EVALUATED = "evaluated"
    PRUNED = "pruned"
    SKIPPED = "skipped"
    FAILED = "failed"


class ConsistencyGuarantee(StrEnum):
    QUIESCED = "quiesced"
    BEST_EFFORT = "best_effort"
    UNAVAILABLE = "unavailable"
