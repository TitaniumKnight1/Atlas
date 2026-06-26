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


class CompareIncidentsRequest(BaseModel):
    incident_group_ids: list[str] = Field(min_length=2)


class ExportIncidentMarkdownRequest(BaseModel):
    occurrence_id: str | None = None
    redaction_profile: str = "default"
