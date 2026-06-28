from __future__ import annotations

from pydantic import BaseModel, Field


class AdoptRepositoryPlanRequest(BaseModel):
    root_path: str
    remote_url: str | None = None


class AdoptRepositoryRequest(BaseModel):
    root_path: str
    remote_url: str | None = None
    idempotency_key: str | None = None


class ApplyRepoNormalizationRequest(BaseModel):
    idempotency_key: str | None = None


class ApplySecretSubstitutionRequest(BaseModel):
    idempotency_key: str | None = None


class ApplyDevSecretRequest(BaseModel):
    slot_id: str
    dev_value: str
    idempotency_key: str | None = None


class ApplyDevTransformRequest(BaseModel):
    hostname: str | None = None
    max_clients: int | None = None
    udp_port: int | None = None
    tcp_port: int | None = None
    idempotency_key: str | None = None


class Pathway2UndoRequest(BaseModel):
    command_execution_id: str


class AuditReference(BaseModel):
    ref_type: str
    ref_id: str


class ErrorPayload(BaseModel):
    code: str
    message: str


class ResponseEnvelope(BaseModel):
    ok: bool
    data: dict | list | None = None
    warnings: list[str] = Field(default_factory=list)
    error: ErrorPayload | None = None
    audit_ref: AuditReference | None = None
