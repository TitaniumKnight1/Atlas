from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.api.dependencies import get_container
from backend.api.schemas.telemetry import (
    AuditReference,
    ErrorPayload,
    RecordDeliveryAttemptRequest,
    ResponseEnvelope,
    TelemetryEventRequest,
    UpdateTelemetryPreferencesRequest,
)
from backend.application.commands import CommandExecutionResult
from backend.application.telemetry import TelemetryApplicationError
from backend.domain.shared_kernel import ErrorCode, ProjectId, Severity, StableIdentifier
from backend.domain.telemetry import SanitizationDecision, TelemetryEventCandidate, TelemetrySubsystem
from backend.infrastructure.di import ApplicationContainer


router = APIRouter(prefix="/api/v1", tags=["telemetry"])


@router.get("/telemetry/preferences", response_model=ResponseEnvelope)
def get_telemetry_preferences(
    project_id: str | None = None,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(container.create_telemetry_service().get_preferences(ProjectId(project_id) if project_id else None))
    except TelemetryApplicationError as error:
        return _failure(error)


@router.patch("/telemetry/preferences", response_model=ResponseEnvelope)
def update_telemetry_preferences(
    request: UpdateTelemetryPreferencesRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        patch = {
            key: value
            for key, value in {
                "telemetry_enabled": request.telemetry_enabled,
                "crash_reporting_enabled": request.crash_reporting_enabled,
                "plugin_telemetry_enabled": request.plugin_telemetry_enabled,
            }.items()
            if value is not None
        }
        result = container.create_telemetry_service().execute_update_preferences(
            patch=patch,
            project_id=ProjectId(request.project_id) if request.project_id else None,
            updated_by=request.updated_by,
        )
        return _command_success(result)
    except TelemetryApplicationError as error:
        return _failure(error)


@router.post("/telemetry/evaluate", response_model=ResponseEnvelope)
def evaluate_telemetry_event(
    request: TelemetryEventRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        decision = container.create_telemetry_service().evaluate_event(_candidate_from_request(request))
        if not decision.accepted:
            return _failure(TelemetryApplicationError(ErrorCode.TELEMETRY_REJECTED, "Telemetry event rejected by sanitizer"))
        return _success(_decision_data(decision))
    except TelemetryApplicationError as error:
        return _failure(error)


@router.post("/telemetry/queue", response_model=ResponseEnvelope)
def queue_telemetry_event(
    request: TelemetryEventRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(container.create_telemetry_service().queue_event(_candidate_from_request(request)))
    except TelemetryApplicationError as error:
        return _failure(error)


@router.post("/telemetry/delivery-attempts", response_model=ResponseEnvelope)
def record_delivery_attempt(
    request: RecordDeliveryAttemptRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(container.create_telemetry_service().record_delivery_attempt(StableIdentifier(request.telemetry_event_id)))
    except TelemetryApplicationError as error:
        return _failure(error)


@router.get("/telemetry/rejections", response_model=ResponseEnvelope)
def list_telemetry_rejections(container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    return _success(container.create_telemetry_service().list_rejections())


@router.get("/telemetry/delivery-attempts", response_model=ResponseEnvelope)
def list_delivery_attempts(container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    return _success(container.create_telemetry_service().list_delivery_attempts())


def _candidate_from_request(request: TelemetryEventRequest) -> TelemetryEventCandidate:
    try:
        return TelemetryEventCandidate(
            event_type=request.event_type,
            subsystem=TelemetrySubsystem(request.subsystem),
            severity=Severity(request.severity),
            payload=request.payload,
            project_id=ProjectId(request.project_id) if request.project_id else None,
        )
    except ValueError as error:
        raise TelemetryApplicationError(ErrorCode.VALIDATION_FAILED, str(error)) from error


def _success(data: dict | list[dict], warnings: list[str] | None = None) -> ResponseEnvelope:
    return ResponseEnvelope(ok=True, data=data, warnings=warnings or [])


def _failure(error: TelemetryApplicationError) -> ResponseEnvelope:
    return ResponseEnvelope(ok=False, error=ErrorPayload(code=error.code.value, message=str(error)))


def _command_success(result: CommandExecutionResult) -> ResponseEnvelope:
    return ResponseEnvelope(
        ok=True,
        data={
            **result.result,
            "command_plan_id": str(result.command_plan_id),
            "command_execution_id": str(result.command_execution_id),
            "undo_plan": result.undo_plan.payload if result.undo_plan else None,
        },
        audit_ref=AuditReference(ref_type=result.audit_ref.ref_type, ref_id=result.audit_ref.ref_id),
    )


def _decision_data(decision: SanitizationDecision) -> dict[str, object]:
    return {
        "event_type": decision.event_type,
        "subsystem": decision.subsystem.value,
        "severity": decision.severity.value,
        "sanitization_state": decision.state.value,
        "rules_applied": decision.rules_applied,
        "redaction_count": decision.redaction_count,
        "payload": decision.sanitized_payload,
    }
