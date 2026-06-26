from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Literal


class AlertRuntimeState(StrEnum):
    OK = "ok"
    PENDING = "pending"
    FIRING = "firing"


class AlertEventKind(StrEnum):
    FIRED = "AlertFired"
    RESOLVED = "AlertResolved"


Comparator = Literal[">", ">=", "<", "<="]


@dataclass(frozen=True, slots=True)
class AlertCondition:
    metric_series_id: str
    comparator: Comparator
    threshold: float
    duration_seconds: int = 0


@dataclass(frozen=True, slots=True)
class AlertEvaluationInput:
    condition: AlertCondition
    runtime_state: AlertRuntimeState
    pending_since: datetime | None
    observed_value: float | None
    evaluated_at: datetime
    duration_satisfied: bool


@dataclass(frozen=True, slots=True)
class AlertStateTransition:
    next_state: AlertRuntimeState
    pending_since: datetime | None
    event_kind: AlertEventKind | None


def is_breaching(value: float, comparator: Comparator, threshold: float) -> bool:
    if comparator == ">":
        return value > threshold
    if comparator == ">=":
        return value >= threshold
    if comparator == "<":
        return value < threshold
    return value <= threshold


def evaluate_alert_state(input_data: AlertEvaluationInput) -> AlertStateTransition:
    """Pure alert state machine — at most one fire and one resolve per breach cycle."""
    now = input_data.evaluated_at
    breaching = (
        input_data.observed_value is not None
        and is_breaching(input_data.observed_value, input_data.condition.comparator, input_data.condition.threshold)
    )
    state = input_data.runtime_state
    pending_since = input_data.pending_since

    if state == AlertRuntimeState.FIRING:
        if breaching:
            return AlertStateTransition(AlertRuntimeState.FIRING, pending_since, None)
        return AlertStateTransition(AlertRuntimeState.OK, None, AlertEventKind.RESOLVED)

    if breaching and input_data.duration_satisfied:
        return AlertStateTransition(AlertRuntimeState.FIRING, None, AlertEventKind.FIRED)

    if breaching:
        started = pending_since or now
        return AlertStateTransition(AlertRuntimeState.PENDING, started, None)

    if state == AlertRuntimeState.PENDING:
        return AlertStateTransition(AlertRuntimeState.OK, None, None)
    return AlertStateTransition(AlertRuntimeState.OK, None, None)


def sustained_breach_holds(
    samples: list[tuple[datetime, float]],
    *,
    condition: AlertCondition,
    window_end: datetime,
) -> bool:
    """True when every sample in the duration window breaches the threshold."""
    if condition.duration_seconds <= 0:
        return True
    window_start = window_end - timedelta(seconds=condition.duration_seconds)
    in_window = [(ts, value) for ts, value in samples if window_start <= ts <= window_end]
    if not in_window:
        return False
    return all(is_breaching(value, condition.comparator, condition.threshold) for _, value in in_window)


def compute_duration_satisfied(
    *,
    condition: AlertCondition,
    breaching: bool,
    pending_since: datetime | None,
    evaluated_at: datetime,
    recent_samples: list[tuple[datetime, float]],
) -> bool:
    if not breaching:
        return False
    if condition.duration_seconds <= 0:
        return True
    if pending_since is None:
        return False
    if evaluated_at - pending_since < timedelta(seconds=condition.duration_seconds):
        return False
    return sustained_breach_holds(recent_samples, condition=condition, window_end=evaluated_at)
