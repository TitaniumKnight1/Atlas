from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.adapters.persistence.sqlite_smoke import SqliteSmokeStore
from backend.api.routers.config import router as config_router
from backend.api.routers.git import router as git_router
from backend.api.routers.health import router as health_router
from backend.api.routers.project import router as project_router
from backend.api.routers.setup import router as setup_router
from backend.api.routers.streams import router as streams_router
from backend.api.routers.telemetry import router as telemetry_router
from backend.infrastructure.di import create_application_container


def create_app(app_data_dir: Path | None = None) -> FastAPI:
    resolved_app_data_dir = app_data_dir or _default_app_data_dir()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container = create_application_container(resolved_app_data_dir)
        sqlite_smoke_store = SqliteSmokeStore(resolved_app_data_dir)
        sqlite_smoke_store.open()
        app.state.container = container
        app.state.sqlite_smoke_store = sqlite_smoke_store
        try:
            yield
        finally:
            sqlite_smoke_store.close()
            container.close()

    app = FastAPI(title="Atlas Backend", version="0.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:1420",
            "http://localhost:1420",
            "http://tauri.localhost",
            "https://tauri.localhost",
            "tauri://localhost",
        ],
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(project_router)
    app.include_router(config_router)
    app.include_router(git_router)
    app.include_router(setup_router)
    app.include_router(streams_router)
    app.include_router(telemetry_router)

    @app.exception_handler(Exception)
    async def capture_unhandled_backend_error(request: Request, error: Exception) -> JSONResponse:
        container = getattr(request.app.state, "container", None)
        if container is not None:
            container.create_telemetry_service().capture_backend_exception(error)
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": {"code": "ExternalAdapterFailed", "message": "Unhandled Atlas backend error"},
                "warnings": [],
            },
        )

    return app


def _default_app_data_dir() -> Path:
    override = os.environ.get("ATLAS_APP_DATA_DIR")
    if override:
        return Path(override)

    if os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return root / "Atlas"
