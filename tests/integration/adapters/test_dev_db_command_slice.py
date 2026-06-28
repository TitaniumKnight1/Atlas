from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from backend.adapters.persistence.models import CommandExecutionRecord
from backend.domain.pathway2.settings import Pathway2SettingKeys
from backend.domain.shared_kernel import ProjectId
from backend.infrastructure.di import create_application_container


def test_provision_undo_container_only_then_teardown_removes_volume(tmp_path: Path) -> None:
    container, project_id = _container_with_project(tmp_path)
    try:
        service = container.create_dev_database_service()
        plan = service._dev_db_port.build_plan(str(project_id))
        inspect_running = _inspect_json(running=True)
        inspect_absent = None

        with patch(
            "backend.adapters.docker.mysql_dev_database.subprocess.run",
            side_effect=_provision_side_effect(inspect_running, inspect_absent),
        ):
            with patch("backend.adapters.docker.cli_probe.subprocess.run", side_effect=_docker_probe_side_effect):
                with patch("backend.domain.dev_db.checks.is_tcp_port_listening", return_value=False):
                    with patch("backend.application.dev_db.service.build_dev_db_port_available_check", return_value={"status": "pass", "message": "free"}):
                        with patch("backend.application.dev_db.service.wait_for_mysql_ready", return_value=(True, True)):
                            dry_run = service.dry_run_provision_dev_database(project_id=project_id)
                            assert dry_run.valid is True
                            result = service.execute_provision_dev_database(project_id=project_id)

        assert result.result["connection_string"] == "mysql://atlas_dev:atlas_dev@127.0.0.1:3306/atlas_dev"
        assert result.result["status"]["mysql_reachable"] is True
        settings = _read_settings(container, project_id)
        assert settings[Pathway2SettingKeys.DEV_DB_CONTAINER_NAME] == plan.container_name
        assert settings[Pathway2SettingKeys.DEV_DB_VOLUME_NAME] == plan.volume_name

        remove_calls: list[list[str]] = []
        inspect_payload = _inspect_json(running=False)

        def remove_side_effect(args, **kwargs):
            remove_calls.append(args)
            if args[:3] == ["docker", "inspect", "--format"]:
                return _completed(stdout=inspect_payload)
            return _completed()

        assert result.undo_plan is not None
        with patch("backend.adapters.docker.mysql_dev_database.subprocess.run", side_effect=remove_side_effect):
            service.undo(result.undo_plan)

        assert any(call[:3] == ["docker", "rm", "-f"] for call in remove_calls)
        assert not any(call[:3] == ["docker", "volume", "rm"] for call in remove_calls)
        assert _read_settings(container, project_id).get(Pathway2SettingKeys.DEV_DB_CONTAINER_NAME) is None

        volume_rm_calls: list[list[str]] = []

        def teardown_side_effect(args, **kwargs):
            volume_rm_calls.append(args)
            if args[:3] == ["docker", "inspect", "--format"]:
                return _completed(returncode=1)
            return _completed()

        with patch("backend.adapters.docker.mysql_dev_database.subprocess.run", side_effect=teardown_side_effect):
            teardown = service.execute_teardown_dev_database(project_id=project_id)

        assert any(call[:3] == ["docker", "volume", "rm"] for call in volume_rm_calls)
        assert teardown.result["removal"]["remove_volume"] is True
    finally:
        container.close()


def _provision_side_effect(inspect_running: str, inspect_absent):
    state = {"seen_run": False}

    def side_effect(args, **kwargs):
        if args[:2] == ["docker", "pull"]:
            return _completed()
        if args[:2] == ["docker", "volume"]:
            return _completed()
        if args[:2] == ["docker", "run"]:
            state["seen_run"] = True
            return _completed(stdout="container-id-123\n")
        if args[:3] == ["docker", "inspect", "--format"]:
            if state["seen_run"]:
                return _completed(stdout=inspect_running)
            return _completed(returncode=1, stderr="No such object")
        return _completed()

    return side_effect


def _docker_probe_side_effect(args, **kwargs):
    if args[:2] == ["docker", "version"]:
        return _completed(stdout='{"Client":{"Version":"29.0.0"}}')
    if args[:2] == ["docker", "info"]:
        return _completed(stdout="Server Version: 29.0.0")
    return _completed()


def _inspect_json(*, running: bool) -> str:
    return json.dumps({"Id": "cid-123", "State": {"Running": running, "Status": "running" if running else "exited"}})


def _completed(returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _container_with_project(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir(parents=True)
    (root / "resources").mkdir()
    container = create_application_container(tmp_path / "app-data")
    project_id = ProjectId(container.create_project_service().execute_import_project(root_path=root).result["project_id"])
    return container, project_id


def _read_settings(container, project_id: ProjectId) -> dict[str, str]:
    service = container.create_project_service()
    return service.get_project_settings(project_id)
