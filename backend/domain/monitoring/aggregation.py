from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import isfinite


MINUTE_BUCKET_SECONDS = 60
HOUR_BUCKET_SECONDS = 3600


@dataclass(frozen=True, slots=True)
class MetricAggregate:
    min_value: float | None
    max_value: float | None
    sum_value: float
    sample_count: int
    bucket_start: datetime
    bucket_end: datetime

    @property
    def avg_value(self) -> float | None:
        if self.sample_count <= 0:
            return None
        return self.sum_value / self.sample_count


def floor_to_bucket(timestamp: datetime, bucket_size_seconds: int) -> datetime:
    normalized = timestamp.astimezone(UTC).replace(microsecond=0)
    if bucket_size_seconds == MINUTE_BUCKET_SECONDS:
        return normalized.replace(second=0)
    if bucket_size_seconds == HOUR_BUCKET_SECONDS:
        return normalized.replace(minute=0, second=0)
    epoch_seconds = int(normalized.timestamp())
    aligned = epoch_seconds - (epoch_seconds % bucket_size_seconds)
    return datetime.fromtimestamp(aligned, tz=UTC)


def bucket_end(bucket_start: datetime, bucket_size_seconds: int) -> datetime:
    return bucket_start + timedelta(seconds=bucket_size_seconds)


def aggregate_raw_values(
    values: list[float],
    *,
    bucket_start: datetime,
    bucket_size_seconds: int,
) -> MetricAggregate | None:
    numeric = [value for value in values if isfinite(value)]
    if not numeric:
        return None
    start = floor_to_bucket(bucket_start, bucket_size_seconds)
    end = bucket_end(start, bucket_size_seconds)
    return MetricAggregate(
        min_value=min(numeric),
        max_value=max(numeric),
        sum_value=sum(numeric),
        sample_count=len(numeric),
        bucket_start=start,
        bucket_end=end,
    )


def compose_aggregates(
    aggregates: list[MetricAggregate],
    *,
    bucket_start: datetime,
    bucket_size_seconds: int,
) -> MetricAggregate | None:
    if not aggregates:
        return None
    mins = [item.min_value for item in aggregates if item.min_value is not None]
    maxes = [item.max_value for item in aggregates if item.max_value is not None]
    total_count = sum(item.sample_count for item in aggregates)
    if total_count <= 0:
        return None
    start = floor_to_bucket(bucket_start, bucket_size_seconds)
    end = bucket_end(start, bucket_size_seconds)
    return MetricAggregate(
        min_value=min(mins) if mins else None,
        max_value=max(maxes) if maxes else None,
        sum_value=sum(item.sum_value for item in aggregates),
        sample_count=total_count,
        bucket_start=start,
        bucket_end=end,
    )


def aggregate_to_payload(aggregate: MetricAggregate) -> dict[str, float | int | str | None]:
    return {
        "min_value": aggregate.min_value,
        "max_value": aggregate.max_value,
        "avg_value": aggregate.avg_value,
        "sum_value": aggregate.sum_value,
        "sample_count": aggregate.sample_count,
        "bucket_start": aggregate.bucket_start.isoformat(),
        "bucket_end": aggregate.bucket_end.isoformat(),
    }
