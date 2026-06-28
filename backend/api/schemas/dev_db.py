from __future__ import annotations

from pydantic import BaseModel, Field


class ErrorPayload(BaseModel):
    code: str
    message: str


class AuditReference(BaseModel):
    ref_type: str
    ref_id: str


class ResponseEnvelope(BaseModel):
    ok: bool
    data: dict[str, object] | list[dict[str, object]] | None = None
    error: ErrorPayload | None = None
    warnings: list[str] = Field(default_factory=list)
    audit_ref: AuditReference | None = None


class DevDatabaseUndoRequest(BaseModel):
    command_execution_id: str
