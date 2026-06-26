from __future__ import annotations

from backend.adapters.monitoring.platform_metrics import disk_usage_percent, system_memory_percent
from backend.domain.monitoring import CollectedMetricSample, CollectorContext, MetricQuality, MetricSourceType, MetricValueType


class SystemMetricCollector:
    collector_id = "system"
    source_type = MetricSourceType.DISK.value

    def collect(self, context: CollectorContext) -> list[CollectedMetricSample]:
        samples: list[CollectedMetricSample] = []
        if context.project_root is not None:
            disk = disk_usage_percent(context.project_root)
            if disk is not None:
                used_percent, free_gb = disk
                samples.append(
                    CollectedMetricSample(
                        source_type=MetricSourceType.DISK.value,
                        source_ref=str(context.project_root),
                        metric_name="disk_used_percent",
                        unit="percent",
                        value_type=MetricValueType.GAUGE.value,
                        value_real=used_percent,
                    )
                )
                samples.append(
                    CollectedMetricSample(
                        source_type=MetricSourceType.DISK.value,
                        source_ref=str(context.project_root),
                        metric_name="disk_free_gb",
                        unit="gigabytes",
                        value_type=MetricValueType.GAUGE.value,
                        value_real=free_gb,
                    )
                )
        memory = system_memory_percent()
        if memory is not None:
            samples.append(
                CollectedMetricSample(
                    source_type="system",
                    source_ref="host",
                    metric_name="memory_used_percent",
                    unit="percent",
                    value_type=MetricValueType.GAUGE.value,
                    value_real=memory,
                )
            )
        samples.append(
            CollectedMetricSample(
                source_type="system",
                source_ref="host",
                metric_name="cpu_used_percent",
                unit="percent",
                value_type=MetricValueType.GAUGE.value,
                quality=MetricQuality.MISSING.value,
                deferred_reason="deferred — host CPU sampling needs platform-specific counters; psutil not added in M6a",
            )
        )
        return samples
