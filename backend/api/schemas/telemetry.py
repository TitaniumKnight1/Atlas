from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorPayload(BaseModel):
    code: str
    message: str


class AuditReference(BaseModel):
    ref_type: str
    ref_id: str


class ResponseEnvelope(BaseModel):
    ok: bool
    data: dict[str, Any] | list[dict[str, Any]] | None = None
    error: ErrorPayload | None = None
    warnings: list[str] = Field(default_factory=list)
    audit_ref: AuditReference | None = None


class UpdateTelemetryPreferencesRequest(BaseModel):
    project_id: str | None = None
    telemetry_enabled: bool | None = None
    crash_reporting_enabled: bool | None = None
    plugin_telemetry_enabled: bool | None = None
    record_consent_prompt_shown: bool | None = None
    updated_by: str | None = None


class TelemetryEventRequest(BaseModel):
    event_type: str
    subsystem: str
    severity: str
    payload: dict[str, Any]
    project_id: str | None = None


class RecordDeliveryAttemptRequest(BaseModel):
    telemetry_event_id: str
