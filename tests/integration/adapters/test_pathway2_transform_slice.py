from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import select

from backend.adapters.persistence.models import AuditEventRecord, CommandExecutionRecord
from backend.domain.pathway2.substitution import DEV_LICENSE_PLACEHOLDER
from backend.domain.shared_kernel import ProjectId
from backend.infrastructure.di import create_application_container

DEV_LICENSE = "cfxk_dev_personal_key_for_local_only"
PROD_LICENSE = "cfxk_test_production_key_value_123456"


def test_dev_transform_apply_undo_restores_overlay(tmp_path: Path) -> None:
    container, project_id, config_path = _ready_fixture(tmp_path)
    service = container.create_adopt_service()
    try:
        prior_overlay = (config_path.parent / "server.cfg.local").read_text(encoding="utf-8")
        result = service.execute_apply_dev_config_transform(project_id=project_id)
        overlay_path = config_path.parent / "server.cfg.local"
        transformed = overlay_path.read_text(encoding="utf-8")
        assert "[DEV]" in transformed
        assert "sv_maxclients 8" in transformed
        assert "30121" in transformed
        assert result.result["pathway2_state"]["dev_transformed"] is True

        service.undo(result.undo_plan)
        assert overlay_path.read_text(encoding="utf-8") == prior_overlay
    finally:
        container.close()


def test_prepared_start_preview_masks_plus_set_secret(tmp_path: Path) -> None:
    container, project_id, config_path = _ready_fixture(tmp_path, resist_overlay_license=True)
    service = container.create_adopt_service()
    setup = container.create_setup_service()
    fxserver = tmp_path / "FXServer.exe"
    fxserver.write_text("stub", encoding="utf-8")
    try:
        service.execute_apply_dev_config_transform(project_id=project_id)
        service.execute_apply_dev_secret(project_id=project_id, slot_id="sv_licenseKey", dev_value=DEV_LICENSE)
        preview = setup.preview_start_server(
            project_id=project_id,
            fxserver_path=str(fxserver),
            server_data_path=str(config_path.parent),
        )
        blob = json.dumps(preview.preview)
        assert DEV_LICENSE not in blob
        assert "[REDACTED]" in preview.preview["arguments"]
        assert any(item["key"] == "onesync" for item in preview.preview["plus_set_overrides"])
    finally:
        container.close()


def test_start_server_persists_masked_arguments_not_secret(tmp_path: Path) -> None:
    container, project_id, config_path = _ready_fixture(tmp_path, resist_overlay_license=True)
    service = container.create_adopt_service()
    setup = container.create_setup_service()
    script = tmp_path / "noop.py"
    script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    try:
        service.execute_apply_dev_config_transform(project_id=project_id)
        service.execute_apply_dev_secret(project_id=project_id, slot_id="sv_licenseKey", dev_value=DEV_LICENSE)
        setup.execute_start_server(
            project_id=project_id,
            fxserver_path=str(sys.executable),
            server_data_path=str(config_path.parent),
            extra_args=["-c", str(script)],
        )
        with container.session_factory() as session:
            for record in session.execute(select(AuditEventRecord)).scalars():
                assert DEV_LICENSE not in json.dumps(record.details_json or {})
            for record in session.execute(select(CommandExecutionRecord)).scalars():
                assert DEV_LICENSE not in json.dumps(record.result_json or {})
    finally:
        container.close()


def test_run_gate_still_blocks_without_dev_license(tmp_path: Path) -> None:
    container, project_id, config_path = _ready_fixture(tmp_path)
    service = container.create_adopt_service()
    setup = container.create_setup_service()
    fxserver = tmp_path / "FXServer.exe"
    fxserver.write_text("stub", encoding="utf-8")
    try:
        service.execute_apply_dev_config_transform(project_id=project_id)
        try:
            setup.preview_start_server(
                project_id=project_id,
                fxserver_path=str(fxserver),
                server_data_path=str(config_path.parent),
            )
        except Exception as error:  # noqa: BLE001
            assert DEV_LICENSE_PLACEHOLDER in str(error) or "DEV_LICENSE_KEY_SET_ME" in str(error)
        else:
            raise AssertionError("start should remain blocked until dev license is set")
    finally:
        container.close()


def _ready_fixture(tmp_path: Path, *, resist_overlay_license: bool = False):
    container = create_application_container(tmp_path / "app-data")
    root = tmp_path / "transform-project"
    (root / "resources" / "demo").mkdir(parents=True)
    config_path = root / "server.cfg"
    if resist_overlay_license:
        config_path.write_text(
            'sv_licenseKey GetConvar("sv_licenseKey", "changeme")\n'
            "ensure mapmanager\n"
            'set mysql_connection_string "mysql://dbuser:secret@prod-db-host/game"\n',
            encoding="utf-8",
        )
    else:
        config_path.write_text(
            f'sv_licenseKey "{PROD_LICENSE}"\n'
            "ensure mapmanager\n"
            'set mysql_connection_string "mysql://dbuser:secret@prod-db-host/game"\n',
            encoding="utf-8",
        )
    project_id = ProjectId(container.create_project_service().execute_import_project(root_path=root).result["project_id"])
    container.create_config_service().execute_rescan_config_files(project_id=project_id)
    container.create_project_service().update_project_settings(project_id=project_id, patch={"pathway2.origin": "adopted_local"})
    adopt = container.create_adopt_service()
    adopt.execute_apply_repo_normalization(project_id=project_id)
    adopt.execute_apply_secret_substitution(project_id=project_id)
    if resist_overlay_license:
        _restore_getconvar_license_base(config_path)
    return container, project_id, config_path


def _restore_getconvar_license_base(config_path: Path) -> None:
    lines: list[str] = []
    for line in config_path.read_text(encoding="utf-8").splitlines():
        if line.strip().lower().startswith("sv_licensekey"):
            lines.append('sv_licenseKey GetConvar("sv_licenseKey", "changeme")')
            continue
        lines.append(line)
    config_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
