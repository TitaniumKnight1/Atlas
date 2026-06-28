from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import select

from backend.adapters.persistence.models import TelemetryDeliveryAttemptRecord, TelemetryQueueRecord
from backend.application.telemetry import TelemetryApplicationError
from backend.domain.shared_kernel import Severity
from backend.domain.telemetry import TelemetryEventCandidate, TelemetrySubsystem
from backend.infrastructure.di import create_application_container


def test_sentry_delivery_scrubs_secrets_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_SENTRY_DSN", "https://examplePublicKey@o0.ingest.sentry.io/0")
    container = create_application_container(tmp_path / "app-data")
    try:
        service = container.create_telemetry_service()
        service.execute_update_preferences(patch={"telemetry_enabled": True, "crash_reporting_enabled": True})

        with patch("backend.adapters.telemetry.sentry_delivery.sentry_sdk.capture_event") as mock_capture:
            with patch("backend.adapters.telemetry.sentry_delivery.sentry_sdk.init"):
                queued = service.queue_event(
                    TelemetryEventCandidate(
                        event_type="atlas.backend.unhandled_exception",
                        subsystem=TelemetrySubsystem.BACKEND,
                        severity=Severity.ERROR,
                        payload={
                            "message": "Atlas failed at postgres://user:pass@127.0.0.1:5432/db",
                            "exception": {"type": "RuntimeError", "value": "api_key=secret-token", "module": "backend"},
                            "stacktrace": [{"filename": "C:\\Users\\Ryan\\Atlas\\backend\\service.py", "function": "run", "module": "backend", "lineno": 42}],
                            "contexts": {"backend": {"component": "api"}},
                            "tags": {"backend_subsystem": "backend"},
                        },
                    )
                )

        assert queued["delivery_status"] == "succeeded"
        mock_capture.assert_called_once()
        serialized = json.dumps(mock_capture.call_args.args[0])
        assert "postgres://user:pass" not in serialized
        assert "secret-token" not in serialized
        assert "127.0.0.1" not in serialized
    finally:
        container.close()


def test_sentry_disabled_by_default_even_with_dsn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_SENTRY_DSN", "https://examplePublicKey@o0.ingest.sentry.io/0")
    container = create_application_container(tmp_path / "app-data")
    try:
        service = container.create_telemetry_service()
        with pytest.raises(TelemetryApplicationError):
            service.queue_event(
                TelemetryEventCandidate(
                    event_type="atlas.backend.unhandled_exception",
                    subsystem=TelemetrySubsystem.BACKEND,
                    severity=Severity.ERROR,
                    payload={"message": "safe"},
                )
            )
        assert _count(container, TelemetryQueueRecord) == 0
    finally:
        container.close()


def _count(container, model: type) -> int:
    with container.session_factory() as session:
        return len(list(session.execute(select(model)).scalars()))
