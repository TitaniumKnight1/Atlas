from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ErrorPayload(BaseModel):
    code: str
    message: str


class HealthData(BaseModel):
    status: Literal["ok"]
    service: Literal["atlas-backend"]
    transport: Literal["loopback-http"]
    database_path: str
    database_journal_mode: str = Field(description="SQLite journal mode reported by PRAGMA journal_mode")


class HealthResponse(BaseModel):
    ok: Literal[True]
    data: HealthData
    error: None = None
    warnings: list[str] = Field(default_factory=list)


class SqliteSmokeData(BaseModel):
    database_path: str
    journal_mode: str
    inserted_key: str
    round_tripped_value: str


class SqliteSmokeResponse(BaseModel):
    ok: Literal[True]
    data: SqliteSmokeData
    error: None = None
    warnings: list[str] = Field(default_factory=list)
