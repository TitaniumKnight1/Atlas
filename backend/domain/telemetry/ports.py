from __future__ import annotations

from typing import Protocol

from backend.domain.telemetry.types import SanitizationDecision, TelemetryDeliveryStatus, TelemetryEventCandidate


class TelemetrySanitizerPort(Protocol):
    def sanitize(self, candidate: TelemetryEventCandidate) -> SanitizationDecision:
        """Return a sanitized event or fail-closed rejection without I/O."""


class TelemetryDeliveryPort(Protocol):
    def deliver(
        self,
        event_id: str,
        payload: dict[str, object],
        *,
        event_type: str = "atlas.backend.unhandled_exception",
        subsystem: str = "backend",
    ) -> TelemetryDeliveryStatus:
        """Deliver a previously sanitized event through the configured transport."""
