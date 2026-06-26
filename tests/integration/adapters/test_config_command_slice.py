from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select

from backend.adapters.persistence.models import CommandExecutionRecord, TelemetryQueueRecord, TelemetryRejectionRecord
from backend.domain.shared_kernel import ProjectId
from backend.infrastructure.di import create_application_container


def test_preview_and_dry_run_do_not_write_files(tmp_path: Path) -> None:
    container, project_id, config_path, config_file_id = _fixture(tmp_path)
    service = container.create_config_service()
    proposed = _bad_config_with_secret()
    try:
        before = config_path.read_text(encoding="utf-8")
        service.preview_plan_config_change(project_id=project_id, config_file_id=config_file_id, proposed_content=proposed)
        service.dry_run_plan_config_change(project_id=project_id, config_file_id=config_file_id, proposed_content=proposed)
        assert config_path.read_text(encoding="utf-8") == before
    finally:
        container.close()


def test_execute_snapshots_and_undo_restores_prior_content(tmp_path: Path) -> None:
    container, project_id, config_path, config_file_id = _fixture(tmp_path)
    service = container.create_config_service()
    prior = config_path.read_text(encoding="utf-8")
    proposed = prior + '\nset atlas_test "1"\n'
    try:
        result = service.execute_apply_config_change(project_id=project_id, config_file_id=config_file_id, proposed_content=proposed)
        assert 'atlas_test' in config_path.read_text(encoding="utf-8")
        assert result.undo_plan is not None
        service.undo(result.undo_plan)
        assert config_path.read_text(encoding="utf-8") == prior
        assert _count(container, CommandExecutionRecord) >= 2
    finally:
        container.close()


def test_validation_finds_missing_license_key(tmp_path: Path) -> None:
    container, project_id, config_path, config_file_id = _fixture(tmp_path, content='endpoint_add_tcp "0.0.0.0:30120"\n')
    service = container.create_config_service()
    try:
        result = service.execute_run_validation(project_id=project_id, config_file_id=config_file_id)
        assert result["status"] == "fail"
        assert any(item["rule_id"] == "missing_license_key" for item in result["findings"])
    finally:
        container.close()


def test_secret_scan_finds_secrets_without_telemetry_leak(tmp_path: Path) -> None:
    container, project_id, config_path, config_file_id = _fixture(tmp_path, content=_bad_config_with_secret())
    service = container.create_config_service()
    try:
        result = service.execute_run_secret_scan(project_id=project_id, config_file_id=config_file_id)
        assert result["finding_count"] >= 1
        assert all("redacted_preview" in item for item in result["findings"])
        assert all("[REDACTED]" in item["redacted_preview"] for item in result["findings"])
        with container.session_factory() as session:
            assert int(session.scalar(select(func.count()).select_from(TelemetryQueueRecord)) or 0) == 0
            assert int(session.scalar(select(func.count()).select_from(TelemetryRejectionRecord)) or 0) == 0
    finally:
        container.close()


def test_project_isolation_blocks_foreign_config_access(tmp_path: Path) -> None:
    container, first_project_id, _, first_config_id = _fixture(tmp_path, name="alpha")
    second_project_id = ProjectId(container.create_project_service().execute_import_project(root_path=_project_root(tmp_path, "beta")).result["project_id"])
    service = container.create_config_service()
    try:
        try:
            service.get_config_file_view(second_project_id, first_config_id)
        except Exception as error:  # noqa: BLE001
            assert "not found" in str(error).lower()
        else:
            raise AssertionError("cross-project config access was allowed")
    finally:
        container.close()


def _fixture(tmp_path: Path, name: str = "config-project", content: str | None = None):
    container = create_application_container(tmp_path / "app-data")
    root = _project_root(tmp_path, name)
    server_data = root / "server-data"
    server_data.mkdir(parents=True)
    config_path = server_data / "server.cfg"
    config_path.write_text(content or _valid_config(), encoding="utf-8")
    project_id = ProjectId(container.create_project_service().execute_import_project(root_path=root).result["project_id"])
    scan = container.create_config_service().execute_rescan_config_files(project_id=project_id, scan_roots=[str(server_data)])
    config_file_id = scan["files"][0]["config_file_id"] or container.create_config_service().list_config_files(project_id)[0]["config_file_id"]
    return container, project_id, config_path, config_file_id


def _project_root(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    (root / "resources").mkdir(parents=True)
    return root


def _valid_config() -> str:
    return 'endpoint_add_tcp "0.0.0.0:30120"\nendpoint_add_udp "0.0.0.0:30120"\nsv_licenseKey "cfxk_test_placeholder_key_value"\n'


def _bad_config_with_secret() -> str:
    token_part_a = "MTIzNDU2Nzg5MDEyMzQ1Njc4OTAx"
    token_part_b = "Ghpcy5pcy5hLnRlc3QudG9rZW4"
    token_part_c = "c2VjcmV0X3ZhbHVlX2hlcmU"
    return (
        _valid_config()
        + f'set mysql_connection_string "mysql://user:supersecret@{token_part_a}.local/db"\n'
        + f'set discord_token "{token_part_a}.{token_part_b}.{token_part_c}"\n'
    )


def _count(container, model) -> int:
    with container.session_factory() as session:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)
