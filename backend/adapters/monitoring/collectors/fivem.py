from __future__ import annotations

import httpx

from backend.domain.monitoring import CollectedMetricSample, CollectorContext, MetricQuality, MetricValueType


class FivemPlayerCountCollector:
    """Consumes FXServer's dynamic.json HTTP endpoint for live player count."""

    collector_id = "fivem-players"
    source_type = "fivem"

    def __init__(self, port: int = 30120, http_client: httpx.Client | None = None) -> None:
        self._port = port
        self._http_client = http_client or httpx.Client(timeout=2.0)

    def collect(self, context: CollectorContext) -> list[CollectedMetricSample]:
        if context.process_run_id is None:
            return [
                CollectedMetricSample(
                    source_type=self.source_type,
                    source_ref="server",
                    metric_name="player_count",
                    unit="players",
                    value_type=MetricValueType.GAUGE.value,
                    value_real=0.0,
                    quality=MetricQuality.MISSING.value,
                )
            ]

        try:
            response = self._http_client.get(f"http://127.0.0.1:{self._port}/dynamic.json")
            response.raise_for_status()
            data = response.json()
            clients = data.get("clients", 0)

            return [
                CollectedMetricSample(
                    source_type=self.source_type,
                    source_ref=context.process_run_id,
                    metric_name="player_count",
                    unit="players",
                    value_type=MetricValueType.GAUGE.value,
                    value_real=float(clients),
                )
            ]
        except (httpx.RequestError, httpx.HTTPStatusError, ValueError):
            return [
                CollectedMetricSample(
                    source_type=self.source_type,
                    source_ref=context.process_run_id,
                    metric_name="player_count",
                    unit="players",
                    value_type=MetricValueType.GAUGE.value,
                    value_real=0.0,
                    quality=MetricQuality.MISSING.value,
                )
            ]
