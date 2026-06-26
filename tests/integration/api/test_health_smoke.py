from __future__ import annotations

import json
import socket
import threading
import time
from pathlib import Path
from urllib import request

import uvicorn

from backend.atlas_backend.app import create_app


def test_health_round_trip_and_sqlite_smoke(tmp_path: Path) -> None:
    port = _free_loopback_port()
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(app_data_dir=tmp_path),
            host="127.0.0.1",
            port=port,
            lifespan="on",
            log_level="warning",
            access_log=False,
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{port}"
        health = _request_json(f"{base_url}/api/v1/health")
        sqlite_smoke = _request_json(f"{base_url}/api/v1/debug/sqlite-smoke", method="POST")
    finally:
        server.should_exit = True
        thread.join(timeout=5)

    assert not thread.is_alive()
    assert health["ok"] is True
    assert health["data"]["status"] == "ok"
    assert health["data"]["transport"] == "loopback-http"
    assert health["data"]["database_journal_mode"].lower() == "wal"
    assert sqlite_smoke["ok"] is True
    assert sqlite_smoke["data"]["journal_mode"].lower() == "wal"
    assert sqlite_smoke["data"]["round_tripped_value"].startswith("atlas-smoke:")
    assert Path(health["data"]["database_path"]).parent == tmp_path


def _request_json(url: str, method: str = "GET") -> dict:
    deadline = time.monotonic() + 5
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            req = request.Request(url, method=method, headers={"Accept": "application/json"})
            with request.urlopen(req, timeout=1) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as error:  # noqa: BLE001 - retry until Uvicorn is accepting connections.
            last_error = error
            time.sleep(0.05)
    raise AssertionError(f"Backend did not respond before timeout: {last_error}")


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as socket_:
        socket_.bind(("127.0.0.1", 0))
        return int(socket_.getsockname()[1])
