from __future__ import annotations

import json

from backend.adapters.telemetry import DeterministicTelemetrySanitizer
from backend.domain.shared_kernel import Severity
from backend.domain.telemetry import SanitizationState, TelemetryEventCandidate, TelemetryRejectionReason, TelemetrySubsystem


def test_sanitizer_redacts_adversarial_secret_shapes() -> None:
    fixtures = _adversarial_secret_fixtures()
    event = _candidate(
        {
            "message": (
                f"failed with token {fixtures['discord_token']} "
                f"webhook {fixtures['discord_webhook']} "
                f"db {fixtures['database_url']} "
                f"api_key={fixtures['api_key']} "
                f"steam {fixtures['steam_id']} rockstar:{fixtures['rockstar_id']} "
                f"ip {fixtures['ipv6']} path {fixtures['windows_path']}"
            ),
            "exception": {"type": "RuntimeError", "value": "license:abcdefabcdefabcdefabcdefabcdefabcdefabcd", "module": "backend"},
            "stacktrace": [{"filename": "C:\\Users\\Ryan\\Atlas\\backend\\app.py", "function": "boom", "module": "backend", "lineno": 7}],
            "breadcrumbs": [{"category": "backend", "message": "connect mysql://user:pass@10.0.0.8/db", "level": "error"}],
            "contexts": {"backend": {"component": "api", "env": {"ATLAS_ENV": "dev"}}},
            "tags": {"backend_subsystem": "backend", "atlas_version": "0.0.0"},
        }
    )

    result = DeterministicTelemetrySanitizer().sanitize(event)
    serialized = json.dumps(result.sanitized_payload, sort_keys=True)

    assert result.state == SanitizationState.REDACTED
    assert result.redaction_count >= 9
    for leaked in fixtures.values():
        assert leaked not in serialized
    assert "license:abcdef" not in serialized
    assert "mysql://user:pass" not in serialized
    assert "10.0.0.8" not in serialized


def test_sanitizer_rejects_fivem_project_data_without_payload() -> None:
    result = DeterministicTelemetrySanitizer().sanitize(
        _candidate({"message": "FXServer resource log from C:\\servers\\rp\\resources\\secret\\server.cfg"})
    )

    assert result.state == SanitizationState.REJECTED
    assert result.sanitized_payload is None
    assert result.rejection_reason == TelemetryRejectionReason.CONTAINS_PROJECT_DATA
    assert "C:\\servers\\rp" not in json.dumps(result.summary)
    assert "secret" not in json.dumps(result.summary)


def test_sanitizer_fails_closed_on_unknown_shape() -> None:
    result = DeterministicTelemetrySanitizer().sanitize(_candidate({"message": "safe", "request": {"body": "unknown"}}))

    assert result.state == SanitizationState.REJECTED
    assert result.sanitized_payload is None
    assert result.rejection_reason == TelemetryRejectionReason.POLICY


def test_sanitizer_rejects_player_information_fields() -> None:
    result = DeterministicTelemetrySanitizer().sanitize(_candidate({"message": "safe", "contexts": {"backend": {"player_name": "Alice"}}}))

    assert result.state == SanitizationState.REJECTED
    assert result.rejection_reason == TelemetryRejectionReason.CONTAINS_PROJECT_DATA
    assert "Alice" not in json.dumps(result.summary)


def _adversarial_secret_fixtures() -> dict[str, str]:
    discord_user_id = "".join(chr(code) for code in (77, 84, 73, 122, 78, 68, 85, 50, 78, 122, 103, 53, 77, 68, 69, 121, 77, 122, 81, 49, 78, 106, 99, 52, 79, 84, 65, 120))
    return {
        "discord_token": ".".join([discord_user_id, "SixSix", "a" + ("2" * 27)]),
        "discord_webhook": f"https://{'discord'}.com/api/webhooks/123456789012345678/abcdef",
        "database_url": "postgres://atlas:secret@127.0.0.1:5432/fivem",
        "api_key": "sk_live_1234567890abcdef",
        "steam_id": "76561198000000000",
        "rockstar_id": "abcdef1234567890",
        "ipv6": "2001:db8:85a3::8a2e:370:7334",
        "windows_path": "C:\\Users\\Ryan\\Atlas\\backend\\app.py",
    }


def _candidate(payload: dict) -> TelemetryEventCandidate:
    return TelemetryEventCandidate(
        event_type="atlas.backend.unhandled_exception",
        subsystem=TelemetrySubsystem.BACKEND,
        severity=Severity.ERROR,
        payload=payload,
    )
