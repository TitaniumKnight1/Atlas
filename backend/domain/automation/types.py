from __future__ import annotations

from enum import StrEnum


class TriggerType(StrEnum):
    SERVER_CRASHED = "server_crashed"
    ALERT_FIRED = "alert_fired"
    GIT_PULL_COMPLETED = "git_pull_completed"
    SCHEDULE = "schedule"
    MANUAL = "manual"


class ActionType(StrEnum):
    RECORD_LOCAL_NOTIFICATION = "record_local_notification"
    APPEND_CONFIG_MARKER = "append_config_marker"
    RESTART_SERVER = "restart_server"
    RUN_CONFIG_VALIDATION = "run_config_validation"
    RESCAN_RESOURCES = "rescan_resources"
    GIT_CAPTURE_STATUS = "git_capture_status"
    CREATE_BACKUP = "create_backup"


class ExecutionTier(StrEnum):
    AUTO = "auto"
    APPROVAL_GATED = "approval_gated"


class StepStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    NOT_ATTEMPTED = "not_attempted"
    PENDING_APPROVAL = "pending_approval"
    REJECTED = "rejected"
    SKIPPED = "skipped"
    DEFERRED = "deferred"


class ApprovalState(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"


class RecipeKey(StrEnum):
    RESTART_ON_CRASH = "restart_on_crash"
    POST_GIT_PULL_VALIDATION = "post_git_pull_validation"
    NIGHTLY_MAINTENANCE = "nightly_maintenance"
    ON_ALERT_REMEDIATION = "on_alert_remediation"


class RecipeInstanceStatus(StrEnum):
    ACTIVE = "active"
    DEFERRED = "deferred"
    DISABLED = "disabled"


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
