from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select

from backend.adapters.persistence.models import (
    TelemetryDeliveryAttemptRecord,
    TelemetryPreferenceRecord,
    TelemetryQueueRecord,
    TelemetryRejectionRecord,
    TelemetrySanitizationResultRecord,
)
from backend.domain.shared_kernel import ProjectId, StableIdentifier
from backend.domain.telemetry import TelemetryDeliveryStatus, TelemetryPreferences, TelemetryQueueStatus, TelemetryRejectionReason
from backend.infrastructure.unit_of_work import RepositoryContext


class TelemetryRepository:
    def __init__(self, context: RepositoryContext) -> None:
        self._session = context.session
        self._project_id = context.project_id

    def get_preferences(self, project_id: ProjectId | None = None) -> TelemetryPreferenceRecord | None:
        scoped_project_id = project_id if project_id is not None else self._project_id
        query = select(TelemetryPreferenceRecord)
        if scoped_project_id is None:
            query = query.where(TelemetryPreferenceRecord.project_id.is_(None))
        else:
            query = query.where(TelemetryPreferenceRecord.project_id == str(scoped_project_id))
        return self._session.execute(query.order_by(TelemetryPreferenceRecord.updated_at.desc())).scalar_one_or_none()

    def upsert_preferences(
        self,
        *,
        project_id: ProjectId | None,
        telemetry_enabled: bool,
        crash_reporting_enabled: bool,
        plugin_telemetry_enabled: bool,
        updated_at: datetime,
        updated_by: str | None = None,
        last_prompted_at: datetime | None = None,
    ) -> TelemetryPreferenceRecord:
        existing = self.get_preferences(project_id)
        timestamp = updated_at.isoformat()
        if existing is None:
            existing = TelemetryPreferenceRecord(
                telemetry_preference_id=str(StableIdentifier.new()),
                project_id=str(project_id) if project_id else None,
                telemetry_enabled=1 if telemetry_enabled else 0,
                crash_reporting_enabled=1 if crash_reporting_enabled else 0,
                plugin_telemetry_enabled=1 if plugin_telemetry_enabled else 0,
                last_prompted_at=last_prompted_at.isoformat() if last_prompted_at else None,
                updated_at=timestamp,
                updated_by=updated_by,
            )
            self._session.add(existing)
            return existing
        existing.telemetry_enabled = 1 if telemetry_enabled else 0
        existing.crash_reporting_enabled = 1 if crash_reporting_enabled else 0
        existing.plugin_telemetry_enabled = 1 if plugin_telemetry_enabled else 0
        existing.last_prompted_at = last_prompted_at.isoformat() if last_prompted_at else existing.last_prompted_at
        existing.updated_at = timestamp
        existing.updated_by = updated_by
        return existing

    def add_queue_event(
        self,
        *,
        telemetry_event_id: StableIdentifier,
        event_type: str,
        subsystem: str,
        severity: str,
        payload: dict[str, Any],
        created_at: datetime,
        expires_at: datetime,
        status: TelemetryQueueStatus = TelemetryQueueStatus.QUEUED,
    ) -> None:
        self._session.add(
            TelemetryQueueRecord(
                telemetry_event_id=str(telemetry_event_id),
                event_type=event_type,
                subsystem=subsystem,
                severity=severity,
                event_payload_json=payload,
                status=status.value,
                created_at=created_at.isoformat(),
                next_attempt_at=created_at.isoformat(),
                expires_at=expires_at.isoformat(),
            )
        )

    def get_queue_event(self, telemetry_event_id: StableIdentifier | str) -> TelemetryQueueRecord | None:
        return self._session.get(TelemetryQueueRecord, str(telemetry_event_id))

    def list_queue(self, status: str | None = None) -> list[TelemetryQueueRecord]:
        query = select(TelemetryQueueRecord)
        if status is not None:
            query = query.where(TelemetryQueueRecord.status == status)
        return list(self._session.execute(query.order_by(TelemetryQueueRecord.created_at.desc())).scalars())

    def add_rejection(
        self,
        *,
        telemetry_rejection_id: StableIdentifier,
        event_type: str,
        rejection_reason: TelemetryRejectionReason,
        subsystem: str,
        created_at: datetime,
        summary: dict[str, Any] | None,
        fingerprint: str | None = None,
    ) -> None:
        self._session.add(
            TelemetryRejectionRecord(
                telemetry_rejection_id=str(telemetry_rejection_id),
                event_type=event_type,
                rejection_reason=rejection_reason.value,
                subsystem=subsystem,
                fingerprint=fingerprint,
                created_at=created_at.isoformat(),
                summary_json=summary or {},
            )
        )

    def list_rejections(self, reason: str | None = None) -> list[TelemetryRejectionRecord]:
        query = select(TelemetryRejectionRecord)
        if reason is not None:
            query = query.where(TelemetryRejectionRecord.rejection_reason == reason)
        return list(self._session.execute(query.order_by(TelemetryRejectionRecord.created_at.desc())).scalars())

    def add_sanitization_result(
        self,
        *,
        sanitization_result_id: StableIdentifier,
        state: str,
        rules_applied: list[str],
        redaction_count: int,
        created_at: datetime,
        telemetry_event_id: StableIdentifier | None = None,
        telemetry_rejection_id: StableIdentifier | None = None,
    ) -> None:
        self._session.add(
            TelemetrySanitizationResultRecord(
                sanitization_result_id=str(sanitization_result_id),
                telemetry_event_id=str(telemetry_event_id) if telemetry_event_id else None,
                telemetry_rejection_id=str(telemetry_rejection_id) if telemetry_rejection_id else None,
                result_state=state,
                rules_applied_json=rules_applied,
                redaction_count=redaction_count,
                created_at=created_at.isoformat(),
            )
        )

    def add_delivery_attempt(
        self,
        *,
        delivery_attempt_id: StableIdentifier,
        telemetry_event_id: StableIdentifier | str,
        status: TelemetryDeliveryStatus,
        attempted_at: datetime,
        http_status: int | None = None,
        error_summary: str | None = None,
    ) -> int:
        attempt_number = self.next_attempt_number(telemetry_event_id)
        self._session.add(
            TelemetryDeliveryAttemptRecord(
                delivery_attempt_id=str(delivery_attempt_id),
                telemetry_event_id=str(telemetry_event_id),
                attempt_number=attempt_number,
                status=status.value,
                attempted_at=attempted_at.isoformat(),
                http_status=http_status,
                error_summary=error_summary,
            )
        )
        return attempt_number

    def next_attempt_number(self, telemetry_event_id: StableIdentifier | str) -> int:
        current = self._session.scalar(
            select(func.max(TelemetryDeliveryAttemptRecord.attempt_number)).where(
                TelemetryDeliveryAttemptRecord.telemetry_event_id == str(telemetry_event_id)
            )
        )
        return int(current or 0) + 1

    def list_delivery_attempts(self, telemetry_event_id: str | None = None) -> list[TelemetryDeliveryAttemptRecord]:
        query = select(TelemetryDeliveryAttemptRecord)
        if telemetry_event_id is not None:
            query = query.where(TelemetryDeliveryAttemptRecord.telemetry_event_id == telemetry_event_id)
        return list(self._session.execute(query.order_by(TelemetryDeliveryAttemptRecord.attempted_at.desc())).scalars())


def preference_record_to_domain(record: TelemetryPreferenceRecord | None, project_id: ProjectId | None = None) -> TelemetryPreferences:
    if record is None:
        return TelemetryPreferences(project_id=project_id)
    return TelemetryPreferences(
        project_id=ProjectId(record.project_id) if record.project_id else None,
        telemetry_enabled=bool(record.telemetry_enabled),
        crash_reporting_enabled=bool(record.crash_reporting_enabled),
        plugin_telemetry_enabled=bool(record.plugin_telemetry_enabled),
        last_prompted_at=record.last_prompted_at,
        updated_at=record.updated_at,
        updated_by=record.updated_by,
    )
