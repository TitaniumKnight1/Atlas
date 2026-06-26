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


class RescanResourcesRequest(BaseModel):
    path_filters: list[str] | None = None


class ResourceSourceRequest(BaseModel):
    source_type: str
    source_uri: str
    resource_name: str | None = None
    enable: bool = True


class UpdateResourceRequest(BaseModel):
    source_type: str
    source_uri: str


class SetEnabledStateRequest(BaseModel):
    enabled: bool
