from __future__ import annotations

import json
import socket
import threading
import time
from pathlib import Path
from urllib import error, request

import uvicorn
from sqlalchemy import select

from backend.adapters.persistence.models import TelemetryQueueRecord, TelemetryRejectionRecord
from backend.atlas_backend.app import create_app
from backend.infrastructure.di import create_application_container


def test_telemetry_preferences_and_queue_api(tmp_path: Path) -> None:
    app_data = tmp_path / "app-data"
    port = _free_loopback_port()
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(app_data_dir=app_data),
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
        default = _request_json(f"{base_url}/api/v1/telemetry/preferences", method="GET")
        updated = _request_json(
            f"{base_url}/api/v1/telemetry/preferences",
            {"telemetry_enabled": True, "crash_reporting_enabled": True, "updated_by": "api-test"},
            method="PATCH",
        )
        queued = _request_json(
            f"{base_url}/api/v1/telemetry/queue",
            {
                "event_type": "atlas.backend.unhandled_exception",
                "subsystem": "backend",
                "severity": "error",
                "payload": {
                    "message": "Atlas failed at 127.0.0.1 with password=secret",
                    "exception": {"type": "RuntimeError", "value": "safe", "module": "backend"},
                    "stacktrace": [{"filename": "C:\\Users\\Ryan\\Atlas\\backend\\api.py", "function": "run", "module": "backend", "lineno": 5}],
                    "contexts": {"backend": {"component": "api"}},
                    "tags": {"backend_subsystem": "backend"},
                },
            },
        )
        attempts = _request_json(f"{base_url}/api/v1/telemetry/delivery-attempts", method="GET")
    finally:
        server.should_exit = True
        thread.join(timeout=5)

    assert not thread.is_alive()
    assert default["data"]["telemetry_enabled"] is False
    assert updated["ok"] is True
    assert updated["audit_ref"]["ref_type"] == "audit_event"
    assert queued["ok"] is True
    assert queued["data"]["delivery_status"] == "skipped"
    assert attempts["data"][0]["status"] == "skipped"

    container = create_application_container(app_data)
    try:
        event = _records(container, TelemetryQueueRecord)[0]
        serialized = json.dumps(event.event_payload_json, sort_keys=True)
        assert "127.0.0.1" not in serialized
        assert "secret" not in serialized
        assert "C:\\Users\\Ryan" not in serialized
    finally:
        container.close()


def test_telemetry_evaluate_rejects_unsafe_payload_over_api(tmp_path: Path) -> None:
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
        rejected = _request_json(
            f"{base_url}/api/v1/telemetry/evaluate",
            {
                "event_type": "atlas.backend.unhandled_exception",
                "subsystem": "backend",
                "severity": "error",
                "payload": {"message": "server.cfg from txData resources should never leave"},
            },
        )
        rejections = _request_json(f"{base_url}/api/v1/telemetry/rejections", method="GET")
    finally:
        server.should_exit = True
        thread.join(timeout=5)

    assert not thread.is_alive()
    assert rejected["ok"] is False
    assert rejected["error"]["code"] == "TelemetryRejected"
    assert rejections["data"][0]["rejection_reason"] == "contains_project_data"
    assert "server.cfg" not in json.dumps(rejections["data"][0]["summary"])


def test_unhandled_backend_error_routes_through_disabled_sanitizer_path(tmp_path: Path) -> None:
    app_data = tmp_path / "app-data"
    app = create_app(app_data_dir=app_data)

    def crash() -> None:
        raise RuntimeError("Atlas crash with password=secret")

    app.add_api_route("/api/v1/debug/test-crash", crash, methods=["GET"])
    port = _free_loopback_port()
    server = uvicorn.Server(
        uvicorn.Config(
            app,
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
        response = _request_json(f"http://127.0.0.1:{port}/api/v1/debug/test-crash", method="GET")
    finally:
        server.should_exit = True
        thread.join(timeout=5)

    assert not thread.is_alive()
    assert response["ok"] is False
    container = create_application_container(app_data)
    try:
        assert _records(container, TelemetryQueueRecord) == []
        rejection = _records(container, TelemetryRejectionRecord)[0]
        assert rejection.rejection_reason == "disabled"
        assert "secret" not in json.dumps(rejection.summary_json)
    finally:
        container.close()


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
        except error.HTTPError as http_error:
            return json.loads(http_error.read().decode("utf-8"))
        except Exception as caught:  # noqa: BLE001 - retry until Uvicorn accepts connections.
            last_error = caught
            time.sleep(0.05)
    raise AssertionError(f"Telemetry API did not respond before timeout: {last_error}")


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as socket_:
        socket_.bind(("127.0.0.1", 0))
        return int(socket_.getsockname()[1])


def _records(container, model: type):
    with container.session_factory() as session:
        return list(session.execute(select(model)).scalars())
