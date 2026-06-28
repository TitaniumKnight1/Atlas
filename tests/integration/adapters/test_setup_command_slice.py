from __future__ import annotations

import zipfile
from pathlib import Path

from sqlalchemy import select

from backend.adapters.fivem import LocalArtifactSource
from backend.adapters.persistence.models import AuditEventRecord, CommandExecutionRecord, DependencyCheckRecord, DomainEventRecord, SetupRunRecord, SetupRunStepRecord
from backend.domain.setup import ArtifactChannel, ArtifactPlatform, ArtifactVersion
from backend.domain.shared_kernel import ProjectId, StableIdentifier
from backend.infrastructure.di import create_application_container


def test_artifact_preview_dry_run_execute_progress_and_undo(tmp_path: Path) -> None:
    container, project_id = _container_with_project(tmp_path)
    try:
        service = container.create_setup_service()
        before_files = list((tmp_path / "app-data").glob("**/*"))
        preview = service.preview_install_artifact(project_id=project_id, build_number="9999")
        dry_run = service.dry_run_install_artifact(project_id=project_id, build_number="9999")

        assert preview.command_type == "InstallFxServerArtifact"
        assert dry_run.valid is True
        assert list((tmp_path / "app-data").glob("**/*")) == before_files

        result = service.execute_install_artifact(project_id=project_id, build_number="9999")
        extract_path = Path(str(result.result["extract_path"]))

        assert (extract_path / "FXServer.exe").exists()
        assert result.result["progress"][0]["bytes_received"] > 0
        assert _count(container, CommandExecutionRecord) == 2  # import + install
        assert _domain_event_types(container)[-1] == "ArtifactInstalled"

        assert result.undo_plan is not None
        service.undo(result.undo_plan)
        assert not extract_path.exists()
    finally:
        container.close()


def test_server_cfg_preview_execute_survives_restart_and_undo_restores(tmp_path: Path) -> None:
    container, project_id = _container_with_project(tmp_path)
    server_data = tmp_path / "server-data"
    server_data.mkdir()
    existing = server_data / "server.cfg"
    existing.write_text("sv_hostname \"Old\"\n", encoding="utf-8")
    try:
        service = container.create_setup_service()
        preview = service.preview_generate_server_cfg(
            project_id=project_id,
            server_data_path=str(server_data),
            options={"hostname": "Atlas Test", "license_key": "CHANGE_ME", "max_clients": 32},
        )
        dry_run = service.dry_run_generate_server_cfg(
            project_id=project_id,
            server_data_path=str(server_data),
            options={"hostname": "Atlas Test", "license_key": "CHANGE_ME", "max_clients": 32},
        )

        assert "Existing server.cfg" in preview.warnings[0]
        assert dry_run.valid is True
        assert existing.read_text(encoding="utf-8") == "sv_hostname \"Old\"\n"

        result = service.execute_generate_server_cfg(
            project_id=project_id,
            server_data_path=str(server_data),
            options={"hostname": "Atlas Test", "license_key": "CHANGE_ME", "max_clients": 32},
        )
        assert 'endpoint_add_tcp "0.0.0.0:30120"' in existing.read_text(encoding="utf-8")
    finally:
        container.close()

    restarted = create_application_container(tmp_path / "app-data")
    restarted.artifact_client = LocalArtifactSource(_artifact(), _artifact_zip(tmp_path))
    try:
        service = restarted.create_setup_service()
        assert existing.exists()
        assert result.undo_plan is not None
        service.undo(result.undo_plan)
        assert existing.read_text(encoding="utf-8") == "sv_hostname \"Old\"\n"
    finally:
        restarted.close()


def test_dependency_checks_and_database_prepare_are_audited_and_reversible(tmp_path: Path) -> None:
    container, project_id = _container_with_project(tmp_path)
    server_data = tmp_path / "server-data"
    try:
        service = container.create_setup_service()
        checks = service.execute_run_dependency_checks(project_id=project_id, server_data_path=str(server_data))
        database = service.execute_prepare_database(project_id=project_id, server_data_path=str(server_data))
        database_path = Path(str(database.result["database_path"]))

        check_keys = {item["check_key"] for item in checks.result["checks"]}
        assert check_keys >= {
            "server_data_directory",
            "server_cfg",
            "docker_available",
            "dev_db_port_available",
            "dev_db_reachable",
        }
        assert "database_placeholder" not in check_keys
        assert _count(container, DependencyCheckRecord) >= 5
        assert database_path.exists()
        assert database.result["reversible"] is True

        assert checks.undo_plan is not None
        service.undo(checks.undo_plan)
        assert _count(container, DependencyCheckRecord) == 0

        assert database.undo_plan is not None
        service.undo(database.undo_plan)
        assert not database_path.exists()

        database_path.parent.mkdir(parents=True, exist_ok=True)
        database_path.write_text("existing", encoding="utf-8")
        warning = service.preview_prepare_database(project_id=project_id, server_data_path=str(server_data))
        assert warning.warnings == ["Existing database files are not modified and are not safely reversible."]
    finally:
        container.close()


def test_setup_run_records_step_command_refs_and_project_isolation(tmp_path: Path) -> None:
    container, first_project_id = _container_with_project(tmp_path, name="first")
    second_project_id = ProjectId(container.create_project_service().execute_import_project(root_path=_project_root(tmp_path, "second")).result["project_id"])
    server_data = tmp_path / "server-data"
    try:
        service = container.create_setup_service()
        result = service.execute_run_server_setup(
            project_id=first_project_id,
            server_data_path=str(server_data),
            build_number="9999",
            options={"hostname": "Atlas Run", "license_key": "CHANGE_ME"},
        )
        setup_run_id = StableIdentifier(str(result.result["setup_run_id"]))

        run = service.get_setup_run(first_project_id, setup_run_id)
        assert run["status"] == "succeeded"
        assert len(run["steps"]) == 4
        assert _count(container, SetupRunRecord) == 1
        assert _count(container, SetupRunStepRecord) == 4

        missing = service.get_setup_run
        try:
            missing(second_project_id, setup_run_id)
        except Exception as error:  # noqa: BLE001 - assert scoped not found without depending on concrete API type.
            assert "not found" in str(error).lower()
        else:
            raise AssertionError("setup run crossed project scope")
    finally:
        container.close()


def _container_with_project(tmp_path: Path, name: str = "setup-project"):
    container = create_application_container(tmp_path / "app-data")
    container.artifact_client = LocalArtifactSource(_artifact(), _artifact_zip(tmp_path))
    project_id = ProjectId(container.create_project_service().execute_import_project(root_path=_project_root(tmp_path, name)).result["project_id"])
    return container, project_id


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
    archive = tmp_path / "fxserver.zip"
    if not archive.exists():
        with zipfile.ZipFile(archive, "w") as zip_file:
            zip_file.writestr("FXServer.exe", "binary")
            zip_file.writestr("citizen/system.txt", "runtime")
    return archive


def _count(container, model: type) -> int:
    with container.session_factory() as session:
        return len(list(session.execute(select(model)).scalars()))


def _domain_event_types(container) -> list[str]:
    with container.session_factory() as session:
        return [record.event_type for record in session.execute(select(DomainEventRecord)).scalars()]
