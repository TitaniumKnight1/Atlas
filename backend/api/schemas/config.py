from __future__ import annotations

from pydantic import BaseModel, Field


class AuditReference(BaseModel):
    ref_type: str
    ref_id: str


class ErrorPayload(BaseModel):
    code: str
    message: str


class ResponseEnvelope(BaseModel):
    ok: bool
    data: dict | list[dict] | None = None
    error: ErrorPayload | None = None
    warnings: list[str] = Field(default_factory=list)
    audit_ref: AuditReference | None = None


class RescanConfigRequest(BaseModel):
    scan_roots: list[str] | None = None


class ConfigChangePlanRequest(BaseModel):
    config_file_id: str
    proposed_content: str


class ApplyConfigChangeRequest(BaseModel):
    config_file_id: str
    proposed_content: str
    idempotency_key: str | None = None


class ValidationRunRequest(BaseModel):
    config_file_id: str | None = None


class SecretScanRequest(BaseModel):
    config_file_id: str | None = None


class ConfigRemediationRequest(BaseModel):
    finding_id: str

