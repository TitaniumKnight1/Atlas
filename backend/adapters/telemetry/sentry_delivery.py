from __future__ import annotations

import os
from typing import Any

import sentry_sdk
from sentry_sdk.types import Event, Hint

from backend.adapters.telemetry.sanitizer import DeterministicTelemetrySanitizer
from backend.domain.shared_kernel import Severity
from backend.domain.telemetry import (
    SanitizationState,
    TelemetryDeliveryStatus,
    TelemetryEventCandidate,
    TelemetrySanitizerPort,
    TelemetrySubsystem,
)

_sdk_initialized = False


def _reset_sdk_for_tests() -> None:
    global _sdk_initialized
    _sdk_initialized = False
    try:
        client = sentry_sdk.get_client()
        if client.is_active():
            client.close()
    except Exception:  # noqa: BLE001 - test cleanup only
        pass


def _before_send(event: Event, hint: Hint) -> Event | None:
    atlas_meta = (event.get("extra") or {}).get("atlas_telemetry")
    if not isinstance(atlas_meta, dict):
        return None

    payload = atlas_meta.get("payload")
    if not isinstance(payload, dict):
        return None

    sanitizer = DeterministicTelemetrySanitizer()
    decision = sanitizer.sanitize(
        TelemetryEventCandidate(
            event_type=str(atlas_meta.get("event_type", "atlas.telemetry.rejected")),
            subsystem=TelemetrySubsystem(str(atlas_meta.get("subsystem", "backend"))),
            severity=Severity.ERROR,
            payload=payload,
        )
    )
    if decision.state == SanitizationState.REJECTED or not decision.accepted:
        return None

    sanitized = decision.sanitized_payload or {}
    event["message"] = str(sanitized.get("message", event.get("message", "Atlas error")))
    event["tags"] = dict(sanitized.get("tags") or {})
    event["contexts"] = dict(sanitized.get("contexts") or {})
    atlas_meta["payload"] = sanitized
    event["extra"] = {"atlas_telemetry": atlas_meta}
    event.pop("request", None)
    event.pop("user", None)
    _apply_exception_and_stacktrace(event, sanitized)
    return event


def _apply_exception_and_stacktrace(event: dict[str, Any], payload: dict[str, Any]) -> None:
    exception = payload.get("exception")
    if not isinstance(exception, dict):
        return

    value: dict[str, Any] = {
        "type": str(exception.get("type", "Error")),
        "value": str(exception.get("value", "")),
    }
    if exception.get("module"):
        value["module"] = str(exception["module"])

    stacktrace = payload.get("stacktrace")
    if isinstance(stacktrace, list) and stacktrace:
        frames: list[dict[str, Any]] = []
        for frame in stacktrace:
            if not isinstance(frame, dict):
                continue
            frames.append(
                {
                    "filename": str(frame.get("filename", "unknown")),
                    "function": str(frame.get("function", "?")),
                    "lineno": frame.get("lineno"),
                    "module": frame.get("module"),
                }
            )
        if frames:
            value["stacktrace"] = {"frames": frames}

    event["exception"] = {"values": [value]}


def _build_sentry_event(
    *,
    event_id: str,
    event_type: str,
    subsystem: str,
    payload: dict[str, object],
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "message": str(payload.get("message", "Atlas error")),
        "level": "error",
        "tags": dict(payload.get("tags") or {}),
        "contexts": dict(payload.get("contexts") or {}),
        "extra": {
            "atlas_telemetry": {
                "event_id": event_id,
                "event_type": event_type,
                "subsystem": subsystem,
                "payload": payload,
            }
        },
    }
    _apply_exception_and_stacktrace(event, payload)  # type: ignore[arg-type]
    return event


def _init_sentry(dsn: str) -> None:
    global _sdk_initialized
    if _sdk_initialized:
        return
    sentry_sdk.init(
        dsn=dsn,
        send_default_pii=False,
        traces_sample_rate=0.0,
        profiles_sample_rate=0.0,
        auto_enabling_integrations=False,
        integrations=[],
        before_send=_before_send,
    )
    _sdk_initialized = True


class SentryTelemetryDelivery:
    """Delivers pre-sanitized Atlas telemetry events to Sentry with defense-in-depth re-scrubbing."""

    def __init__(self, *, sanitizer: TelemetrySanitizerPort | None = None) -> None:
        self._sanitizer = sanitizer or DeterministicTelemetrySanitizer()
        self._dsn = os.environ.get("ATLAS_SENTRY_DSN", "").strip()

    @property
    def is_configured(self) -> bool:
        return bool(self._dsn)

    def deliver(
        self,
        event_id: str,
        payload: dict[str, object],
        *,
        event_type: str = "atlas.backend.unhandled_exception",
        subsystem: str = "backend",
    ) -> TelemetryDeliveryStatus:
        if not self._dsn:
            return TelemetryDeliveryStatus.SKIPPED

        try:
            _init_sentry(self._dsn)
            sentry_event = _build_sentry_event(
                event_id=event_id,
                event_type=event_type,
                subsystem=subsystem,
                payload=payload,
            )
            filtered = _before_send(sentry_event, {})
            if filtered is None:
                return TelemetryDeliveryStatus.FAILED

            sentry_sdk.capture_event(filtered)
            return TelemetryDeliveryStatus.SUCCEEDED
        except Exception:  # noqa: BLE001 - delivery must not crash the app
            return TelemetryDeliveryStatus.FAILED
