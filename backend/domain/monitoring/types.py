from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MetricSourceType(StrEnum):
    PROCESS = "process"
    RESOURCE = "resource"
    DISK = "disk"
    PLUGIN = "plugin"
    FIVEM = "fivem"


class MetricValueType(StrEnum):
    GAUGE = "gauge"
    COUNTER = "counter"
    STATUS = "status"


class MetricQuality(StrEnum):
    OK = "ok"
    ESTIMATED = "estimated"
    MISSING = "missing"


class RetentionClass(StrEnum):
    HIGH = "high"
    STANDARD = "standard"
    LONG = "long"


@dataclass(frozen=True, slots=True)
class CollectedMetricSample:
    source_type: str
    source_ref: str | None
    metric_name: str
    unit: str
    value_type: str
    value_real: float | None = None
    value_text: str | None = None
    quality: str = MetricQuality.OK.value
    deferred_reason: str | None = None
