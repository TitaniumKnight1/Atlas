from __future__ import annotations

from backend.domain.telemetry import TelemetryDeliveryStatus


class LocalNoopTelemetryDelivery:
    """No-network delivery adapter until the Sentry SDK is explicitly approved."""

    def deliver(
        self,
        event_id: str,
        payload: dict[str, object],
        *,
        event_type: str = "atlas.backend.unhandled_exception",
        subsystem: str = "backend",
    ) -> TelemetryDeliveryStatus:
        _ = (event_id, payload, event_type, subsystem)
        return TelemetryDeliveryStatus.SKIPPED
