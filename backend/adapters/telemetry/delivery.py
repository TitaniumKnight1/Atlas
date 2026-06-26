from __future__ import annotations

from backend.domain.telemetry import TelemetryDeliveryStatus


class LocalNoopTelemetryDelivery:
    """No-network delivery adapter until the Sentry SDK is explicitly approved."""

    def deliver(self, event_id: str, payload: dict[str, object]) -> TelemetryDeliveryStatus:
        _ = (event_id, payload)
        return TelemetryDeliveryStatus.SKIPPED
