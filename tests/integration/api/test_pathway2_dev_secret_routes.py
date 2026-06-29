"""HTTP integration: dev-license overlay-write command routes (preview/dry-run/apply/undo)."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.adapters.persistence.models import AuditEventRecord, CommandExecutionRecord, CommandPlanRecord
from backend.atlas_backend.app import create_app
from backend.domain.pathway2.substitution import DEV_LICENSE_PLACEHOLDER
from backend.domain.shared_kernel import ProjectId
from backend.infrastructure.di import create_application_container

VERIFY_KEY = "cfxk_TESTKEY_VERIFY123"
PROD_LICENSE = "cfxk_test_production_key_value_123456"
PROD_DB_PASSWORD = "supersecret"
PROD_DB_HOST = "prod-db-host.example"


def test_dev_secret_http_routes_preview_masks_apply_undo(tmp_path: Path) -> None:
    app_data = tmp_path / "app-data"
    project_id, config_path = _seed_substituted_project(app_data)
    overlay_path = config_path.parent / "server.cfg.local"
    base = f"/api/v1/projects/{project_id}/pathway2"
    body = {"slot_id": "sv_licenseKey", "dev_value": VERIFY_KEY}

    with TestClient(create_app(app_data)) as client:
        plan = client.post(f"{base}/dev-secret-plan", json=body)
        assert plan.status_code == 200, plan.text
        plan_json = plan.json()
        assert plan_json["ok"] is True
        assert VERIFY_KEY not in json.dumps(plan_json["data"]["preview"])
        assert "REDACTED" in json.dumps(plan_json)

        dry_run = client.post(f"{base}/dev-secret-dry-run", json=body)
        assert dry_run.status_code == 200, dry_run.text
        dry_json = dry_run.json()
        assert dry_json["ok"] is True
        assert dry_json["data"]["valid"] is True
        assert VERIFY_KEY not in json.dumps(dry_json["data"])

        apply = client.post(f"{base}/dev-secret/apply", json=body)
        assert apply.status_code == 200, apply.text
        apply_json = apply.json()
        assert apply_json["ok"] is True
        assert VERIFY_KEY not in json.dumps(apply_json["data"])
        assert apply_json["data"]["run_ready"] is True

        overlay = overlay_path.read_text(encoding="utf-8")
        base_cfg = config_path.read_text(encoding="utf-8")
        assert VERIFY_KEY in overlay
        assert VERIFY_KEY not in base_cfg
        assert DEV_LICENSE_PLACEHOLDER not in overlay

        command_execution_id = apply_json["data"]["command_execution_id"]
        undo = client.post(f"{base}/undo", json={"command_execution_id": command_execution_id})
        assert undo.status_code == 200, undo.text
        assert undo.json()["ok"] is True
        assert DEV_LICENSE_PLACEHOLDER in overlay_path.read_text(encoding="utf-8")
        assert VERIFY_KEY not in overlay_path.read_text(encoding="utf-8")

        wizard = client.get(f"{base}/wizard-status")
        assert wizard.json()["data"]["pathway2_state"]["run_ready"] is False

    _assert_no_raw_key_in_persistence(app_data, VERIFY_KEY)


def test_dev_secret_dry_run_route_registered(tmp_path: Path) -> None:
    """Missing sidecar routes return 404; registered routes reach handlers (non-404)."""
    with TestClient(create_app(tmp_path / "app-data"), raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/projects/missing/pathway2/dev-secret-dry-run",
            json={"slot_id": "sv_licenseKey", "dev_value": VERIFY_KEY},
        )
        assert response.status_code != 404


def _seed_substituted_project(app_data: Path) -> tuple[str, Path]:
    container = create_application_container(app_data)
    root = app_data.parent / "dev-secret-http-project"
    (root / "resources" / "demo").mkdir(parents=True)
    (root / "txData").mkdir(parents=True)
    config_path = root / "server.cfg"
    config_path.write_text(_prod_config(), encoding="utf-8")
    try:
        project_id = ProjectId(
            container.create_project_service().execute_import_project(root_path=root).result["project_id"]
        )
        container.create_config_service().execute_rescan_config_files(project_id=project_id)
        container.create_project_service().update_project_settings(
            project_id=project_id,
            patch={"pathway2.origin": "adopted_local"},
        )
        adopt = container.create_adopt_service()
        adopt.execute_apply_repo_normalization(project_id=project_id)
        adopt.execute_apply_secret_substitution(project_id=project_id)
        return str(project_id), config_path
    finally:
        container.close()


def _prod_config() -> str:
    return (
        'endpoint_add_udp "0.0.0.0:30120"\n'
        'endpoint_add_tcp "0.0.0.0:30120"\n'
        f'sv_licenseKey "{PROD_LICENSE}"\n'
        "ensure mapmanager\n"
        f'set mysql_connection_string "mysql://dbuser:{PROD_DB_PASSWORD}@{PROD_DB_HOST}/game"\n'
    )


def _assert_no_raw_key_in_persistence(app_data: Path, needle: str) -> None:
    container = create_application_container(app_data)
    try:
        with container.session_factory() as session:
            for record in session.execute(select(AuditEventRecord)).scalars():
                assert needle not in json.dumps(record.details_json or {})
            for record in session.execute(select(CommandExecutionRecord)).scalars():
                assert needle not in json.dumps(record.result_json or {})
            for record in session.execute(select(CommandPlanRecord)).scalars():
                assert needle not in json.dumps(record.dry_run_plan_json or {})
    finally:
        container.close()
