from __future__ import annotations

from pydantic import BaseModel, Field


class ErrorPayload(BaseModel):
    code: str
    message: str


class ResponseEnvelope(BaseModel):
    ok: bool
    data: dict | list[dict] | None = None
    error: ErrorPayload | None = None
    warnings: list[str] = Field(default_factory=list)


class ValidateManifestRequest(BaseModel):
    manifest: dict | None = None
    manifest_path: str | None = None


class RegisterPluginRequest(BaseModel):
    manifest: dict
    source_ref: str | None = None
    idempotency_key: str | None = None


class SetPluginEnabledRequest(BaseModel):
    enabled: bool


class SetGlobalPluginRequest(BaseModel):
    global_enabled: bool


class GrantCapabilitiesRequest(BaseModel):
    capabilities: list[str]
    trust_acknowledgment: dict
    idempotency_key: str | None = None


class StartPluginRunRequest(BaseModel):
    mode: str = "normal"


class RevokeCapabilityRequest(BaseModel):
    capability: str
    idempotency_key: str | None = None


class InvokeContributionRequest(BaseModel):
    payload: dict | None = None
