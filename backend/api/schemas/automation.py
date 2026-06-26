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


class AutomationActionRequest(BaseModel):
    action_type: str
    safety_class: str = "read_only"
    config_json: dict | None = None


class AutomationConditionRequest(BaseModel):
    condition_type: str = "always"
    config_json: dict | None = None


class CreateAutomationWorkflowRequest(BaseModel):
    name: str
    description: str | None = None
    trigger_type: str
    trigger_config: dict | None = None
    conditions: list[AutomationConditionRequest] | None = None
    actions: list[AutomationActionRequest]
    schedule_interval_seconds: int | None = None
    is_enabled: bool = True


class SetAutomationEnabledRequest(BaseModel):
    is_enabled: bool


class SetGlobalAutomationRequest(BaseModel):
    global_enabled: bool


class RunAutomationRequest(BaseModel):
    idempotency_key: str | None = None
