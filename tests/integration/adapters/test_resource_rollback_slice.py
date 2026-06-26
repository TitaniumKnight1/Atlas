from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from sqlalchemy import func, select

from backend.adapters.persistence.models import TelemetryQueueRecord, TelemetryRejectionRecord
from backend.application.commands.compensation import CompositeCompensation
from backend.application.resources import InstallSource
from backend.application.resources.server_cfg_ops import list_ensure_lines
from backend.domain.shared_kernel import ProjectId
from backend.domain.shared_kernel.events import DomainEventEnvelope
from backend.infrastructure.di import create_application_container


def test_clean_batch_rollback_reverses_all_resources_in_order(tmp_path: Path) -> None:
    container, project_id, resources_root, staging = _fixture(tmp_path)
    lifecycle = container.create_resource_lifecycle_service()
    rollback = container.create_resource_rollback_service()
    server_cfg = _server_cfg_path(resources_root)
    before_cfg = server_cfg.read_text(encoding="utf-8")
    try:
        installs = [
            lifecycle.execute_install_resource(
                project_id=project_id,
                source=InstallSource("local", str(staging / name)),
                enable=True,
            )
            for name in ("delta", "epsilon", "zeta")
        ]
        container.create_resource_service().execute_rescan_resources(project_id=project_id, path_filters=[str(resources_root)])
        execution_ids = [str(item.command_execution_id) for item in installs]
        preview = rollback.preview_rollback_batch(project_id=project_id, command_execution_ids=execution_ids)
        assert preview.preview["ok"] is True
        assert preview.preview["order"] == ["zeta", "epsilon", "delta"]

        result = rollback.execute_rollback_batch(project_id=project_id, command_execution_ids=execution_ids)
        assert result.result["status"] == "completed"
        assert result.result["succeeded"] == ["zeta", "epsilon", "delta"]
        assert not (resources_root / "delta").exists()
        assert not (resources_root / "epsilon").exists()
        assert not (resources_root / "zeta").exists()
        assert server_cfg.read_text(encoding="utf-8") == before_cfg
    finally:
        container.close()


def test_mid_rollback_failure_stop_and_hold_with_precise_persisted_outcomes(tmp_path: Path) -> None:
    container, project_id, resources_root, staging = _fixture(tmp_path)
    lifecycle = container.create_resource_lifecycle_service()
    rollback = container.create_resource_rollback_service()
    try:
        installs = [
            lifecycle.execute_install_resource(
                project_id=project_id,
                source=InstallSource("local", str(staging / name)),
                enable=True,
            )
            for name in ("delta", "epsilon", "zeta")
        ]
        container.create_resource_service().execute_rescan_resources(project_id=project_id, path_filters=[str(resources_root)])
        execution_ids = [str(item.command_execution_id) for item in installs]
        original_apply = CompositeCompensation.apply
        calls = {"count": 0}

        def failing_apply(self, context):  # noqa: ANN001
            calls["count"] += 1
            if calls["count"] == 2:
                raise RuntimeError("forced rollback failure")
            return original_apply(self, context)

        with patch.object(CompositeCompensation, "apply", failing_apply):
            result = rollback.execute_rollback_batch(project_id=project_id, command_execution_ids=execution_ids)

        assert result.result["status"] == "halted"
        assert result.result["succeeded"] == ["zeta"]
        assert result.result["failed"]["resource_name"] == "epsilon"
        assert result.result["not_attempted"] == ["delta"]
        assert not (resources_root / "zeta").exists()
        assert (resources_root / "epsilon").exists()
        assert (resources_root / "delta").exists()

        run = rollback.get_rollback_run(project_id, result.result["rollback_run_id"])
        assert run["status"] == "halted"
        statuses = [item["status"] for item in run["outcomes"]]
        assert statuses == ["succeeded", "failed", "not_attempted"]
        assert run["outcomes"][1]["error_message"] == "forced rollback failure"
    finally:
        container.close()


def test_rollback_blocks_when_enabled_dependent_outside_batch(tmp_path: Path) -> None:
    container, project_id, resources_root, staging = _fixture(tmp_path)
    lifecycle = container.create_resource_lifecycle_service()
    rollback = container.create_resource_rollback_service()
    resources = container.create_resource_service()
    try:
        resources.execute_rescan_resources(project_id=project_id, path_filters=[str(resources_root)])
        gamma = next(item for item in resources.list_resources(project_id) if item["resource_name"] == "gamma")
        lifecycle.execute_set_enabled_state(project_id=project_id, resource_id=gamma["resource_id"], enabled=False)
        lifecycle.execute_set_enabled_state(project_id=project_id, resource_id=gamma["resource_id"], enabled=True)
        lifecycle.execute_install_resource(
            project_id=project_id,
            source=InstallSource("local", str(staging / "delta")),
            enable=True,
        )
        resources.execute_rescan_resources(project_id=project_id, path_filters=[str(resources_root)])
        preview = rollback.preview_rollback_batch(project_id=project_id, resource_ids=[gamma["resource_id"]])
        assert any("outside batch" in warning.lower() for warning in preview.warnings)
        dry_run = rollback.dry_run_rollback_batch(project_id=project_id, resource_ids=[gamma["resource_id"]])
        assert dry_run.valid is False
    finally:
        container.close()


def test_cycle_batch_refused_without_hanging(tmp_path: Path) -> None:
    container, project_id, resources_root, _ = _fixture(tmp_path, include_cycle=True)
    lifecycle = container.create_resource_lifecycle_service()
    rollback = container.create_resource_rollback_service()
    resources = container.create_resource_service()
    try:
        resources.execute_rescan_resources(project_id=project_id, path_filters=[str(resources_root)])
        cycle_a = next(item for item in resources.list_resources(project_id) if item["resource_name"] == "cycle_a")
        cycle_b = next(item for item in resources.list_resources(project_id) if item["resource_name"] == "cycle_b")
        lifecycle.execute_set_enabled_state(project_id=project_id, resource_id=cycle_a["resource_id"], enabled=True)
        lifecycle.execute_set_enabled_state(project_id=project_id, resource_id=cycle_b["resource_id"], enabled=True)
        preview = rollback.preview_rollback_batch(
            project_id=project_id,
            resource_ids=[cycle_a["resource_id"], cycle_b["resource_id"]],
        )
        assert preview.preview["ok"] is False
        assert preview.preview.get("order_error") or preview.preview.get("findings")
    finally:
        container.close()


def test_rollback_publishes_operation_progress(tmp_path: Path) -> None:
    container, project_id, resources_root, staging = _fixture(tmp_path)
    lifecycle = container.create_resource_lifecycle_service()
    rollback = container.create_resource_rollback_service()
    progress: list[dict] = []

    def _capture(event: DomainEventEnvelope) -> None:
        progress.append(event.payload)

    container.event_bus.register("OperationProgress", _capture)
    try:
        install = lifecycle.execute_install_resource(
            project_id=project_id,
            source=InstallSource("local", str(staging / "delta")),
            enable=True,
        )
        rollback.execute_rollback_batch(
            project_id=project_id,
            command_execution_ids=[str(install.command_execution_id)],
        )
        assert progress
    finally:
        container.close()


def test_rollback_batch_does_not_write_resource_content_to_telemetry(tmp_path: Path) -> None:
    container, project_id, resources_root, staging = _fixture(tmp_path)
    lifecycle = container.create_resource_lifecycle_service()
    rollback = container.create_resource_rollback_service()
    try:
        install = lifecycle.execute_install_resource(
            project_id=project_id,
            source=InstallSource("local", str(staging / "delta")),
            enable=True,
        )
        rollback.execute_rollback_batch(
            project_id=project_id,
            command_execution_ids=[str(install.command_execution_id)],
        )
        with container.session_factory() as session:
            assert int(session.scalar(select(func.count()).select_from(TelemetryQueueRecord)) or 0) == 0
            assert int(session.scalar(select(func.count()).select_from(TelemetryRejectionRecord)) or 0) == 0
    finally:
        container.close()


def _fixture(tmp_path: Path, include_cycle: bool = False):
    container = create_application_container(tmp_path / "app-data")
    root = _project_root(tmp_path, "rollback-project")
    resources_root = root / "resources"
    resources_root.mkdir(parents=True)
    server_data = root / "server-data"
    server_data.mkdir(parents=True)
    (server_data / "server.cfg").write_text(
        'endpoint_add_tcp "0.0.0.0:30120"\nendpoint_add_udp "0.0.0.0:30120"\nsv_licenseKey "cfxk_test"\nensure gamma\n',
        encoding="utf-8",
    )
    _write_resource(resources_root / "gamma", "gamma", [])
    if include_cycle:
        _write_resource(resources_root / "cycle_a", "cycle_a", ["cycle_b"])
        _write_resource(resources_root / "cycle_b", "cycle_b", ["cycle_a"])
    staging = tmp_path / "staging"
    staging.mkdir()
    _write_resource(staging / "delta", "delta", ["gamma"])
    _write_resource(staging / "epsilon", "epsilon", ["delta"])
    _write_resource(staging / "zeta", "zeta", ["epsilon"])
    project_id = ProjectId(container.create_project_service().execute_import_project(root_path=root).result["project_id"])
    container.create_config_service().execute_rescan_config_files(project_id=project_id, scan_roots=[str(server_data)])
    return container, project_id, resources_root, staging


def _project_root(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    root.mkdir(parents=True)
    return root


def _server_cfg_path(resources_root: Path) -> Path:
    return resources_root.parent / "server-data" / "server.cfg"


def _write_resource(path: Path, name: str, dependencies: list[str]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    deps = ",\n  ".join(f"'{item}'" for item in dependencies)
    body = f"""fx_version 'cerulean'
game 'gta5'
version '1.0.0'
dependencies {{
  {deps}
}}
"""
    (path / "fxmanifest.lua").write_text(body, encoding="utf-8")
