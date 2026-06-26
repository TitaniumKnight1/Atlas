from __future__ import annotations

from enum import StrEnum


class TriggerType(StrEnum):
    SERVER_CRASHED = "server_crashed"
    ALERT_FIRED = "alert_fired"
    SCHEDULE = "schedule"
    MANUAL = "manual"


class ActionType(StrEnum):
    RECORD_LOCAL_NOTIFICATION = "record_local_notification"
    APPEND_CONFIG_MARKER = "append_config_marker"


class SafetyClass(StrEnum):
    READ_ONLY = "read_only"
    REVERSIBLE_WRITE = "reversible_write"
    PROCESS_CONTROL = "process_control"
    DESTRUCTIVE = "destructive"
    EXTERNAL = "external"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class ConditionType(StrEnum):
    ALWAYS = "always"
    SEVERITY_EQUALS = "severity_equals"


class AutomationSettingKey(StrEnum):
    GLOBAL_ENABLED = "global_enabled"
