from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from backend.adapters.telemetry.delivery import LocalNoopTelemetryDelivery
from backend.adapters.telemetry.sentry_delivery import SentryTelemetryDelivery
from backend.adapters.persistence.telemetry_repository import preference_record_to_domain
from backend.domain.telemetry import TelemetryDeliveryPort, TelemetryDeliveryStatus, TelemetryPreferences, TelemetrySanitizerPort, TelemetrySubsystem
from backend.infrastructure.sentry_dsn import resolve_sentry_dsn


class PreferenceGatedTelemetryDelivery:
    """Routes to Sentry only when telemetry preferences allow and a DSN is configured."""

    def __init__(
        self,
        *,
        get_preferences: Callable[[], TelemetryPreferences],
        sentry_delivery: SentryTelemetryDelivery,
        noop_delivery: LocalNoopTelemetryDelivery,
    ) -> None:
        self._get_preferences = get_preferences
        self._sentry_delivery = sentry_delivery
        self._noop_delivery = noop_delivery

    def deliver(
        self,
        event_id: str,
        payload: dict[str, object],
        *,
        event_type: str = "atlas.backend.unhandled_exception",
        subsystem: str = "backend",
    ) -> TelemetryDeliveryStatus:
        preferences = self._get_preferences()
        if not _delivery_allowed(preferences, payload, subsystem):
            return self._noop_delivery.deliver(
                event_id,
                payload,
                event_type=event_type,
                subsystem=subsystem,
            )
        if not self._sentry_delivery.is_configured:
            return self._noop_delivery.deliver(
                event_id,
                payload,
                event_type=event_type,
                subsystem=subsystem,
            )
        return self._sentry_delivery.deliver(
            event_id,
            payload,
            event_type=event_type,
            subsystem=subsystem,
        )


def _delivery_allowed(preferences: TelemetryPreferences, payload: dict[str, object], subsystem: str) -> bool:
    if not preferences.telemetry_enabled:
        return False
    if subsystem == TelemetrySubsystem.PLUGIN.value and not preferences.plugin_telemetry_enabled:
        return False
    if "exception" in payload and not preferences.crash_reporting_enabled:
        return False
    return True


def create_telemetry_delivery(
    *,
    container: Any,
    sanitizer: TelemetrySanitizerPort,
) -> TelemetryDeliveryPort:
    noop = LocalNoopTelemetryDelivery()
    dsn = resolve_sentry_dsn()
    if not dsn:
        return noop

    sentry = SentryTelemetryDelivery(sanitizer=sanitizer)

    def get_preferences() -> TelemetryPreferences:
        with container.create_unit_of_work() as uow:
            uow.begin()
            try:
                from backend.adapters.persistence import TelemetryRepository

                record = uow.repository(TelemetryRepository).get_preferences()
                return preference_record_to_domain(record)
            finally:
                uow.rollback()

    return PreferenceGatedTelemetryDelivery(
        get_preferences=get_preferences,
        sentry_delivery=sentry,
        noop_delivery=noop,
    )
