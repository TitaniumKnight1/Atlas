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


class CreateBackupPlanRequest(BaseModel):
    name: str
    backup_scope: str = "full"
    retention_policy: dict | None = None
    schedule_interval_seconds: int | None = None
    is_enabled: bool = True


class RunBackupRequest(BaseModel):
    backup_plan_id: str | None = None
    idempotency_key: str | None = None


class RestoreBackupRequest(BaseModel):
    backup_run_id: str
    confirm_destructive: bool = False
    idempotency_key: str | None = None


class EvaluateRetentionRequest(BaseModel):
    backup_plan_id: str | None = None
