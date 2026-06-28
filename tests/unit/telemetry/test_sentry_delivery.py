from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from backend.adapters.telemetry.sentry_delivery import (
    SentryTelemetryDelivery,
    _before_send,
    _build_sentry_event,
    _reset_sdk_for_tests,
)
from backend.adapters.telemetry.sanitizer import DeterministicTelemetrySanitizer
from backend.domain.shared_kernel import Severity
from backend.domain.telemetry import SanitizationState, TelemetryDeliveryStatus, TelemetryEventCandidate, TelemetrySubsystem


@pytest.fixture(autouse=True)
def reset_sentry_sdk() -> None:
    _reset_sdk_for_tests()
    yield
    _reset_sdk_for_tests()


@pytest.fixture
def sentry_dsn(monkeypatch: pytest.MonkeyPatch) -> str:
    dsn = "https://examplePublicKey@o0.ingest.sentry.io/0"
    monkeypatch.setenv("ATLAS_SENTRY_DSN", dsn)
    return dsn


def _candidate_payload(**overrides: object) -> dict:
    base = {
        "message": "Atlas failed at postgres://user:pass@127.0.0.1:5432/db",
        "exception": {"type": "RuntimeError", "value": "api_key=secret-token", "module": "backend"},
        "stacktrace": [{"filename": "C:\\Users\\Ryan\\Atlas\\backend\\service.py", "function": "run", "module": "backend", "lineno": 42}],
        "contexts": {"backend": {"component": "api"}},
        "tags": {"backend_subsystem": "backend"},
    }
    base.update(overrides)
    return base


def test_before_send_drops_project_data_fail_closed() -> None:
    sanitizer = DeterministicTelemetrySanitizer()
    decision = sanitizer.sanitize(
        TelemetryEventCandidate(
            event_type="atlas.backend.unhandled_exception",
            subsystem=TelemetrySubsystem.BACKEND,
            severity=Severity.ERROR,
            payload={"message": "FXServer resource log from C:\\servers\\rp\\resources\\bank\\server.cfg"},
        )
    )
    assert decision.state == SanitizationState.REJECTED

    event = _build_sentry_event(
        event_id="evt-1",
        event_type="atlas.backend.unhandled_exception",
        subsystem="backend",
        payload={"message": "FXServer resource log from C:\\servers\\rp\\resources\\bank\\server.cfg"},
    )
    assert _before_send(event, {}) is None


def test_before_send_redacts_secrets_in_accepted_event() -> None:
    sanitizer = DeterministicTelemetrySanitizer()
    raw_payload = _candidate_payload()
    decision = sanitizer.sanitize(
        TelemetryEventCandidate(
            event_type="atlas.backend.unhandled_exception",
            subsystem=TelemetrySubsystem.BACKEND,
            severity=Severity.ERROR,
            payload=raw_payload,
        )
    )
    assert decision.accepted
    sanitized_payload = decision.sanitized_payload or {}

    event = _build_sentry_event(
        event_id="evt-2",
        event_type="atlas.backend.unhandled_exception",
        subsystem="backend",
        payload=sanitized_payload,
    )
    filtered = _before_send(event, {})
    assert filtered is not None

    serialized = json.dumps(filtered)
    assert "postgres://user:pass" not in serialized
    assert "127.0.0.1" not in serialized
    assert "secret-token" not in serialized
    assert "C:\\Users\\Ryan" not in serialized
    assert filtered.get("request") is None
    assert filtered.get("user") is None


@patch("backend.adapters.telemetry.sentry_delivery.sentry_sdk.capture_event")
@patch("backend.adapters.telemetry.sentry_delivery.sentry_sdk.init")
def test_deliver_sends_scrubbed_event(mock_init: MagicMock, mock_capture: MagicMock, sentry_dsn: str) -> None:
    sanitizer = DeterministicTelemetrySanitizer()
    raw_payload = _candidate_payload()
    decision = sanitizer.sanitize(
        TelemetryEventCandidate(
            event_type="atlas.backend.unhandled_exception",
            subsystem=TelemetrySubsystem.BACKEND,
            severity=Severity.ERROR,
            payload=raw_payload,
        )
    )
    delivery = SentryTelemetryDelivery(sanitizer=sanitizer)
    status = delivery.deliver(
        "evt-3",
        decision.sanitized_payload or {},
        event_type="atlas.backend.unhandled_exception",
        subsystem="backend",
    )

    assert status == TelemetryDeliveryStatus.SUCCEEDED
    mock_init.assert_called_once()
    init_kwargs = mock_init.call_args.kwargs
    assert init_kwargs["send_default_pii"] is False
    assert init_kwargs["traces_sample_rate"] == 0.0
    assert init_kwargs["integrations"] == []
    assert init_kwargs["auto_enabling_integrations"] is False
    assert callable(init_kwargs["before_send"])

    mock_capture.assert_called_once()
    captured = mock_capture.call_args.args[0]
    serialized = json.dumps(captured)
    assert "postgres://user:pass" not in serialized
    assert "secret-token" not in serialized


@patch("backend.adapters.telemetry.sentry_delivery.sentry_sdk.capture_event")
@patch("backend.adapters.telemetry.sentry_delivery.sentry_sdk.init")
def test_deliver_drops_project_data_without_capture(mock_init: MagicMock, mock_capture: MagicMock, sentry_dsn: str) -> None:
    delivery = SentryTelemetryDelivery()
    status = delivery.deliver(
        "evt-4",
        {"message": "txAdmin resource log includes C:\\servers\\rp\\resources\\bank\\server.cfg"},
        event_type="atlas.backend.unhandled_exception",
        subsystem="backend",
    )

    assert status == TelemetryDeliveryStatus.FAILED
    mock_capture.assert_not_called()


def test_deliver_skipped_without_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ATLAS_SENTRY_DSN", raising=False)
    delivery = SentryTelemetryDelivery()
    status = delivery.deliver("evt-5", {"message": "safe"})
    assert status == TelemetryDeliveryStatus.SKIPPED
