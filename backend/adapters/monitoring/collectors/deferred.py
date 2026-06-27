from __future__ import annotations

from backend.domain.monitoring import CollectedMetricSample, CollectorContext, MetricQuality, MetricSourceType, MetricValueType

DEFERRED_METRICS: tuple[tuple[str, str, str], ...] = (
    (MetricSourceType.PROCESS.value, "server_fps", "deferred-by-cost — needs resource injection/txAdmin"),
)


class DeferredServerMetricCollector:
    collector_id = "deferred-server-introspection"
    source_type = "deferred"

    def collect(self, context: CollectorContext) -> list[CollectedMetricSample]:
        return [
            CollectedMetricSample(
                source_type=source_type,
                source_ref=context.process_run_id,
                metric_name=metric_name,
                unit="unknown",
                value_type=MetricValueType.GAUGE.value,
                quality=MetricQuality.MISSING.value,
                deferred_reason=reason,
            )
            for source_type, metric_name, reason in DEFERRED_METRICS
        ]
