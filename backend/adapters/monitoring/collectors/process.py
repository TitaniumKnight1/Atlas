from __future__ import annotations

from backend.adapters.monitoring.platform_metrics import process_memory_mb
from backend.domain.monitoring import CollectedMetricSample, CollectorContext, MetricQuality, MetricSourceType, MetricValueType
from backend.domain.setup import ProcessPort


class SupervisedProcessMetricCollector:
    """Consumes M3b process status as a metric source — does not duplicate supervision."""

    collector_id = "supervised-process"
    source_type = MetricSourceType.PROCESS.value

    def __init__(self, process_port: ProcessPort) -> None:
        self._process_port = process_port

    def collect(self, context: CollectorContext) -> list[CollectedMetricSample]:
        if context.process_run_id is None:
            return [
                CollectedMetricSample(
                    source_type=MetricSourceType.PROCESS.value,
                    source_ref=None,
                    metric_name="process_state",
                    unit="status",
                    value_type=MetricValueType.STATUS.value,
                    value_text="absent",
                    quality=MetricQuality.MISSING.value,
                )
            ]
        status = self._process_port.status(context.process_run_id)
        if status is None:
            return []
        samples = [
            CollectedMetricSample(
                source_type=MetricSourceType.PROCESS.value,
                source_ref=context.process_run_id,
                metric_name="process_state",
                unit="status",
                value_type=MetricValueType.STATUS.value,
                value_text=status.state.value,
            ),
            CollectedMetricSample(
                source_type=MetricSourceType.PROCESS.value,
                source_ref=context.process_run_id,
                metric_name="process_up",
                unit="boolean",
                value_type=MetricValueType.GAUGE.value,
                value_real=1.0 if status.state.value == "running" else 0.0,
            ),
        ]
        if status.pid is not None:
            samples.append(
                CollectedMetricSample(
                    source_type=MetricSourceType.PROCESS.value,
                    source_ref=context.process_run_id,
                    metric_name="process_pid",
                    unit="pid",
                    value_type=MetricValueType.GAUGE.value,
                    value_real=float(status.pid),
                )
            )
            memory = process_memory_mb(int(status.pid))
            if memory is not None:
                samples.append(
                    CollectedMetricSample(
                        source_type=MetricSourceType.PROCESS.value,
                        source_ref=context.process_run_id,
                        metric_name="process_memory_mb",
                        unit="megabytes",
                        value_type=MetricValueType.GAUGE.value,
                        value_real=memory,
                    )
                )
        if status.exit_code is not None:
            samples.append(
                CollectedMetricSample(
                    source_type=MetricSourceType.PROCESS.value,
                    source_ref=context.process_run_id,
                    metric_name="process_exit_code",
                    unit="code",
                    value_type=MetricValueType.GAUGE.value,
                    value_real=float(status.exit_code),
                )
            )
        return samples
