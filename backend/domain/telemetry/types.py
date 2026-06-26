from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from backend.domain.shared_kernel import ProjectId, Severity


class TelemetrySubsystem(StrEnum):
    FRONTEND = "frontend"
    BACKEND = "backend"
    TAURI = "tauri"
    PLUGIN = "plugin"
    STARTUP = "startup"


class TelemetryQueueStatus(StrEnum):
    QUEUED = "queued"
    BLOCKED = "blocked"
    DELIVERED = "delivered"
    FAILED = "failed"
    EXPIRED = "expired"


class SanitizationState(StrEnum):
    ALLOWED = "allowed"
    REDACTED = "redacted"
    REJECTED = "rejected"


class TelemetryRejectionReason(StrEnum):
    DISABLED = "disabled"
    CONTAINS_PROJECT_DATA = "contains_project_data"
    CONTAINS_SECRET = "contains_secret"
    CONTAINS_IDENTIFIER = "contains_identifier"
    OVERSIZED = "oversized"
    POLICY = "policy"


class TelemetryDeliveryStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class TelemetryPreferences:
    telemetry_enabled: bool = False
    crash_reporting_enabled: bool = False
    plugin_telemetry_enabled: bool = False
    project_id: ProjectId | None = None
    last_prompted_at: str | None = None
    updated_at: str | None = None
    updated_by: str | None = None


@dataclass(frozen=True, slots=True)
class TelemetryEventCandidate:
    event_type: str
    subsystem: TelemetrySubsystem
    severity: Severity
    payload: dict[str, Any]
    project_id: ProjectId | None = None


@dataclass(frozen=True, slots=True)
class SanitizationDecision:
    state: SanitizationState
    event_type: str
    subsystem: TelemetrySubsystem
    severity: Severity
    sanitized_payload: dict[str, Any] | None
    rules_applied: list[str] = field(default_factory=list)
    redaction_count: int = 0
    rejection_reason: TelemetryRejectionReason | None = None
    summary: dict[str, Any] = field(default_factory=dict)

    @property
    def accepted(self) -> bool:
        return self.state in {SanitizationState.ALLOWED, SanitizationState.REDACTED} and self.sanitized_payload is not None
