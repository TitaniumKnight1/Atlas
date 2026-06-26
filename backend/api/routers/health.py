from __future__ import annotations

from fastapi import APIRouter, Request

from backend.adapters.persistence.sqlite_smoke import SqliteSmokeStore
from backend.api.schemas.health import (
    HealthData,
    HealthResponse,
    SqliteSmokeData,
    SqliteSmokeResponse,
)

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    store = _sqlite_store(request)
    return HealthResponse(
        ok=True,
        data=HealthData(
            status="ok",
            service="atlas-backend",
            transport="loopback-http",
            database_path=str(store.database_path),
            database_journal_mode=store.journal_mode,
        ),
    )


@router.post("/debug/sqlite-smoke", response_model=SqliteSmokeResponse)
def sqlite_smoke(request: Request) -> SqliteSmokeResponse:
    result = _sqlite_store(request).round_trip()
    return SqliteSmokeResponse(
        ok=True,
        data=SqliteSmokeData(
            database_path=result.database_path,
            journal_mode=result.journal_mode,
            inserted_key=result.inserted_key,
            round_tripped_value=result.round_tripped_value,
        ),
    )


def _sqlite_store(request: Request) -> SqliteSmokeStore:
    return request.app.state.sqlite_smoke_store
