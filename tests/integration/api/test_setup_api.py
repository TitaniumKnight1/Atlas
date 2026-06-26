from __future__ import annotations

import json
import socket
import threading
import time
from pathlib import Path
from urllib import request

import uvicorn

from backend.atlas_backend.app import create_app


def test_setup_server_config_and_dependency_api(tmp_path: Path) -> None:
    project_root = tmp_path / "api-setup-project"
    (project_root / "resources").mkdir(parents=True)
    server_data = tmp_path / "server-data"
    port = _free_loopback_port()
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(app_data_dir=tmp_path / "app-data"),
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
        imported = _request_json(f"{base_url}/api/v1/projects/import", {"root_path": str(project_root)})
        project_id = imported["data"]["project_id"]
        plan = _request_json(
            f"{base_url}/api/v1/projects/{project_id}/setup/server-config/plan",
            {"server_data_path": str(server_data), "options": {"hostname": "API Setup", "license_key": "CHANGE_ME"}},
        )
        written = _request_json(
            f"{base_url}/api/v1/projects/{project_id}/setup/server-config/write",
            {"server_data_path": str(server_data), "options": {"hostname": "API Setup", "license_key": "CHANGE_ME"}},
        )
        checks = _request_json(
            f"{base_url}/api/v1/projects/{project_id}/dependency-checks/run",
            {"server_data_path": str(server_data)},
        )
        listed_checks = _request_json(f"{base_url}/api/v1/projects/{project_id}/dependency-checks", method="GET")
    finally:
        server.should_exit = True
        thread.join(timeout=5)

    assert not thread.is_alive()
    assert plan["ok"] is True
    assert "server.cfg" in plan["data"]["preview"]["server_cfg_path"]
    assert written["ok"] is True
    assert written["audit_ref"]["ref_type"] == "audit_event"
    assert (server_data / "server.cfg").exists()
    assert checks["ok"] is True
    assert listed_checks["ok"] is True
    assert len(listed_checks["data"]) >= 2


def _request_json(url: str, payload: dict | None = None, method: str = "POST") -> dict:
    deadline = time.monotonic() + 5
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            req = request.Request(url, data=body, method=method, headers=headers)
            with request.urlopen(req, timeout=1) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as error:  # noqa: BLE001 - retry until Uvicorn is accepting connections.
            last_error = error
            time.sleep(0.05)
    raise AssertionError(f"Setup API did not respond before timeout: {last_error}")


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as socket_:
        socket_.bind(("127.0.0.1", 0))
        return int(socket_.getsockname()[1])
