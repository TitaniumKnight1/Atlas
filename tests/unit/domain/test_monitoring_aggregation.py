from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.domain.monitoring.aggregation import (
    HOUR_BUCKET_SECONDS,
    MINUTE_BUCKET_SECONDS,
    MetricAggregate,
    aggregate_raw_values,
    bucket_end,
    compose_aggregates,
    floor_to_bucket,
)


def test_aggregate_raw_values_computes_min_max_avg_count() -> None:
    start = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    aggregate = aggregate_raw_values([10.0, 20.0, 30.0], bucket_start=start, bucket_size_seconds=MINUTE_BUCKET_SECONDS)
    assert aggregate is not None
    assert aggregate.min_value == 10.0
    assert aggregate.max_value == 30.0
    assert aggregate.sample_count == 3
    assert aggregate.avg_value == 20.0
    assert aggregate.sum_value == 60.0
    assert aggregate.bucket_start == start
    assert aggregate.bucket_end == start + timedelta(seconds=MINUTE_BUCKET_SECONDS)


def test_aggregate_raw_values_ignores_non_finite() -> None:
    start = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    aggregate = aggregate_raw_values([1.0, float("nan"), float("inf")], bucket_start=start, bucket_size_seconds=MINUTE_BUCKET_SECONDS)
    assert aggregate is not None
    assert aggregate.min_value == 1.0
    assert aggregate.max_value == 1.0
    assert aggregate.sample_count == 1


def test_compose_aggregates_uses_min_of_mins_max_of_maxes_weighted_avg() -> None:
    hour_start = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    minute_start = hour_start
    lower = [
        MetricAggregate(1.0, 5.0, 6.0, 2, minute_start, minute_start + timedelta(seconds=MINUTE_BUCKET_SECONDS)),
        MetricAggregate(3.0, 10.0, 26.0, 2, minute_start + timedelta(minutes=1), minute_start + timedelta(minutes=2)),
    ]
    composed = compose_aggregates(lower, bucket_start=hour_start, bucket_size_seconds=HOUR_BUCKET_SECONDS)
    assert composed is not None
    assert composed.min_value == 1.0
    assert composed.max_value == 10.0
    assert composed.sample_count == 4
    assert composed.sum_value == 32.0
    assert composed.avg_value == 8.0


def test_compose_aggregates_preserves_spike_peak() -> None:
    hour_start = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    lower = [
        MetricAggregate(1.0, 2.0, 1.5, 1, hour_start, hour_start + timedelta(seconds=MINUTE_BUCKET_SECONDS)),
        MetricAggregate(2.0, 100.0, 51.0, 1, hour_start + timedelta(minutes=1), hour_start + timedelta(minutes=2)),
    ]
    composed = compose_aggregates(lower, bucket_start=hour_start, bucket_size_seconds=HOUR_BUCKET_SECONDS)
    assert composed is not None
    assert composed.max_value == 100.0
    assert composed.avg_value != composed.max_value


def test_floor_to_bucket_aligns_minute_and_hour() -> None:
    ts = datetime(2026, 1, 1, 12, 34, 56, tzinfo=UTC)
    assert floor_to_bucket(ts, MINUTE_BUCKET_SECONDS) == datetime(2026, 1, 1, 12, 34, 0, tzinfo=UTC)
    assert floor_to_bucket(ts, HOUR_BUCKET_SECONDS) == datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def test_bucket_end_matches_size() -> None:
    start = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    assert bucket_end(start, MINUTE_BUCKET_SECONDS) == start + timedelta(seconds=60)


@pytest.mark.parametrize(
    ("values", "expected_min", "expected_max", "expected_avg"),
    [
        ([5.0], 5.0, 5.0, 5.0),
        ([1.0, 9.0], 1.0, 9.0, 5.0),
        ([2.0, 4.0, 6.0, 8.0], 2.0, 8.0, 5.0),
    ],
)
def test_aggregate_raw_values_matches_direct_truth(values: list[float], expected_min: float, expected_max: float, expected_avg: float) -> None:
    start = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
    aggregate = aggregate_raw_values(values, bucket_start=start, bucket_size_seconds=MINUTE_BUCKET_SECONDS)
    assert aggregate is not None
    assert aggregate.min_value == expected_min
    assert aggregate.max_value == expected_max
    assert aggregate.avg_value == expected_avg
    assert aggregate.sample_count == len(values)
