from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from backend.adapters.persistence.models import AuditEventRecord, CommandExecutionRecord, CommandPlanRecord, ProjectSettingRecord
from backend.domain.pathway2.substitution import DEV_LICENSE_PLACEHOLDER
from backend.domain.shared_kernel import ProjectId
from backend.infrastructure.di import create_application_container


PROD_LICENSE = "cfxk_test_production_key_value_123456"
PROD_DB_PASSWORD = "supersecret"
PROD_DB_HOST = "prod-db-host.example"
DEV_LICENSE = "cfxk_dev_personal_key_for_local_only"


def test_substitution_zero_escape_and_auto_local_fresh(tmp_path: Path) -> None:
    container, project_id, config_path = _normalized_fixture(tmp_path)
    service = container.create_adopt_service()
    try:
        _assert_no_prod_secret_in_persistence(container, project_id)
        preview = service.preview_secret_substitution(project_id=project_id)
        assert PROD_LICENSE not in json.dumps(preview.preview)

        result = service.execute_apply_secret_substitution(project_id=project_id)
        overlay_path = config_path.parent / "server.cfg.local"
        overlay = overlay_path.read_text(encoding="utf-8")
        base = config_path.read_text(encoding="utf-8")

        assert PROD_LICENSE not in overlay
        assert PROD_DB_PASSWORD not in overlay
        assert PROD_DB_HOST not in overlay
        assert "127.0.0.1" in overlay
        assert "atlas_dev" in overlay
        assert PROD_LICENSE not in base
        assert result.result["run_ready"] is False
        assert DEV_LICENSE_PLACEHOLDER in overlay

        _assert_no_prod_secret_in_persistence(container, project_id)

        service.undo(result.undo_plan)
        assert "CHANGE_ME" in overlay_path.read_text(encoding="utf-8")
    finally:
        container.close()


def test_full_cycle_no_raw_secrets_in_audit_and_normalization_undo(tmp_path: Path) -> None:
    container, project_id, config_path = _imported_fixture(tmp_path)
    service = container.create_adopt_service()
    prior = config_path.read_text(encoding="utf-8")
    try:
        norm_result = service.execute_apply_repo_normalization(project_id=project_id)
        _assert_no_secrets_in_persistence(container, project_id, (PROD_LICENSE, PROD_DB_PASSWORD, PROD_DB_HOST, DEV_LICENSE))

        sub_result = service.execute_apply_secret_substitution(project_id=project_id)
        _assert_no_secrets_in_persistence(container, project_id, (PROD_LICENSE, PROD_DB_PASSWORD, PROD_DB_HOST, DEV_LICENSE))

        service.execute_apply_dev_secret(project_id=project_id, slot_id="sv_licenseKey", dev_value=DEV_LICENSE)
        _assert_no_secrets_in_persistence(container, project_id, (PROD_LICENSE, PROD_DB_PASSWORD, PROD_DB_HOST, DEV_LICENSE))

        service.undo(sub_result.undo_plan)
        _assert_no_secrets_in_persistence(container, project_id, (PROD_LICENSE, PROD_DB_PASSWORD, PROD_DB_HOST, DEV_LICENSE))

        service.undo(norm_result.undo_plan)
        assert config_path.read_text(encoding="utf-8") == prior
        _assert_no_secrets_in_persistence(container, project_id, (PROD_LICENSE, PROD_DB_PASSWORD, PROD_DB_HOST, DEV_LICENSE))
    finally:
        container.close()


def test_run_gate_blocks_until_dev_license_filled(tmp_path: Path) -> None:
    container, project_id, config_path = _normalized_fixture(tmp_path)
    service = container.create_adopt_service()
    setup = container.create_setup_service()
    fxserver = tmp_path / "FXServer.exe"
    fxserver.write_text("stub", encoding="utf-8")
    try:
        service.execute_apply_secret_substitution(project_id=project_id)
        status = service.get_adopt_status(project_id)
        assert status["pathway2_state"]["run_ready"] is False
        assert "DEV_LICENSE_KEY_SET_ME" in status["run_blocked_reason"]

        try:
            setup.preview_start_server(
                project_id=project_id,
                fxserver_path=str(fxserver),
                server_data_path=str(config_path.parent),
            )
        except Exception as error:  # noqa: BLE001
            assert "DEV_LICENSE_KEY_SET_ME" in str(error)
        else:
            raise AssertionError("start should be blocked")

        service.execute_apply_dev_secret(
            project_id=project_id,
            slot_id="sv_licenseKey",
            dev_value="cfxk_dev_personal_key_for_local_only",
        )
        status = service.get_adopt_status(project_id)
        assert status["pathway2_state"]["run_ready"] is True
        assert status["run_blocked_reason"] is None
        setup.preview_start_server(
            project_id=project_id,
            fxserver_path=str(tmp_path / "FXServer.exe"),
            server_data_path=str(config_path.parent),
        )
    finally:
        container.close()


def _imported_fixture(tmp_path: Path):
    container = create_application_container(tmp_path / "app-data")
    root = _project_root(tmp_path)
    config_path = root / "server.cfg"
    config_path.write_text(_prod_config(), encoding="utf-8")
    project_id = ProjectId(container.create_project_service().execute_import_project(root_path=root).result["project_id"])
    container.create_config_service().execute_rescan_config_files(project_id=project_id)
    container.create_project_service().update_project_settings(
        project_id=project_id,
        patch={"pathway2.origin": "adopted_local"},
    )
    return container, project_id, config_path


def _normalized_fixture(tmp_path: Path):
    container, project_id, config_path = _imported_fixture(tmp_path)
    container.create_adopt_service().execute_apply_repo_normalization(project_id=project_id)
    return container, project_id, config_path


def _project_root(tmp_path: Path) -> Path:
    root = tmp_path / "substitution-project"
    (root / "resources" / "demo").mkdir(parents=True)
    (root / "txData").mkdir(parents=True)
    return root


def _prod_config() -> str:
    return (
        'endpoint_add_udp "0.0.0.0:30120"\n'
        'endpoint_add_tcp "0.0.0.0:30120"\n'
        f'sv_licenseKey "{PROD_LICENSE}"\n'
        "ensure mapmanager\n"
        f'set mysql_connection_string "mysql://dbuser:{PROD_DB_PASSWORD}@{PROD_DB_HOST}/game"\n'
    )


def _assert_no_prod_secret_in_persistence(container, project_id: ProjectId) -> None:
    _assert_no_secrets_in_persistence(container, project_id, (PROD_LICENSE, PROD_DB_PASSWORD, PROD_DB_HOST))


def _assert_no_secrets_in_persistence(container, project_id: ProjectId, needles: tuple[str, ...]) -> None:
    with container.session_factory() as session:
        for record in session.execute(select(AuditEventRecord)).scalars():
            blob = json.dumps(record.details_json or {})
            for needle in needles:
                assert needle not in blob
        for record in session.execute(select(CommandExecutionRecord)).scalars():
            blob = json.dumps(record.result_json or {})
            for needle in needles:
                assert needle not in blob
        for record in session.execute(select(CommandPlanRecord)).scalars():
            blob = json.dumps(record.dry_run_plan_json or {})
            for needle in needles:
                assert needle not in blob
        for record in session.execute(select(ProjectSettingRecord).where(ProjectSettingRecord.project_id == str(project_id))).scalars():
            blob = json.dumps(record.value_json)
            for needle in needles:
                assert needle not in blob
