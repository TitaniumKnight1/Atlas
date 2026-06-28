from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from backend.adapters.persistence.models import (
    AuditEventRecord,
    CommandExecutionRecord,
    DomainEventRecord,
    TelemetryDeliveryAttemptRecord,
    TelemetryQueueRecord,
    TelemetryRejectionRecord,
    TelemetrySanitizationResultRecord,
)
from backend.application.telemetry import TelemetryApplicationError
from backend.domain.shared_kernel import Severity
from backend.domain.telemetry import TelemetryEventCandidate, TelemetrySubsystem
from backend.infrastructure.di import create_application_container


def test_preferences_default_disabled_and_updates_are_audited(tmp_path: Path) -> None:
    container = create_application_container(tmp_path / "app-data")
    try:
        service = container.create_telemetry_service()
        default = service.get_preferences()
        assert default["telemetry_enabled"] is False
        assert default["crash_reporting_enabled"] is False
        assert default["plugin_telemetry_enabled"] is False
        assert default["error_reporting_available"] is False
        assert default["consent_prompt_pending"] is False

        result = service.execute_update_preferences(
            patch={"telemetry_enabled": True, "crash_reporting_enabled": True},
            updated_by="test-user",
        )

        assert result.command_type == "UpdateTelemetryPreferences"
        assert service.get_preferences()["telemetry_enabled"] is True
        assert _count(container, CommandExecutionRecord) == 1
        assert _count(container, AuditEventRecord) == 1
        assert _domain_event_types(container) == ["TelemetryPreferencesUpdated"]
    finally:
        container.close()


def test_disabled_capture_records_rejection_and_queues_nothing(tmp_path: Path) -> None:
    container = create_application_container(tmp_path / "app-data")
    try:
        service = container.create_telemetry_service()

        with pytest.raises(TelemetryApplicationError):
            service.queue_event(_candidate({"message": "Atlas crashed with safe local-only summary"}))

        assert _count(container, TelemetryQueueRecord) == 0
        assert _count(container, TelemetryRejectionRecord) == 1
        assert _count(container, TelemetrySanitizationResultRecord) == 1
        rejection = _records(container, TelemetryRejectionRecord)[0]
        assert rejection.rejection_reason == "disabled"
        assert "Atlas crashed" not in json.dumps(rejection.summary_json)
    finally:
        container.close()


def test_enabled_capture_queues_sanitized_payload_and_noop_attempt(tmp_path: Path) -> None:
    container = create_application_container(tmp_path / "app-data")
    try:
        service = container.create_telemetry_service()
        service.execute_update_preferences(patch={"telemetry_enabled": True, "crash_reporting_enabled": True})

        queued = service.queue_event(
            _candidate(
                {
                    "message": "Atlas failed at postgres://user:pass@127.0.0.1:5432/db with steam:110000112345678",
                    "exception": {"type": "RuntimeError", "value": "api_key=secret-token", "module": "backend"},
                    "stacktrace": [{"filename": "C:\\Users\\Ryan\\Atlas\\backend\\service.py", "function": "run", "module": "backend", "lineno": 42}],
                    "contexts": {"backend": {"component": "api"}},
                    "tags": {"backend_subsystem": "backend"},
                }
            )
        )

        assert queued["status"] == "queued"
        assert queued["delivery_status"] == "skipped"
        assert _count(container, TelemetryQueueRecord) == 1
        assert _count(container, TelemetryDeliveryAttemptRecord) == 1
        assert _count(container, TelemetryRejectionRecord) == 0
        event = _records(container, TelemetryQueueRecord)[0]
        serialized = json.dumps(event.event_payload_json, sort_keys=True)
        assert "postgres://user:pass" not in serialized
        assert "127.0.0.1" not in serialized
        assert "steam:110000112345678" not in serialized
        assert "secret-token" not in serialized
        assert "C:\\Users\\Ryan" not in serialized
    finally:
        container.close()


def test_project_data_rejection_never_stores_raw_payload(tmp_path: Path) -> None:
    container = create_application_container(tmp_path / "app-data")
    try:
        service = container.create_telemetry_service()
        service.execute_update_preferences(patch={"telemetry_enabled": True, "crash_reporting_enabled": True})

        with pytest.raises(TelemetryApplicationError):
            service.queue_event(_candidate({"message": "txAdmin resource log includes C:\\servers\\rp\\resources\\bank\\server.cfg"}))

        assert _count(container, TelemetryQueueRecord) == 0
        rejection = _records(container, TelemetryRejectionRecord)[0]
        assert rejection.rejection_reason == "contains_project_data"
        serialized = json.dumps(rejection.summary_json, sort_keys=True)
        assert "C:\\servers\\rp" not in serialized
        assert "bank" not in serialized
        assert "server.cfg" not in serialized
    finally:
        container.close()


def test_consent_prompt_state_with_dsn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_SENTRY_DSN", "https://examplePublicKey@o0.ingest.sentry.io/0")
    container = create_application_container(tmp_path / "app-data")
    try:
        service = container.create_telemetry_service()
        prefs = service.get_preferences()
        assert prefs["error_reporting_available"] is True
        assert prefs["consent_prompt_pending"] is True

        service.execute_update_preferences(
            patch={"telemetry_enabled": False, "crash_reporting_enabled": False},
            record_consent_prompt_shown=True,
            updated_by="test-user",
        )
        after = service.get_preferences()
        assert after["consent_prompt_pending"] is False
        assert after["last_prompted_at"] is not None
    finally:
        container.close()


def _candidate(payload: dict) -> TelemetryEventCandidate:
    return TelemetryEventCandidate(
        event_type="atlas.backend.unhandled_exception",
        subsystem=TelemetrySubsystem.BACKEND,
        severity=Severity.ERROR,
        payload=payload,
    )


def _count(container, model: type) -> int:
    return len(_records(container, model))


def _records(container, model: type):
    with container.session_factory() as session:
        return list(session.execute(select(model)).scalars())


def _domain_event_types(container) -> list[str]:
    return [record.event_type for record in _records(container, DomainEventRecord)]
