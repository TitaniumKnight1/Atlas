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


class RefreshArtifactCatalogRequest(BaseModel):
    platform: str = "windows"
    channel: str | None = None


class PinArtifactRequest(BaseModel):
    artifact_version_id: str | None = None
    channel_preference: str = "recommended"
    environment_id: str | None = None
    pinned_reason: str | None = None


class InstallArtifactRequest(BaseModel):
    build_number: str
    platform: str = "windows"
    channel: str = "recommended"


class ServerConfigRequest(BaseModel):
    server_data_path: str
    options: dict[str, Any] = Field(default_factory=dict)


class DependencyChecksRequest(BaseModel):
    server_data_path: str
    categories: list[str] | None = None


class PrepareDatabaseRequest(BaseModel):
    server_data_path: str
    database_name: str = "fivem.sqlite"


class RunSetupRequest(BaseModel):
    server_data_path: str
    build_number: str
    options: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None


class StartServerProcessRequest(BaseModel):
    fxserver_path: str
    server_data_path: str
    txadmin_mode: bool = False
    extra_args: list[str] | None = None


class StopServerProcessRequest(BaseModel):
    process_run_id: str


class RestartServerProcessRequest(StartServerProcessRequest):
    process_run_id: str


class ValidateFxserverPathRequest(BaseModel):
    fxserver_path: str
