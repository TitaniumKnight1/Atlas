from __future__ import annotations

from typing import Any

from backend.domain.monitoring import CollectedMetricSample, CollectorContext, MetricSourceType, MetricValueType


class ResourceHealthMetricCollector:
    """Consumes M5a resource health queries — does not rebuild inventory or graph logic."""

    collector_id = "resource-health"
    source_type = MetricSourceType.RESOURCE.value

    def __init__(self, resource_service: Any) -> None:
        self._resource_service = resource_service

    def collect(self, context: CollectorContext) -> list[CollectedMetricSample]:
        resources = self._resource_service.list_resources(context.project_id)
        counts = {"healthy": 0, "warning": 0, "error": 0, "unknown": 0}
        for resource in resources:
            health = self._resource_service.get_resource_health(context.project_id, resource["resource_id"])
            status = str(health.get("health_status", "unknown"))
            counts[status] = counts.get(status, 0) + 1
        return [
            CollectedMetricSample(
                source_type=MetricSourceType.RESOURCE.value,
                source_ref="inventory",
                metric_name="resource_count",
                unit="count",
                value_type=MetricValueType.GAUGE.value,
                value_real=float(len(resources)),
            ),
            *[
                CollectedMetricSample(
                    source_type=MetricSourceType.RESOURCE.value,
                    source_ref="inventory",
                    metric_name=f"resource_health_{name}_count",
                    unit="count",
                    value_type=MetricValueType.GAUGE.value,
                    value_real=float(count),
                )
                for name, count in counts.items()
            ],
        ]
