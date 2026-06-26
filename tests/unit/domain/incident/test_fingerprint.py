from __future__ import annotations

from backend.domain.incident.fingerprint import compute_fingerprint, normalize_text
from backend.domain.incident.grouping import ExistingIncidentGroup, GroupingAction, decide_grouping, merge_group_timestamps
from backend.domain.incident.signals import FingerprintSignals


def _signals(
    *,
    exit_code: int | None = 7,
    message: str = "Server process exited unexpectedly with code 7",
    log_lines: tuple[str, ...] = ("CRASHING", "Error: script failure"),
    resource_hint: str | None = None,
) -> FingerprintSignals:
    return FingerprintSignals(
        category="crash",
        severity="fatal",
        source_type="process",
        exit_code=exit_code,
        exception_type=None,
        normalized_message=message,
        log_lines=log_lines,
        resource_hint=resource_hint,
    )


def test_identical_crashes_produce_same_fingerprint() -> None:
    first = compute_fingerprint(_signals())
    second = compute_fingerprint(_signals())
    assert first.fingerprint == second.fingerprint


def test_variable_timestamps_normalize_to_same_fingerprint() -> None:
    first = compute_fingerprint(_signals(log_lines=("2024-01-01T12:00:00Z CRASHING",)))
    second = compute_fingerprint(_signals(log_lines=("2026-06-26T17:00:00+00:00 CRASHING",)))
    assert first.fingerprint == second.fingerprint


def test_variable_paths_normalize_to_same_fingerprint() -> None:
    first = compute_fingerprint(_signals(log_lines=(r"C:\Users\Ryan\server\resources\alpha\main.lua error",)))
    second = compute_fingerprint(_signals(log_lines=("/home/user/server/resources/alpha/main.lua error",)))
    assert first.fingerprint == second.fingerprint


def test_variable_pids_and_ports_normalize_to_same_fingerprint() -> None:
    first = compute_fingerprint(_signals(log_lines=("pid 12345 listening on :30120",)))
    second = compute_fingerprint(_signals(log_lines=("pid 98765 listening on :40120",)))
    assert first.fingerprint == second.fingerprint


def test_different_exit_codes_produce_different_fingerprints() -> None:
    first = compute_fingerprint(_signals(exit_code=7))
    second = compute_fingerprint(_signals(exit_code=9))
    assert first.fingerprint != second.fingerprint


def test_different_log_content_produces_different_fingerprints() -> None:
    first = compute_fingerprint(_signals(log_lines=("Error: out of memory",)))
    second = compute_fingerprint(_signals(log_lines=("Error: could not load asset",)))
    assert first.fingerprint != second.fingerprint


def test_secret_bearing_line_not_present_in_fingerprint_or_components() -> None:
    secret = "supersecret-token-value-12345"
    result = compute_fingerprint(_signals(log_lines=(f"discord_token={secret}",)))
    payload = str(result.components)
    assert secret not in result.fingerprint
    assert secret not in payload
    redacted = compute_fingerprint(_signals(log_lines=("discord_token=<secret>",)))
    assert result.fingerprint == redacted.fingerprint


def test_normalize_text_strips_hashes_and_ids() -> None:
    raw = "process 12345678 at C:\\tmp\\run.pid=44221 hash deadbeef0123456789abcdef01234567"
    normalized = normalize_text(raw)
    assert "12345678" not in normalized
    assert "deadbeef0123456789abcdef01234567" not in normalized
    assert "C:\\tmp\\run" not in normalized


def test_decide_grouping_matches_existing_group() -> None:
    existing = ExistingIncidentGroup(
        incident_group_id="group-1",
        fingerprint="abc",
        occurrence_count=2,
        first_seen_at="2026-01-01T00:00:00+00:00",
        last_seen_at="2026-01-02T00:00:00+00:00",
    )
    decision = decide_grouping("abc", existing)
    assert decision.action == GroupingAction.MATCH_EXISTING
    assert decision.incident_group_id == "group-1"


def test_decide_grouping_creates_new_when_no_match() -> None:
    decision = decide_grouping("abc", None)
    assert decision.action == GroupingAction.CREATE_NEW


def test_merge_group_timestamps_accounts_for_new_occurrence() -> None:
    first, last, count = merge_group_timestamps(
        existing_first_seen_at="2026-01-02T00:00:00+00:00",
        existing_last_seen_at="2026-01-03T00:00:00+00:00",
        existing_count=2,
        occurrence_at="2026-01-01T00:00:00+00:00",
    )
    assert first == "2026-01-01T00:00:00+00:00"
    assert last == "2026-01-03T00:00:00+00:00"
    assert count == 3
