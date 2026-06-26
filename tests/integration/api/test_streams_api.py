from __future__ import annotations

import json
import socket
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch
from urllib import request

import uvicorn
from sqlalchemy import func, select

from backend.adapters.fivem import LocalArtifactSource
from backend.adapters.persistence.models import TelemetryQueueRecord
from backend.atlas_backend.app import create_app
from backend.domain.setup import ArtifactChannel, ArtifactPlatform, ArtifactVersion
from backend.domain.shared_kernel import ProjectId
from backend.infrastructure.di import create_application_container
from backend.infrastructure.streams import StreamTopic


def test_sse_stream_delivers_bus_events_with_project_isolation(tmp_path: Path) -> None:
    with patch("backend.api.routers.streams.HEARTBEAT_INTERVAL_SECONDS", 0.1):
        port = _free_loopback_port()
        app = create_app(app_data_dir=tmp_path / "app-data")
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, lifespan="on", log_level="warning", access_log=False))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{port}"
        try:
            project_a = _request_json(f"{base_url}/api/v1/projects/import", {"root_path": str(_project_root(tmp_path, "alpha"))})["data"]["project_id"]
            project_b = _request_json(f"{base_url}/api/v1/projects/import", {"root_path": str(_project_root(tmp_path, "beta"))})["data"]["project_id"]
            received: list[dict] = []
            stop = threading.Event()

            def consume_stream() -> None:
                req = request.Request(
                    f"{base_url}/api/v1/projects/{project_a}/stream?topics=server-output,process-lifecycle",
                    headers={"Accept": "text/event-stream"},
                )
                with request.urlopen(req, timeout=5) as response:
                    buffer = ""
                    while not stop.is_set():
                        chunk = response.read(512)
                        if not chunk:
                            break
                        buffer += chunk.decode("utf-8")
                        while "\n\n" in buffer:
                            block, buffer = buffer.split("\n\n", 1)
                            event = _parse_sse_block(block)
                            if event:
                                received.append(event)

            consumer = threading.Thread(target=consume_stream, daemon=True)
            consumer.start()
            time.sleep(0.2)

            container = app.state.container
            container.stream_publisher.publish_server_output_line(
                project_id=ProjectId(project_a),
                process_run_id="run-a",
                stream="stdout",
                line="alpha-line",
            )
            container.stream_publisher.publish_server_output_line(
                project_id=ProjectId(project_b),
                process_run_id="run-b",
                stream="stdout",
                line="beta-line",
            )
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if any(item.get("payload", {}).get("line") == "alpha-line" for item in received):
                    break
                time.sleep(0.05)
            stop.set()
            consumer.join(timeout=2)
        finally:
            server.should_exit = True
            thread.join(timeout=5)

        assert any(item.get("payload", {}).get("line") == "alpha-line" for item in received)
        assert all(item.get("project_id") == project_a for item in received if item.get("event_type") == "ServerOutputLine")
        assert not any(item.get("payload", {}).get("line") == "beta-line" for item in received)


def test_process_output_reaches_stream_without_telemetry(tmp_path: Path) -> None:
    container = create_application_container(tmp_path / "app-data")
    project_id = ProjectId(
        container.create_project_service().execute_import_project(root_path=_project_root(tmp_path, "stream-project")).result["project_id"]
    )
    service = container.create_setup_service()
    script = "print('STREAM-TEST', flush=True)\nimport time\ntime.sleep(0.5)\n"
    try:
        start = service.execute_start_server(
            project_id=project_id,
            fxserver_path=sys.executable,
            server_data_path=str(tmp_path),
            extra_args=["-c", script],
        )
        subscriber = container.stream_hub.subscribe(str(project_id), {StreamTopic.SERVER_OUTPUT})
        deadline = time.monotonic() + 5
        lines: list[str] = []
        while time.monotonic() < deadline and not lines:
            event = subscriber.wait_next(timeout=0.5)
            if event and event.payload.get("line") == "STREAM-TEST":
                lines.append(str(event.payload["line"]))
        service.execute_stop_server(project_id=project_id, process_run_id=start.result["process_run_id"])
        container.stream_hub.unsubscribe(subscriber)
        assert lines == ["STREAM-TEST"]
        with container.session_factory() as session:
            assert int(session.scalar(select(func.count()).select_from(TelemetryQueueRecord)) or 0) == 0
    finally:
        container.close()


def test_stream_subscriber_is_removed_after_disconnect(tmp_path: Path) -> None:
    with patch("backend.api.routers.streams.HEARTBEAT_INTERVAL_SECONDS", 0.1):
        port = _free_loopback_port()
        app = create_app(app_data_dir=tmp_path / "app-data")
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, lifespan="on", log_level="warning", access_log=False))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{port}"
        try:
            project_id = _request_json(f"{base_url}/api/v1/projects/import", {"root_path": str(_project_root(tmp_path, "teardown"))})["data"]["project_id"]
            req = request.Request(
                f"{base_url}/api/v1/projects/{project_id}/stream?topics=op-progress",
                headers={"Accept": "text/event-stream"},
            )
            with request.urlopen(req, timeout=5) as response:
                response.read(128)
            time.sleep(0.3)
            assert app.state.container.stream_hub.subscriber_count == 0
        finally:
            server.should_exit = True
            thread.join(timeout=5)


def _container_with_project(tmp_path: Path):
    container = create_application_container(tmp_path / "app-data")
    container.artifact_client = LocalArtifactSource(_artifact(), _artifact_zip(tmp_path))
    return container


def _project_root(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    (root / "resources").mkdir(parents=True)
    return root


def _artifact() -> ArtifactVersion:
    return ArtifactVersion(
        artifact_version_id="artifact-9999",
        platform=ArtifactPlatform.WINDOWS,
        channel=ArtifactChannel.RECOMMENDED,
        build_number="9999",
        download_url="file://local/fxserver.zip",
        sha256=None,
        size_bytes=1,
        metadata={"test": True},
    )


def _artifact_zip(tmp_path: Path) -> Path:
    import zipfile

    archive = tmp_path / "fxserver.zip"
    if not archive.exists():
        with zipfile.ZipFile(archive, "w") as zip_file:
            zip_file.writestr("FXServer.exe", "binary")
    return archive


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
        except Exception as error:  # noqa: BLE001
            last_error = error
            time.sleep(0.05)
    raise AssertionError(f"Stream API did not respond before timeout: {last_error}")


def _parse_sse_block(block: str) -> dict | None:
    event_type = "message"
    data: str | None = None
    for line in block.splitlines():
        if line.startswith("event:"):
            event_type = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data = line.split(":", 1)[1].strip()
    if not data:
        return None
    payload = json.loads(data)
    payload.setdefault("event_type", event_type if event_type not in {"message", "heartbeat"} else payload.get("event_type"))
    return payload


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as socket_:
        socket_.bind(("127.0.0.1", 0))
        return int(socket_.getsockname()[1])
