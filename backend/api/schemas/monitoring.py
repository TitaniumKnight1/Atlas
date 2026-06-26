from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ErrorPayload(BaseModel):
    code: str
    message: str


class ResponseEnvelope(BaseModel):
    ok: bool
    data: dict | list[dict] | None = None
    error: ErrorPayload | None = None
    warnings: list[str] = Field(default_factory=list)


class StartCollectionRequest(BaseModel):
    interval_seconds: float | None = None


class HistoryQueryParams(BaseModel):
    start_at: datetime
    end_at: datetime
    metric_series_id: str | None = None
    resolution: str | None = None


class CreateAlertRequest(BaseModel):
    name: str
    severity: str
    metric_series_id: str
    comparator: str
    threshold: float
    duration_seconds: int = 0
    is_enabled: bool = True


class UpdateAlertRequest(BaseModel):
    name: str | None = None
    severity: str | None = None
    metric_series_id: str | None = None
    comparator: str | None = None
    threshold: float | None = None
    duration_seconds: int | None = None
    is_enabled: bool | None = None
