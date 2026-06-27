from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from backend.domain.telemetry import (
    SanitizationDecision,
    SanitizationState,
    TelemetryEventCandidate,
    TelemetryRejectionReason,
)


MAX_EVENT_BYTES = 32_000
REDACTION = "[REDACTED]"
PROJECT_DATA = "[PROJECT_DATA_BLOCKED]"

ALLOWED_PAYLOAD_KEYS = {
    "message",
    "exception",
    "stacktrace",
    "breadcrumbs",
    "contexts",
    "tags",
    "plugin_id",
    "route",
}
ALLOWED_CONTEXT_KEYS = {"atlas", "backend", "os", "runtime", "tauri", "plugin", "feature_flags"}
ALLOWED_TAG_KEYS = {"atlas_version", "backend_subsystem", "environment", "plugin_id", "route"}
ALLOWED_EXCEPTION_KEYS = {"type", "value", "module"}
ALLOWED_FRAME_KEYS = {"filename", "function", "module", "lineno", "abs_path"}
ALLOWED_BREADCRUMB_KEYS = {"category", "message", "level", "timestamp", "type"}
ALLOWED_ENV_KEYS = {"ATLAS_LOG_LEVEL", "ATLAS_ENV"}

SECRET_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "discord_webhook_url",
        re.compile(r"https://(?:canary\.|ptb\.)?discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9._~-]+", re.IGNORECASE),
    ),
    ("discord_token", re.compile(r"\b(?:mfa\.)?[A-Za-z0-9_-]{23,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{20,}\b")),
    (
        "database_connection_string",
        re.compile(r"\b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|redis|mssql|sqlite)://[^\s'\"<>]+", re.IGNORECASE),
    ),
    (
        "credential_assignment",
        re.compile(
            r"\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|secret|password|passwd|pwd|client[_-]?secret|token)\b['\"]?\s*[:=]\s*['\"]?[^'\"\s,;{}()[\]]+",
            re.IGNORECASE,
        ),
    ),
    ("cfx_license_key", re.compile(r"\bcfxk_[A-Za-z0-9_-]{20,}\b", re.IGNORECASE)),
    ("license_identifier", re.compile(r"\blicense:[0-9a-f]{32,40}\b", re.IGNORECASE)),
    ("api_key", re.compile(r"\b(?:sk-[a-zA-Z0-9_-]{20,}|ghp_[a-zA-Z0-9]{30,})\b")),
)

IDENTIFIER_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("ipv4_address", re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")),
    ("ipv6_address", re.compile(r"(?i)(?<![a-z0-9])(?:(?:[0-9a-f]{1,4}:){2,7}[0-9a-f]{1,4}|(?:[0-9a-f]{0,4}::[0-9a-f:]{1,14}))(?![a-z0-9])")),
    ("steam_identifier", re.compile(r"\b(?:steam:[0-9a-f]{15,}|7656119\d{10})\b", re.IGNORECASE)),
    ("rockstar_identifier", re.compile(r"\b(?:rockstar|license2|fivem|license|discord|xbl|live|ip):[^\s'\"<>]+", re.IGNORECASE)),
    ("windows_file_path", re.compile(r"\b[A-Z]:\\[^\s'\"<>]+", re.IGNORECASE)),
    ("unix_file_path", re.compile(r"(?<!\w)/(?:Users|home|srv|opt|var)/[^\s'\"<>]+", re.IGNORECASE)),
)

PROJECT_DATA_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("server_cfg", re.compile(r"\bserver\.cfg\b", re.IGNORECASE)),
    ("txdata_path", re.compile(r"\btxData\b", re.IGNORECASE)),
    ("resources_path", re.compile(r"(?:^|[\\/])resources(?:[\\/]|$)", re.IGNORECASE)),
    ("fxserver_log", re.compile(r"\b(?:FXServer|txAdmin|server log|resource log|player connecting|player dropped)\b", re.IGNORECASE)),
    ("database_dump", re.compile(r"\b(?:INSERT INTO|CREATE TABLE|SELECT \* FROM|ALTER TABLE)\b", re.IGNORECASE)),
)

SENSITIVE_KEY_HINTS = {
    "api_key",
    "apikey",
    "authorization",
    "connection_string",
    "database_url",
    "dsn",
    "license",
    "license_key",
    "password",
    "player",
    "player_id",
    "player_name",
    "secret",
    "server_cfg",
    "steam",
    "token",
    "webhook",
}


class TelemetrySanitizationError(RuntimeError):
    """Raised internally to fail closed with a typed rejection reason."""

    def __init__(self, reason: TelemetryRejectionReason, rule: str, message: str) -> None:
        self.reason = reason
        self.rule = rule
        super().__init__(message)


@dataclass(slots=True)
class _SanitizerState:
    rules_applied: set[str]
    redaction_count: int = 0

    def apply_rule(self, rule: str) -> None:
        self.rules_applied.add(rule)


class DeterministicTelemetrySanitizer:
    """Fail-closed sanitizer for Atlas-owned telemetry candidates only."""

    def sanitize(self, candidate: TelemetryEventCandidate) -> SanitizationDecision:
        state = _SanitizerState(rules_applied=set())
        try:
            if not candidate.event_type.startswith("atlas."):
                raise TelemetrySanitizationError(TelemetryRejectionReason.POLICY, "event_type_allowlist", "event_type must be Atlas-owned")
            serialized = json.dumps(candidate.payload, sort_keys=True, default=str)
            if len(serialized.encode("utf-8")) > MAX_EVENT_BYTES:
                raise TelemetrySanitizationError(TelemetryRejectionReason.OVERSIZED, "max_event_size", "telemetry event is oversized")
            _reject_unknown_keys(candidate.payload, ALLOWED_PAYLOAD_KEYS, "payload")
            sanitized = self._sanitize_payload(candidate.payload, state)
            result_state = SanitizationState.REDACTED if state.redaction_count else SanitizationState.ALLOWED
            return SanitizationDecision(
                state=result_state,
                event_type=candidate.event_type,
                subsystem=candidate.subsystem,
                severity=candidate.severity,
                sanitized_payload=sanitized,
                rules_applied=sorted(state.rules_applied),
                redaction_count=state.redaction_count,
                summary={"fingerprint": _fingerprint(candidate.event_type, candidate.subsystem.value, sorted(state.rules_applied))},
            )
        except TelemetrySanitizationError as error:
            state.apply_rule(error.rule)
            return self._rejection(candidate, error.reason, state, str(error))
        except Exception as error:  # noqa: BLE001 - sanitizer must never send on uncertainty.
            state.apply_rule("sanitizer_exception")
            return self._rejection(candidate, TelemetryRejectionReason.POLICY, state, f"sanitizer failed closed: {type(error).__name__}")

    def _sanitize_payload(self, payload: dict[str, Any], state: _SanitizerState) -> dict[str, Any]:
        sanitized: dict[str, Any] = {}
        for key, value in payload.items():
            _reject_sensitive_key(key)
            if key == "exception":
                sanitized[key] = self._sanitize_exception(value, state)
            elif key == "stacktrace":
                sanitized[key] = self._sanitize_stacktrace(value, state)
            elif key == "breadcrumbs":
                sanitized[key] = self._sanitize_breadcrumbs(value, state)
            elif key == "contexts":
                sanitized[key] = self._sanitize_contexts(value, state)
            elif key == "tags":
                sanitized[key] = self._sanitize_tags(value, state)
            else:
                sanitized[key] = self._sanitize_value(value, state, f"payload.{key}")
        return sanitized

    def _sanitize_exception(self, value: Any, state: _SanitizerState) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise TelemetrySanitizationError(TelemetryRejectionReason.POLICY, "exception_shape", "exception must be an object")
        _reject_unknown_keys(value, ALLOWED_EXCEPTION_KEYS, "exception")
        return {key: self._sanitize_value(item, state, f"exception.{key}") for key, item in value.items()}

    def _sanitize_stacktrace(self, value: Any, state: _SanitizerState) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            raise TelemetrySanitizationError(TelemetryRejectionReason.POLICY, "stacktrace_shape", "stacktrace must be a list")
        frames: list[dict[str, Any]] = []
        for index, frame in enumerate(value):
            if not isinstance(frame, dict):
                raise TelemetrySanitizationError(TelemetryRejectionReason.POLICY, "stacktrace_frame_shape", "stack frames must be objects")
            _reject_unknown_keys(frame, ALLOWED_FRAME_KEYS, f"stacktrace.{index}")
            frames.append({key: self._sanitize_value(item, state, f"stacktrace.{key}") for key, item in frame.items()})
        return frames

    def _sanitize_breadcrumbs(self, value: Any, state: _SanitizerState) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            raise TelemetrySanitizationError(TelemetryRejectionReason.POLICY, "breadcrumbs_shape", "breadcrumbs must be a list")
        crumbs: list[dict[str, Any]] = []
        for index, crumb in enumerate(value):
            if not isinstance(crumb, dict):
                raise TelemetrySanitizationError(TelemetryRejectionReason.POLICY, "breadcrumb_shape", "breadcrumbs must be objects")
            _reject_unknown_keys(crumb, ALLOWED_BREADCRUMB_KEYS, f"breadcrumbs.{index}")
            crumbs.append({key: self._sanitize_value(item, state, f"breadcrumbs.{key}") for key, item in crumb.items()})
        return crumbs

    def _sanitize_contexts(self, value: Any, state: _SanitizerState) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise TelemetrySanitizationError(TelemetryRejectionReason.POLICY, "contexts_shape", "contexts must be an object")
        _reject_unknown_keys(value, ALLOWED_CONTEXT_KEYS, "contexts")
        return {key: self._sanitize_allowed_dict(item, state, f"contexts.{key}") for key, item in value.items()}

    def _sanitize_tags(self, value: Any, state: _SanitizerState) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise TelemetrySanitizationError(TelemetryRejectionReason.POLICY, "tags_shape", "tags must be an object")
        _reject_unknown_keys(value, ALLOWED_TAG_KEYS, "tags")
        return {key: self._sanitize_value(item, state, f"tags.{key}") for key, item in value.items()}

    def _sanitize_allowed_dict(self, value: Any, state: _SanitizerState, path: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise TelemetrySanitizationError(TelemetryRejectionReason.POLICY, "context_value_shape", f"{path} must be an object")
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            _reject_sensitive_key(key)
            if key.lower() == "env":
                sanitized[key] = self._sanitize_environment(item, state)
            else:
                sanitized[key] = self._sanitize_value(item, state, f"{path}.{key}")
        return sanitized

    def _sanitize_environment(self, value: Any, state: _SanitizerState) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise TelemetrySanitizationError(TelemetryRejectionReason.POLICY, "environment_shape", "env context must be an object")
        unknown = sorted(set(value) - ALLOWED_ENV_KEYS)
        if unknown:
            raise TelemetrySanitizationError(TelemetryRejectionReason.POLICY, "environment_allowlist", "environment key is not allowlisted")
        return {key: self._sanitize_value(item, state, f"env.{key}") for key, item in value.items()}

    def _sanitize_value(self, value: Any, state: _SanitizerState, path: str) -> Any:
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, str):
            return _sanitize_string(value, state)
        if isinstance(value, list):
            return [self._sanitize_value(item, state, f"{path}[]") for item in value]
        if isinstance(value, dict):
            return self._sanitize_allowed_dict(value, state, path)
        raise TelemetrySanitizationError(TelemetryRejectionReason.POLICY, "unknown_value_shape", f"unsupported value at {path}")

    def _rejection(
        self,
        candidate: TelemetryEventCandidate,
        reason: TelemetryRejectionReason,
        state: _SanitizerState,
        message: str,
    ) -> SanitizationDecision:
        return SanitizationDecision(
            state=SanitizationState.REJECTED,
            event_type=_safe_event_type(candidate.event_type),
            subsystem=candidate.subsystem,
            severity=candidate.severity,
            sanitized_payload=None,
            rules_applied=sorted(state.rules_applied),
            redaction_count=state.redaction_count,
            rejection_reason=reason,
            summary={
                "reason": reason.value,
                "message": message,
                "rules": sorted(state.rules_applied),
                "fingerprint": _fingerprint(_safe_event_type(candidate.event_type), candidate.subsystem.value, sorted(state.rules_applied)),
            },
        )


def _sanitize_string(value: str, state: _SanitizerState) -> str:
    for rule, pattern in PROJECT_DATA_RULES:
        if pattern.search(value):
            state.apply_rule(rule)
            raise TelemetrySanitizationError(TelemetryRejectionReason.CONTAINS_PROJECT_DATA, rule, "event contains FiveM project data")

    sanitized = value
    for rule, pattern in SECRET_RULES:
        sanitized, count = pattern.subn(REDACTION, sanitized)
        if count:
            state.apply_rule(rule)
            state.redaction_count += count
    for rule, pattern in IDENTIFIER_RULES:
        sanitized, count = pattern.subn(REDACTION, sanitized)
        if count:
            state.apply_rule(rule)
            state.redaction_count += count
    return sanitized


def _reject_unknown_keys(value: dict[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise TelemetrySanitizationError(TelemetryRejectionReason.POLICY, "unknown_field", f"unknown field at {path}: {unknown[0]}")


def _reject_sensitive_key(key: str) -> None:
    normalized = key.lower().replace("-", "_")
    if normalized in SENSITIVE_KEY_HINTS or any(hint in normalized for hint in ("player", "password", "secret", "token", "webhook")):
        reason = TelemetryRejectionReason.CONTAINS_PROJECT_DATA if "player" in normalized else TelemetryRejectionReason.CONTAINS_SECRET
        raise TelemetrySanitizationError(reason, "sensitive_field_name", f"sensitive field name is not allowed: {key}")


def _safe_event_type(value: str) -> str:
    return value if re.fullmatch(r"atlas\.[a-z0-9_.-]{1,120}", value) else "atlas.telemetry.rejected"


def _fingerprint(*parts: object) -> str:
    encoded = json.dumps(parts, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]
