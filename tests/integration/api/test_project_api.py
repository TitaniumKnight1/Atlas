from __future__ import annotations

import json
import socket
import threading
import time
from pathlib import Path
from urllib import request

import uvicorn

from backend.adapters.persistence.models import AuditEventRecord, CommandExecutionRecord, DomainEventRecord
from backend.atlas_backend.app import create_app
from backend.infrastructure.di import create_application_container
from sqlalchemy import select


def test_project_import_and_query_api(tmp_path: Path) -> None:
    project_root = tmp_path / "api-project"
    (project_root / "resources").mkdir(parents=True)
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
        plan = _request_json(f"{base_url}/api/v1/projects/import-plan", {"root_path": str(project_root)})
        imported = _request_json(f"{base_url}/api/v1/projects/import", {"root_path": str(project_root)})
        project_id = imported["data"]["project_id"]
        opened = _request_json(f"{base_url}/api/v1/projects/{project_id}/open", {})
        settings = _request_json(
            f"{base_url}/api/v1/projects/{project_id}/settings",
            {"settings_patch": {"server.name": "API Project"}},
            method="PATCH",
        )
        environment = _request_json(
            f"{base_url}/api/v1/projects/{project_id}/environments",
            {"name": "local", "display_name": "Local", "settings": {"profile": "local"}, "is_default": True},
        )
        environment_id = environment["data"]["environment_id"]
        updated_environment = _request_json(
            f"{base_url}/api/v1/projects/{project_id}/environments/{environment_id}",
            {"display_name": "Local Dev", "settings": {"profile": "dev"}},
            method="PATCH",
        )
        trust = _request_json(
            f"{base_url}/api/v1/projects/{project_id}/trust-decisions",
            {"scope": "project", "trust_state": "trusted", "reason": "test"},
        )
        listed = _request_json(f"{base_url}/api/v1/projects", method="GET")
        templates = _request_json(f"{base_url}/api/v1/project-templates", method="GET")
    finally:
        server.should_exit = True
        thread.join(timeout=5)

    assert not thread.is_alive()
    assert plan["ok"] is True
    assert plan["data"]["command_type"] == "ImportProject"
    assert imported["ok"] is True
    assert imported["audit_ref"]["ref_type"] == "audit_event"
    assert opened["ok"] is True
    assert settings["data"]["changed_keys"] == ["server.name"]
    assert environment["data"]["name"] == "local"
    assert updated_environment["data"]["environment_id"] == environment_id
    assert trust["data"]["trust_decision_id"]
    assert listed["data"][0]["project_id"] == project_id
    assert templates["ok"] is True


def test_import_and_undo_via_api(tmp_path: Path) -> None:
    project_root = tmp_path / "undo-api-project"
    (project_root / "resources").mkdir(parents=True)
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
        imported = _request_json(f"{base_url}/api/v1/projects/import", {"root_path": str(project_root)})
        command_execution_id = imported["data"]["command_execution_id"]
        project_id = imported["data"]["project_id"]
        assert imported["data"]["undo_plan"] is not None

        undone = _request_json(
            f"{base_url}/api/v1/projects/undo",
            {"command_execution_id": command_execution_id},
        )
        project = _request_json(f"{base_url}/api/v1/projects/{project_id}", method="GET")
        already_undone = _request_json(
            f"{base_url}/api/v1/projects/undo",
            {"command_execution_id": command_execution_id},
        )
        missing = _request_json(
            f"{base_url}/api/v1/projects/undo",
            {"command_execution_id": "missing-execution-id"},
        )
    finally:
        server.should_exit = True
        thread.join(timeout=5)

    assert not thread.is_alive()
    assert imported["ok"] is True
    assert undone["ok"] is True
    assert undone["data"]["status"] == "archived"
    assert undone["audit_ref"]["ref_type"] == "audit_event"
    assert undone["data"]["command_execution_id"] != command_execution_id
    assert project["ok"] is True
    assert project["data"]["status"] == "archived"
    assert already_undone["ok"] is False
    assert already_undone["error"]["code"] == "Conflict"
    assert missing["ok"] is False
    assert missing["error"]["code"] == "NotFound"

    container = create_application_container(app_data)
    try:
        assert _count(container, CommandExecutionRecord) == 2
        assert _count(container, AuditEventRecord) == 2
        assert _count(container, DomainEventRecord) == 2
        with container.session_factory() as session:
            archived_events = list(
                session.execute(select(DomainEventRecord).where(DomainEventRecord.event_type == "ProjectArchived")).scalars()
            )
        assert len(archived_events) == 1
        assert archived_events[0].project_id == project_id
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
        except Exception as error:  # noqa: BLE001 - retry until Uvicorn is accepting connections.
            last_error = error
            time.sleep(0.05)
    raise AssertionError(f"Project API did not respond before timeout: {last_error}")


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as socket_:
        socket_.bind(("127.0.0.1", 0))
        return int(socket_.getsockname()[1])


def _count(container, model) -> int:
    with container.session_factory() as session:
        return len(list(session.execute(select(model)).scalars()))
