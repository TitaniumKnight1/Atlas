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


class ImportProjectPlanRequest(BaseModel):
    root_path: str
    template_id: str | None = None


class ImportProjectRequest(BaseModel):
    root_path: str
    template_id: str | None = None
    idempotency_key: str | None = None


class UpdateProjectSettingsRequest(BaseModel):
    settings_patch: dict[str, Any]
    expected_version: str | None = None


class CreateEnvironmentProfileRequest(BaseModel):
    name: str
    display_name: str | None = None
    artifact_channel: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)
    is_default: bool = False


class UpdateEnvironmentProfileRequest(BaseModel):
    display_name: str | None = None
    artifact_channel: str | None = None
    settings: dict[str, Any] | None = None


class RecordTrustDecisionRequest(BaseModel):
    scope: str
    scope_ref: str | None = None
    trust_state: str
    reason: str | None = None
    decided_by: str | None = None


class ArchiveProjectRequest(BaseModel):
    reason: str


class UndoCommandRequest(BaseModel):
    command_execution_id: str
