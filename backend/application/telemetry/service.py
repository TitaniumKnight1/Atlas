from __future__ import annotations

import traceback
from datetime import UTC, datetime, timedelta
from typing import Any

from backend.adapters.persistence import AuditRepository, TelemetryRepository
from backend.adapters.persistence.telemetry_repository import preference_record_to_domain
from backend.application.commands import CommandExecutionResult, CommandPreview, RiskLevel
from backend.application.commands.recorder import CommandAuditRecorder
from backend.domain.shared_kernel import ErrorCode, ProjectId, Severity, StableIdentifier
from backend.domain.telemetry import (
    SanitizationDecision,
    SanitizationState,
    TelemetryDeliveryPort,
    TelemetryEventCandidate,
    TelemetryPreferences,
    TelemetryRejectionReason,
    TelemetrySanitizerPort,
    TelemetrySubsystem,
    telemetry_event_delivered,
    telemetry_event_queued,
    telemetry_preferences_updated,
    telemetry_rejected,
)
from backend.infrastructure.sentry_dsn import resolve_sentry_dsn


class TelemetryApplicationError(RuntimeError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


class TelemetryApplicationService:
    def __init__(
        self,
        *,
        container: Any,
        sanitizer: TelemetrySanitizerPort,
        delivery: TelemetryDeliveryPort,
    ) -> None:
        self._container = container
        self._sanitizer = sanitizer
        self._delivery = delivery
        self._recorder = CommandAuditRecorder()

    def get_preferences(self, project_id: ProjectId | None = None) -> dict[str, Any]:
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            try:
                preferences = preference_record_to_domain(uow.repository(TelemetryRepository).get_preferences(project_id), project_id)
                return _preferences_data(preferences)
            finally:
                uow.rollback()

    def execute_update_preferences(
        self,
        *,
        patch: dict[str, bool],
        project_id: ProjectId | None = None,
        updated_by: str | None = None,
        record_consent_prompt_shown: bool = False,
    ) -> CommandExecutionResult:
        allowed_keys = {"telemetry_enabled", "crash_reporting_enabled", "plugin_telemetry_enabled"}
        unknown = sorted(set(patch) - allowed_keys)
        if unknown:
            raise TelemetryApplicationError(ErrorCode.VALIDATION_FAILED, f"Unknown telemetry preference: {unknown[0]}")
        if any(not isinstance(value, bool) for value in patch.values()):
            raise TelemetryApplicationError(ErrorCode.VALIDATION_FAILED, "Telemetry preferences must be booleans")

        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(TelemetryRepository)
            current = preference_record_to_domain(repository.get_preferences(project_id), project_id)
            updated = TelemetryPreferences(
                project_id=project_id,
                telemetry_enabled=patch.get("telemetry_enabled", current.telemetry_enabled),
                crash_reporting_enabled=patch.get("crash_reporting_enabled", current.crash_reporting_enabled),
                plugin_telemetry_enabled=patch.get("plugin_telemetry_enabled", current.plugin_telemetry_enabled),
                updated_by=updated_by,
            )
            record = repository.upsert_preferences(
                project_id=project_id,
                telemetry_enabled=updated.telemetry_enabled,
                crash_reporting_enabled=updated.crash_reporting_enabled,
                plugin_telemetry_enabled=updated.plugin_telemetry_enabled,
                updated_at=datetime.now(UTC),
                updated_by=updated_by,
                last_prompted_at=datetime.now(UTC) if record_consent_prompt_shown else None,
            )
            preferences = preference_record_to_domain(record, project_id)
            preview = CommandPreview(
                command_type="UpdateTelemetryPreferences",
                summary="Update telemetry privacy preferences",
                preview={"project_id": str(project_id) if project_id else None, "changed_keys": sorted(patch)},
                risk_level=RiskLevel.MEDIUM,
            )
            result = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="TelemetryPreferences",
                entity_id=str(project_id) if project_id else "global",
                summary="Updated telemetry privacy preferences",
                result=_preferences_data(preferences),
                events=[telemetry_preferences_updated(project_id, sorted(patch))],
            )
            uow.commit()
            return result

    def evaluate_event(self, candidate: TelemetryEventCandidate) -> SanitizationDecision:
        decision = self._sanitizer.sanitize(candidate)
        if decision.state == SanitizationState.REJECTED:
            self._record_rejection(candidate, decision)
        return decision

    def queue_event(self, candidate: TelemetryEventCandidate) -> dict[str, Any]:
        with self._container.create_unit_of_work(candidate.project_id) as uow:
            uow.begin()
            repository = uow.repository(TelemetryRepository)
            preferences = preference_record_to_domain(repository.get_preferences(candidate.project_id), candidate.project_id)
            if not _telemetry_allowed(preferences, candidate):
                decision = _disabled_decision(candidate)
                rejection_id = self._record_rejection_in_uow(uow, candidate, decision)
                uow.commit()
                raise TelemetryApplicationError(
                    ErrorCode.TELEMETRY_REJECTED,
                    f"Telemetry disabled; rejected locally as {rejection_id}",
                )

            decision = self._sanitizer.sanitize(candidate)
            if not decision.accepted:
                rejection_id = self._record_rejection_in_uow(uow, candidate, decision)
                uow.commit()
                raise TelemetryApplicationError(
                    ErrorCode.TELEMETRY_REJECTED,
                    f"Telemetry rejected locally as {rejection_id}",
                )

            now = datetime.now(UTC)
            event_id = StableIdentifier.new()
            repository.add_queue_event(
                telemetry_event_id=event_id,
                event_type=decision.event_type,
                subsystem=decision.subsystem.value,
                severity=decision.severity.value,
                payload=decision.sanitized_payload or {},
                created_at=now,
                expires_at=now + timedelta(days=7),
            )
            uow.session.flush()
            repository.add_sanitization_result(
                sanitization_result_id=StableIdentifier.new(),
                telemetry_event_id=event_id,
                state=decision.state.value,
                rules_applied=decision.rules_applied,
                redaction_count=decision.redaction_count,
                created_at=now,
            )
            audit_repository = uow.repository(AuditRepository)
            queued_event = telemetry_event_queued(str(event_id), decision.subsystem.value, decision.severity.value)
            audit_repository.record_domain_event(queued_event, published_at=now)
            uow.collect_event(queued_event)

            delivery_status = self._delivery.deliver(
                str(event_id),
                decision.sanitized_payload or {},
                event_type=decision.event_type,
                subsystem=decision.subsystem.value,
            )
            attempt_number = repository.add_delivery_attempt(
                delivery_attempt_id=StableIdentifier.new(),
                telemetry_event_id=event_id,
                status=delivery_status,
                attempted_at=datetime.now(UTC),
                error_summary=_delivery_error_summary(delivery_status),
            )
            if delivery_status.value == "succeeded":
                delivered_event = telemetry_event_delivered(str(event_id), attempt_number)
                audit_repository.record_domain_event(delivered_event, published_at=datetime.now(UTC))
                uow.collect_event(delivered_event)

            uow.commit()
            return {
                "telemetry_event_id": str(event_id),
                "status": "queued",
                "sanitization_state": decision.state.value,
                "redaction_count": decision.redaction_count,
                "delivery_status": delivery_status.value,
                "delivery_attempt_number": attempt_number,
            }

    def record_delivery_attempt(self, telemetry_event_id: StableIdentifier) -> dict[str, Any]:
        with self._container.create_unit_of_work() as uow:
            uow.begin()
            repository = uow.repository(TelemetryRepository)
            event = repository.get_queue_event(telemetry_event_id)
            if event is None:
                raise TelemetryApplicationError(ErrorCode.NOT_FOUND, f"Telemetry event not found: {telemetry_event_id}")
            status = self._delivery.deliver(
                str(telemetry_event_id),
                event.event_payload_json,
                event_type=event.event_type,
                subsystem=event.subsystem,
            )
            attempt_number = repository.add_delivery_attempt(
                delivery_attempt_id=StableIdentifier.new(),
                telemetry_event_id=telemetry_event_id,
                status=status,
                attempted_at=datetime.now(UTC),
                error_summary=_delivery_error_summary(status),
            )
            uow.commit()
            return {"telemetry_event_id": str(telemetry_event_id), "attempt_number": attempt_number, "status": status.value}

    def list_rejections(self) -> list[dict[str, Any]]:
        with self._container.create_unit_of_work() as uow:
            uow.begin()
            try:
                return [_rejection_data(record) for record in uow.repository(TelemetryRepository).list_rejections()]
            finally:
                uow.rollback()

    def list_delivery_attempts(self) -> list[dict[str, Any]]:
        with self._container.create_unit_of_work() as uow:
            uow.begin()
            try:
                return [_delivery_attempt_data(record) for record in uow.repository(TelemetryRepository).list_delivery_attempts()]
            finally:
                uow.rollback()

    def capture_backend_exception(self, error: BaseException, *, subsystem: str = "backend") -> None:
        try:
            candidate = backend_exception_candidate(error, subsystem=subsystem)
            self.queue_event(candidate)
        except TelemetryApplicationError:
            return

    def _record_rejection(self, candidate: TelemetryEventCandidate, decision: SanitizationDecision) -> StableIdentifier:
        with self._container.create_unit_of_work(candidate.project_id) as uow:
            uow.begin()
            rejection_id = self._record_rejection_in_uow(uow, candidate, decision)
            uow.commit()
            return rejection_id

    def _record_rejection_in_uow(self, uow: Any, candidate: TelemetryEventCandidate, decision: SanitizationDecision) -> StableIdentifier:
        now = datetime.now(UTC)
        repository = uow.repository(TelemetryRepository)
        rejection_id = StableIdentifier.new()
        reason = decision.rejection_reason or TelemetryRejectionReason.POLICY
        repository.add_rejection(
            telemetry_rejection_id=rejection_id,
            event_type=decision.event_type,
            rejection_reason=reason,
            subsystem=decision.subsystem.value,
            created_at=now,
            summary=decision.summary,
            fingerprint=str(decision.summary.get("fingerprint")) if decision.summary.get("fingerprint") else None,
        )
        uow.session.flush()
        repository.add_sanitization_result(
            sanitization_result_id=StableIdentifier.new(),
            telemetry_rejection_id=rejection_id,
            state=decision.state.value,
            rules_applied=decision.rules_applied,
            redaction_count=decision.redaction_count,
            created_at=now,
        )
        audit_repository = uow.repository(AuditRepository)
        event = telemetry_rejected(reason.value, candidate.subsystem.value, candidate.project_id)
        audit_repository.record_domain_event(event, published_at=now)
        uow.collect_event(event)
        return rejection_id


def backend_exception_candidate(error: BaseException, *, subsystem: str = "backend") -> TelemetryEventCandidate:
    frames = traceback.extract_tb(error.__traceback__)[-12:] if error.__traceback__ else []
    return TelemetryEventCandidate(
        event_type="atlas.backend.unhandled_exception",
        subsystem=TelemetrySubsystem(subsystem),
        severity=Severity.ERROR,
        payload={
            "message": f"{type(error).__name__}: {error}",
            "exception": {"type": type(error).__name__, "module": type(error).__module__, "value": str(error)},
            "stacktrace": [
                {
                    "filename": "atlas-backend",
                    "function": frame.name,
                    "module": _safe_module(frame.filename),
                    "lineno": frame.lineno,
                }
                for frame in frames
            ],
            "contexts": {"backend": {"component": "fastapi"}},
            "tags": {"backend_subsystem": subsystem},
        },
    )


def _disabled_decision(candidate: TelemetryEventCandidate) -> SanitizationDecision:
    return SanitizationDecision(
        state=SanitizationState.REJECTED,
        event_type=candidate.event_type if candidate.event_type.startswith("atlas.") else "atlas.telemetry.rejected",
        subsystem=candidate.subsystem,
        severity=candidate.severity,
        sanitized_payload=None,
        rules_applied=["telemetry_disabled"],
        rejection_reason=TelemetryRejectionReason.DISABLED,
        summary={"reason": "disabled", "message": "telemetry preferences disabled capture", "rules": ["telemetry_disabled"]},
    )


def _telemetry_allowed(preferences: TelemetryPreferences, candidate: TelemetryEventCandidate) -> bool:
    if not preferences.telemetry_enabled:
        return False
    if candidate.subsystem == TelemetrySubsystem.PLUGIN and not preferences.plugin_telemetry_enabled:
        return False
    if "exception" in candidate.payload and not preferences.crash_reporting_enabled:
        return False
    return True


def _preferences_data(preferences: TelemetryPreferences) -> dict[str, Any]:
    return {
        "project_id": str(preferences.project_id) if preferences.project_id else None,
        "telemetry_enabled": preferences.telemetry_enabled,
        "crash_reporting_enabled": preferences.crash_reporting_enabled,
        "plugin_telemetry_enabled": preferences.plugin_telemetry_enabled,
        "last_prompted_at": preferences.last_prompted_at,
        "updated_at": preferences.updated_at,
        "updated_by": preferences.updated_by,
        "error_reporting_available": bool(resolve_sentry_dsn()),
        "consent_prompt_pending": bool(resolve_sentry_dsn()) and preferences.last_prompted_at is None,
    }


def _rejection_data(record: Any) -> dict[str, Any]:
    return {
        "telemetry_rejection_id": record.telemetry_rejection_id,
        "event_type": record.event_type,
        "rejection_reason": record.rejection_reason,
        "subsystem": record.subsystem,
        "fingerprint": record.fingerprint,
        "created_at": record.created_at,
        "summary": record.summary_json or {},
    }


def _delivery_attempt_data(record: Any) -> dict[str, Any]:
    return {
        "delivery_attempt_id": record.delivery_attempt_id,
        "telemetry_event_id": record.telemetry_event_id,
        "attempt_number": record.attempt_number,
        "status": record.status,
        "attempted_at": record.attempted_at,
        "http_status": record.http_status,
        "error_summary": record.error_summary,
    }


def _delivery_error_summary(status: Any) -> str | None:
    if status.value == "succeeded":
        return None
    if status.value == "skipped":
        return "Telemetry delivery skipped (disabled, no DSN, or no-op transport)"
    return "Telemetry delivery failed"


def _safe_module(filename: str) -> str:
    normalized = filename.replace("\\", "/")
    if "/backend/" in normalized:
        return "backend/" + normalized.rsplit("/backend/", 1)[1].rsplit("/", 1)[0]
    return "backend"
