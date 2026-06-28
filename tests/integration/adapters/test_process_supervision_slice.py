from __future__ import annotations

import ctypes
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import func, select

from backend.adapters.persistence.models import (
    CommandExecutionRecord,
    DomainEventRecord,
    SetupProcessRunRecord,
    TelemetryQueueRecord,
    TelemetryRejectionRecord,
)
from backend.domain.shared_kernel import ProjectId
from backend.infrastructure.di import create_application_container


def test_start_stop_kills_full_process_tree_and_audits(tmp_path: Path) -> None:
    container, project_id = _container_with_project(tmp_path)
    service = container.create_setup_service()
    script = (
        "import subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "print(f'CHILD_PID={child.pid}', flush=True)\n"
        "while True: time.sleep(0.2)\n"
    )
    try:
        start = service.execute_start_server(project_id=project_id, fxserver_path=sys.executable, server_data_path=str(tmp_path), extra_args=["-c", script])
        process_run_id = start.result["process_run_id"]
        child_pid = _wait_for_child_pid(service, project_id, process_run_id)

        assert start.result["state"] == "running"
        assert _count(container, SetupProcessRunRecord) == 1
        assert _domain_event_types(container)[-1] == "ServerStarted"

        stop = service.execute_stop_server(project_id=project_id, process_run_id=process_run_id)

        assert stop.result["state"] == "stopped"
        assert _eventually_not_alive(int(start.result["pid"]))
        assert _eventually_not_alive(child_pid)
        commands = _command_types(container)
        assert "StartServerProcess" in commands
        assert "StopServerProcess" in commands
        assert _domain_event_types(container)[-1] == "ServerStopped"
    finally:
        container.close()


def test_restart_creates_new_running_process(tmp_path: Path) -> None:
    container, project_id = _container_with_project(tmp_path)
    service = container.create_setup_service()
    script = "import time\nprint('READY', flush=True)\nwhile True: time.sleep(0.2)\n"
    try:
        first = service.execute_start_server(project_id=project_id, fxserver_path=sys.executable, server_data_path=str(tmp_path), extra_args=["-c", script])
        second = service.execute_restart_server(
            project_id=project_id,
            process_run_id=first.result["process_run_id"],
            fxserver_path=sys.executable,
            server_data_path=str(tmp_path),
            extra_args=["-c", script],
        )
        try:
            assert first.result["process_run_id"] != second.result["process_run_id"]
            assert second.result["state"] == "running"
            assert _eventually_not_alive(int(first.result["pid"]))
            assert "RestartServerProcess" in _command_types(container)
        finally:
            service.execute_stop_server(project_id=project_id, process_run_id=second.result["process_run_id"])
    finally:
        container.close()


def test_unexpected_exit_records_local_crash_without_telemetry(tmp_path: Path) -> None:
    container, project_id = _container_with_project(tmp_path)
    service = container.create_setup_service()
    script = "import time, sys\nprint('CRASHING', flush=True)\ntime.sleep(0.2)\nsys.exit(7)\n"
    try:
        start = service.execute_start_server(project_id=project_id, fxserver_path=sys.executable, server_data_path=str(tmp_path), extra_args=["-c", script])
        process_run_id = start.result["process_run_id"]

        deadline = time.monotonic() + 5
        status = service.get_process_status(project_id, process_run_id)
        while status["state"] != "crashed" and time.monotonic() < deadline:
            time.sleep(0.05)
            status = service.get_process_status(project_id, process_run_id)

        assert status["state"] == "crashed"
        assert status["exit_code"] == 7

        while time.monotonic() < deadline:
            event_types = _domain_event_types(container)
            if "IncidentCaptured" in event_types:
                break
            time.sleep(0.05)

        event_types = _domain_event_types(container)
        assert "ServerCrashed" in event_types
        assert "IncidentCaptured" in event_types
        assert event_types[-1] == "IncidentCaptured"
        assert _count(container, TelemetryQueueRecord) == 0
        assert _count(container, TelemetryRejectionRecord) == 0
    finally:
        container.close()


def test_unexpected_exit_never_invokes_sentry_even_when_telemetry_enabled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_SENTRY_DSN", "https://examplePublicKey@o0.ingest.sentry.io/0")
    container, project_id = _container_with_project(tmp_path)
    service = container.create_setup_service()
    telemetry = container.create_telemetry_service()
    telemetry.execute_update_preferences(patch={"telemetry_enabled": True, "crash_reporting_enabled": True})
    script = "import time, sys\nprint('CRASHING', flush=True)\ntime.sleep(0.2)\nsys.exit(7)\n"
    try:
        with patch("backend.adapters.telemetry.sentry_delivery.sentry_sdk.capture_event") as mock_capture:
            with patch("backend.adapters.telemetry.sentry_delivery.sentry_sdk.init"):
                start = service.execute_start_server(
                    project_id=project_id,
                    fxserver_path=sys.executable,
                    server_data_path=str(tmp_path),
                    extra_args=["-c", script],
                )
                process_run_id = start.result["process_run_id"]

                deadline = time.monotonic() + 5
                status = service.get_process_status(project_id, process_run_id)
                while status["state"] != "crashed" and time.monotonic() < deadline:
                    time.sleep(0.05)
                    status = service.get_process_status(project_id, process_run_id)

                while time.monotonic() < deadline:
                    if "IncidentCaptured" in _domain_event_types(container):
                        break
                    time.sleep(0.05)

        assert status["state"] == "crashed"
        assert "IncidentCaptured" in _domain_event_types(container)
        assert _count(container, TelemetryQueueRecord) == 0
        mock_capture.assert_not_called()
    finally:
        container.close()


def test_process_project_id_isolation_blocks_cross_project_stop(tmp_path: Path) -> None:
    container, first_project_id = _container_with_project(tmp_path, "first")
    second_project_id = ProjectId(container.create_project_service().execute_import_project(root_path=_project_root(tmp_path, "second")).result["project_id"])
    service = container.create_setup_service()
    script = "import time\nwhile True: time.sleep(0.2)\n"
    try:
        start = service.execute_start_server(project_id=first_project_id, fxserver_path=sys.executable, server_data_path=str(tmp_path), extra_args=["-c", script])
        try:
            service.execute_stop_server(project_id=second_project_id, process_run_id=start.result["process_run_id"])
        except Exception as error:  # noqa: BLE001 - asserts scoped process lookup blocks before termination.
            assert "not found" in str(error).lower()
        else:
            raise AssertionError("cross-project stop was allowed")

        assert service.get_process_status(first_project_id, start.result["process_run_id"])["state"] == "running"
        service.execute_stop_server(project_id=first_project_id, process_run_id=start.result["process_run_id"])
    finally:
        container.close()


def _container_with_project(tmp_path: Path, name: str = "process-project"):
    container = create_application_container(tmp_path / "app-data")
    project_id = ProjectId(container.create_project_service().execute_import_project(root_path=_project_root(tmp_path, name)).result["project_id"])
    return container, project_id


def _project_root(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    (root / "resources").mkdir(parents=True)
    return root


def _wait_for_child_pid(service, project_id: ProjectId, process_run_id: str) -> int:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        status = service.get_process_status(project_id, process_run_id)
        for line in status["stdout_tail"]:
            if line.startswith("CHILD_PID="):
                return int(line.split("=", 1)[1])
        time.sleep(0.05)
    raise AssertionError("child pid was not captured")


def _eventually_not_alive(pid: int) -> bool:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return True
        time.sleep(0.05)
    return False


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        handle = ctypes.windll.kernel32.OpenProcess(0x0400, False, pid)
        if handle:
            exit_code = ctypes.c_ulong()
            ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            ctypes.windll.kernel32.CloseHandle(handle)
            return exit_code.value == 259
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _count(container, model) -> int:
    with container.session_factory() as session:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _domain_event_types(container) -> list[str]:
    with container.session_factory() as session:
        return list(session.execute(select(DomainEventRecord.event_type).order_by(DomainEventRecord.occurred_at)).scalars())


def _command_types(container) -> list[str]:
    with container.session_factory() as session:
        records = session.execute(select(CommandExecutionRecord).order_by(CommandExecutionRecord.started_at)).scalars()
        return [str((record.result_json or {}).get("command_type")) for record in records]
