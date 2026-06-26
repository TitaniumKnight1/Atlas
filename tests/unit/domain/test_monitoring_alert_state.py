from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.domain.monitoring.alert_state import (
    AlertCondition,
    AlertEvaluationInput,
    AlertEventKind,
    AlertRuntimeState,
    compute_duration_satisfied,
    evaluate_alert_state,
    sustained_breach_holds,
)


def _condition(duration: int = 0) -> AlertCondition:
    return AlertCondition(metric_series_id="series-1", comparator=">", threshold=80.0, duration_seconds=duration)


def _input(
    *,
    state: AlertRuntimeState,
    value: float | None,
    duration_satisfied: bool,
    pending_since: datetime | None = None,
    at: datetime | None = None,
) -> AlertEvaluationInput:
    return AlertEvaluationInput(
        condition=_condition(),
        runtime_state=state,
        pending_since=pending_since,
        observed_value=value,
        evaluated_at=at or datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
        duration_satisfied=duration_satisfied,
    )


def test_ok_to_firing_emits_one_alert_fired_immediate() -> None:
    transition = evaluate_alert_state(_input(state=AlertRuntimeState.OK, value=90.0, duration_satisfied=True))
    assert transition.next_state == AlertRuntimeState.FIRING
    assert transition.event_kind == AlertEventKind.FIRED


def test_firing_to_firing_emits_no_event() -> None:
    transition = evaluate_alert_state(_input(state=AlertRuntimeState.FIRING, value=95.0, duration_satisfied=True))
    assert transition.next_state == AlertRuntimeState.FIRING
    assert transition.event_kind is None


def test_firing_to_ok_emits_one_alert_resolved() -> None:
    transition = evaluate_alert_state(_input(state=AlertRuntimeState.FIRING, value=50.0, duration_satisfied=False))
    assert transition.next_state == AlertRuntimeState.OK
    assert transition.event_kind == AlertEventKind.RESOLVED


def test_sustained_breach_enters_pending_without_event() -> None:
    transition = evaluate_alert_state(_input(state=AlertRuntimeState.OK, value=90.0, duration_satisfied=False))
    assert transition.next_state == AlertRuntimeState.PENDING
    assert transition.event_kind is None
    assert transition.pending_since is not None


def test_pending_to_firing_after_duration_satisfied() -> None:
    started = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    transition = evaluate_alert_state(
        _input(state=AlertRuntimeState.PENDING, value=90.0, duration_satisfied=True, pending_since=started)
    )
    assert transition.next_state == AlertRuntimeState.FIRING
    assert transition.event_kind == AlertEventKind.FIRED


def test_pending_flapping_returns_to_ok_without_event() -> None:
    started = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    transition = evaluate_alert_state(
        _input(state=AlertRuntimeState.PENDING, value=50.0, duration_satisfied=False, pending_since=started)
    )
    assert transition.next_state == AlertRuntimeState.OK
    assert transition.event_kind is None


def test_sustained_breach_holds_requires_all_samples_in_window() -> None:
    condition = _condition(duration=60)
    end = datetime(2026, 6, 1, 12, 1, tzinfo=UTC)
    samples = [
        (end - timedelta(seconds=50), 90.0),
        (end - timedelta(seconds=10), 90.0),
    ]
    assert sustained_breach_holds(samples, condition=condition, window_end=end) is True
    spike_samples = [
        (end - timedelta(seconds=50), 90.0),
        (end - timedelta(seconds=10), 50.0),
    ]
    assert sustained_breach_holds(spike_samples, condition=condition, window_end=end) is False


def test_compute_duration_satisfied_immediate_mode() -> None:
    condition = _condition(duration=0)
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    assert (
        compute_duration_satisfied(
            condition=condition,
            breaching=True,
            pending_since=None,
            evaluated_at=now,
            recent_samples=[],
        )
        is True
    )


def test_compute_duration_satisfied_requires_window_persistence() -> None:
    condition = _condition(duration=60)
    now = datetime(2026, 6, 1, 12, 2, tzinfo=UTC)
    started = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    recent = [(started + timedelta(seconds=10), 90.0), (now, 90.0)]
    assert (
        compute_duration_satisfied(
            condition=condition,
            breaching=True,
            pending_since=started,
            evaluated_at=now,
            recent_samples=recent,
        )
        is True
    )
    spike_recent = [(started + timedelta(seconds=10), 90.0), (now, 50.0)]
    assert (
        compute_duration_satisfied(
            condition=condition,
            breaching=True,
            pending_since=started,
            evaluated_at=now,
            recent_samples=spike_recent,
        )
        is False
    )


@pytest.mark.parametrize("value", [90.0, 95.0, 100.0])
def test_repeated_firing_evaluations_never_re_emit(value: float) -> None:
    for _ in range(5):
        transition = evaluate_alert_state(_input(state=AlertRuntimeState.FIRING, value=value, duration_satisfied=True))
        assert transition.event_kind is None
