from __future__ import annotations

from backend.domain.monitoring import MetricCollectorPort


class MetricCollectorRegistry:
    """Pluggable collector seam deferred from ADR-0007 to M6."""

    def __init__(self) -> None:
        self._collectors: dict[str, MetricCollectorPort] = {}

    def register(self, collector: MetricCollectorPort) -> None:
        self._collectors[collector.collector_id] = collector

    def list_collectors(self) -> list[MetricCollectorPort]:
        return list(self._collectors.values())
