from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from sqlalchemy import func, select

from backend.adapters.persistence.models import TelemetryQueueRecord, TelemetryRejectionRecord
from backend.application.resources import InstallSource
from backend.application.resources.server_cfg_ops import list_ensure_lines
from backend.domain.shared_kernel import ProjectId
from backend.domain.shared_kernel.events import DomainEventEnvelope
from backend.infrastructure.di import create_application_container


def test_install_preview_and_dry_run_do_not_mutate(tmp_path: Path) -> None:
    container, project_id, resources_root, staging = _fixture(tmp_path)
    lifecycle = container.create_resource_lifecycle_service()
    server_cfg = _server_cfg_path(resources_root)
    before_cfg = server_cfg.read_text(encoding="utf-8")
    try:
        preview = lifecycle.preview_install_resource(
            project_id=project_id,
            source=InstallSource("local", str(staging / "delta")),
            enable=True,
        )
        assert any("missing-lib" in warning for warning in preview.warnings)
        dry_run = lifecycle.dry_run_install_resource(
            project_id=project_id,
            source=InstallSource("local", str(staging / "delta")),
            enable=True,
        )
        assert dry_run.valid is True
        assert not (resources_root / "delta").exists()
        assert server_cfg.read_text(encoding="utf-8") == before_cfg
    finally:
        container.close()


def test_install_execute_and_composite_undo_restore_files_and_server_cfg(tmp_path: Path) -> None:
    container, project_id, resources_root, staging = _fixture(tmp_path)
    lifecycle = container.create_resource_lifecycle_service()
    server_cfg = _server_cfg_path(resources_root)
    before_cfg = server_cfg.read_text(encoding="utf-8")
    try:
        result = lifecycle.execute_install_resource(
            project_id=project_id,
            source=InstallSource("local", str(staging / "delta")),
            enable=True,
        )
        assert (resources_root / "delta").exists()
        after_cfg = server_cfg.read_text(encoding="utf-8")
        assert "ensure delta" in after_cfg
        order = list_ensure_lines(after_cfg)
        assert order.index("gamma") < order.index("delta")

        lifecycle.undo(result.undo_plan)
        assert not (resources_root / "delta").exists()
        assert server_cfg.read_text(encoding="utf-8") == before_cfg
    finally:
        container.close()


def test_disable_warns_and_blocks_when_enabled_dependents_exist(tmp_path: Path) -> None:
    container, project_id, resources_root, _ = _fixture(tmp_path)
    lifecycle = container.create_resource_lifecycle_service()
    resources = container.create_resource_service()
    try:
        resources.execute_rescan_resources(project_id=project_id, path_filters=[str(resources_root)])
        gamma = next(item for item in resources.list_resources(project_id) if item["resource_name"] == "gamma")
        preview = lifecycle.preview_set_enabled_state(project_id=project_id, resource_id=gamma["resource_id"], enabled=False)
        assert any("enabled dependent" in warning.lower() for warning in preview.warnings)
        dry_run = lifecycle.dry_run_set_enabled_state(project_id=project_id, resource_id=gamma["resource_id"], enabled=False)
        assert dry_run.valid is False
    finally:
        container.close()


def test_update_undo_restores_prior_version_files(tmp_path: Path) -> None:
    container, project_id, resources_root, staging = _fixture(tmp_path)
    lifecycle = container.create_resource_lifecycle_service()
    resources = container.create_resource_service()
    target = resources_root / "gamma"
    try:
        resources.execute_rescan_resources(project_id=project_id, path_filters=[str(resources_root)])
        gamma = next(item for item in resources.list_resources(project_id) if item["resource_name"] == "gamma")
        original = (target / "fxmanifest.lua").read_text(encoding="utf-8")
        updated_source = staging / "gamma-v2"
        shutil.copytree(target, updated_source)
        (updated_source / "fxmanifest.lua").write_text(original.replace("1.0.0", "2.0.0"), encoding="utf-8")
        result = lifecycle.execute_update_resource(
            project_id=project_id,
            resource_id=gamma["resource_id"],
            source=InstallSource("local", str(updated_source)),
        )
        assert "2.0.0" in (target / "fxmanifest.lua").read_text(encoding="utf-8")
        lifecycle.undo(result.undo_plan)
        assert "1.0.0" in (target / "fxmanifest.lua").read_text(encoding="utf-8")
    finally:
        container.close()


def test_zip_install_publishes_operation_progress(tmp_path: Path) -> None:
    container, project_id, resources_root, staging = _fixture(tmp_path)
    lifecycle = container.create_resource_lifecycle_service()
    progress: list[dict] = []

    def _capture(event: DomainEventEnvelope) -> None:
        progress.append(event.payload)

    container.event_bus.register("OperationProgress", _capture)
    archive = staging / "delta.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for path in (staging / "delta").rglob("*"):
            if path.is_file():
                zf.write(path, arcname=str(Path("delta") / path.relative_to(staging / "delta")))
    try:
        lifecycle.execute_install_resource(
            project_id=project_id,
            source=InstallSource("zip", str(archive)),
            enable=False,
        )
        assert progress
        assert any(item.get("message") for item in progress)
    finally:
        container.close()


def test_mutations_do_not_write_resource_content_to_telemetry(tmp_path: Path) -> None:
    container, project_id, resources_root, staging = _fixture(tmp_path)
    lifecycle = container.create_resource_lifecycle_service()
    try:
        lifecycle.execute_install_resource(
            project_id=project_id,
            source=InstallSource("local", str(staging / "delta")),
            enable=True,
        )
        with container.session_factory() as session:
            assert int(session.scalar(select(func.count()).select_from(TelemetryQueueRecord)) or 0) == 0
            assert int(session.scalar(select(func.count()).select_from(TelemetryRejectionRecord)) or 0) == 0
    finally:
        container.close()


def test_project_isolation_on_delete(tmp_path: Path) -> None:
    container, project_id, resources_root, staging = _fixture(tmp_path)
    lifecycle = container.create_resource_lifecycle_service()
    other_project = ProjectId(container.create_project_service().execute_import_project(root_path=_project_root(tmp_path, "other")).result["project_id"])
    container.create_config_service().execute_rescan_config_files(project_id=other_project, scan_roots=[str(resources_root.parent / "server-data")])
    try:
        result = lifecycle.execute_install_resource(
            project_id=project_id,
            source=InstallSource("local", str(staging / "delta")),
            enable=False,
        )
        resource_id = result.result["resource_id"]
        try:
            lifecycle.execute_delete_resource(project_id=other_project, resource_id=resource_id)
        except Exception as error:  # noqa: BLE001
            assert "not found" in str(error).lower()
        else:
            raise AssertionError("cross-project delete was allowed")
    finally:
        container.close()


def _fixture(tmp_path: Path):
    container = create_application_container(tmp_path / "app-data")
    root = _project_root(tmp_path, "lifecycle-project")
    resources_root = root / "resources"
    resources_root.mkdir(parents=True)
    server_data = root / "server-data"
    server_data.mkdir(parents=True)
    server_cfg = server_data / "server.cfg"
    server_cfg.write_text(
        'endpoint_add_tcp "0.0.0.0:30120"\nendpoint_add_udp "0.0.0.0:30120"\nsv_licenseKey "cfxk_test"\nensure gamma\nensure alpha\n',
        encoding="utf-8",
    )
    _write_resource(resources_root / "gamma", "gamma", [])
    _write_resource(resources_root / "alpha", "alpha", ["beta", "gamma"])
    _write_resource(resources_root / "beta", "beta", ["gamma"])
    staging = tmp_path / "staging"
    staging.mkdir()
    _write_resource(staging / "delta", "delta", ["gamma", "missing-lib"])
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


def test_undo_resource_install_via_command_execution_id(tmp_path: Path) -> None:
    container, project_id, resources_root, staging = _fixture(tmp_path)
    lifecycle = container.create_resource_lifecycle_service()
    project_svc = container.create_project_service()
    server_cfg = _server_cfg_path(resources_root)
    before_cfg = server_cfg.read_text(encoding="utf-8")
    try:
        result = lifecycle.execute_install_resource(
            project_id=project_id,
            source=InstallSource("local", str(staging / "delta")),
            enable=True,
        )
        assert (resources_root / "delta").exists()
        
        # Round trip via command execution ID
        rollback_svc = container.create_resource_rollback_service()
        rollback_svc.execute_rollback_batch(
            project_id=project_id,
            command_execution_ids=[str(result.command_execution_id)]
        )
        
        assert not (resources_root / "delta").exists()
        assert server_cfg.read_text(encoding="utf-8") == before_cfg
    finally:
        container.close()

def test_delete_resource_and_rollback_restores_resource(tmp_path: Path) -> None:
    container, project_id, resources_root, staging = _fixture(tmp_path)
    lifecycle = container.create_resource_lifecycle_service()
    rollback_svc = container.create_resource_rollback_service()
    try:
        # 1. Install
        install_result = lifecycle.execute_install_resource(
            project_id=project_id,
            source=InstallSource("local", str(staging / "delta")),
            enable=True,
        )
        assert (resources_root / "delta").exists()
        resource_id = install_result.result["resource_id"]

        # 2. Delete
        delete_result = lifecycle.execute_delete_resource(
            project_id=project_id,
            resource_id=resource_id,
        )
        assert not (resources_root / "delta").exists()
        assert delete_result.command_execution_id is not None
        
        # 3. Rollback the deletion using the captured command execution ID
        rollback_result = rollback_svc.execute_rollback_batch(
            project_id=project_id,
            command_execution_ids=[str(delete_result.command_execution_id)]
        )
        assert rollback_result.result["status"] == "completed"
        assert (resources_root / "delta").exists()
    finally:
        container.close()
