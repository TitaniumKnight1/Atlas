from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.application.commands import UndoPlan
from backend.application.dev_db.compensation import ClearDevDatabaseSettingsCompensation
from backend.domain.dev_db.types import (
    DevDatabaseEngine,
    DevDatabaseLifecycleStatus,
    DevDatabasePlan,
    DevDatabaseRuntimeStatus,
    DockerAvailabilityState,
    DockerProbeResult,
)
from backend.domain.pathway2.settings import Pathway2SettingKeys
from backend.domain.shared_kernel import ProjectId
from backend.infrastructure.di import create_application_container
from backend.infrastructure.unit_of_work import SingleWriterSQLiteUnitOfWork


def test_provision_long_work_happens_before_uow(tmp_path: Path) -> None:
    container, project_id = _container_with_project(tmp_path)
    try:
        service = container.create_dev_database_service()
        plan = _sample_plan(str(project_id))
        runtime = _sample_runtime(plan)

        events: list[str] = []
        original_enter = SingleWriterSQLiteUnitOfWork.__enter__

        def track_enter(self):
            events.append("uow")
            return original_enter(self)

        def pull_image(_plan):
            events.append("pull")

        fake_port = MagicMock()
        fake_port.build_plan.return_value = plan
        fake_port.pull_image.side_effect = pull_image
        fake_port.provision.return_value = runtime
        fake_port.inspect.return_value = runtime

        fake_probe = MagicMock()
        fake_probe.probe.return_value = DockerProbeResult(state=DockerAvailabilityState.AVAILABLE, client_version="29")

        service._dev_db_port = fake_port
        service._docker_probe = fake_probe

        with patch.object(SingleWriterSQLiteUnitOfWork, "__enter__", track_enter):
            with patch("backend.application.dev_db.service.wait_for_mysql_ready", return_value=(True, True)):
                with patch("backend.application.dev_db.service.build_dev_db_port_available_check", return_value={"status": "pass", "message": "free"}):
                    result = service.execute_provision_dev_database(project_id=project_id)

        assert events.index("pull") < events.index("uow")
        assert result.result["connection_string"] == plan.connection_string
        fake_port.pull_image.assert_called_once()
    finally:
        container.close()


def test_undo_provision_default_keeps_volume(tmp_path: Path) -> None:
    container, project_id = _container_with_project(tmp_path)
    try:
        service = container.create_dev_database_service()
        plan = _sample_plan(str(project_id))
        fake_port = MagicMock()
        fake_port.remove.return_value = {"removed_container": True, "removed_volume": False}
        service._dev_db_port = fake_port

        undo_plan = UndoPlan(
            "UndoProvisionDevDatabase",
            "Remove dev database container (keep named volume)",
            ClearDevDatabaseSettingsCompensation(str(project_id)),
            {
                "project_id": str(project_id),
                "engine": "mysql",
                "image": "mysql:8.0",
                "container_name": plan.container_name,
                "volume_name": plan.volume_name,
                "host": plan.host,
                "port": plan.port,
                "database": plan.database,
                "user": plan.user,
                "password": plan.password,
                "connection_string": plan.connection_string,
                "publish_host_port": plan.publish_host_port,
                "remove_volume": False,
            },
        )

        service.undo(undo_plan)
        fake_port.remove.assert_called_once_with(plan, remove_volume=False)
    finally:
        container.close()


def test_dry_run_invalid_when_docker_unavailable(tmp_path: Path) -> None:
    container, project_id = _container_with_project(tmp_path)
    try:
        service = container.create_dev_database_service()
        fake_probe = MagicMock()
        fake_probe.probe.return_value = DockerProbeResult(state=DockerAvailabilityState.CLI_MISSING, client_version=None)
        service._docker_probe = fake_probe

        dry_run = service.dry_run_provision_dev_database(project_id=project_id)
        assert dry_run.valid is False
        assert dry_run.warnings
    finally:
        container.close()


def _sample_plan(project_id: str) -> DevDatabasePlan:
    return DevDatabasePlan(
        project_id=project_id,
        engine=DevDatabaseEngine.MYSQL,
        image="mysql:8.0",
        container_name=f"atlas-dev-mysql-{project_id}",
        volume_name=f"atlas-dev-mysql-{project_id}",
        host="127.0.0.1",
        port=3306,
        database="atlas_dev",
        user="atlas_dev",
        password="atlas_dev",
        connection_string="mysql://atlas_dev:atlas_dev@127.0.0.1:3306/atlas_dev",
        publish_host_port="127.0.0.1:3306:3306",
    )


def _sample_runtime(plan: DevDatabasePlan) -> DevDatabaseRuntimeStatus:
    return DevDatabaseRuntimeStatus(
        lifecycle=DevDatabaseLifecycleStatus.REACHABLE,
        engine=DevDatabaseEngine.MYSQL,
        container_id="cid-1",
        container_name=plan.container_name,
        volume_name=plan.volume_name,
        container_running=True,
        mysql_reachable=True,
        connection_string=plan.connection_string,
    )


def _container_with_project(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir(parents=True)
    (root / "resources").mkdir()
    container = create_application_container(tmp_path / "app-data")
    project_id = ProjectId(container.create_project_service().execute_import_project(root_path=root).result["project_id"])
    return container, project_id
