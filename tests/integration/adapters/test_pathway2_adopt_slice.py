from __future__ import annotations

from pathlib import Path

from backend.domain.shared_kernel import ProjectId
from backend.infrastructure.di import create_application_container


def test_plan_repo_normalization_redacts_secrets_in_diff(tmp_path: Path) -> None:
    container, project_id, config_path = _fixture(tmp_path)
    service = container.create_adopt_service()
    try:
        preview = service.preview_repo_normalization(project_id=project_id)
        diff = preview.preview["diff"]
        assert "supersecret" not in diff
        assert "cfxk_" not in diff or "CHANGE_ME" in diff
        assert "[REDACTED]" in diff or "CHANGE_ME" in diff
        assert preview.preview["inline_secrets"]
        assert all("[REDACTED]" in item["redacted_preview"] for item in preview.preview["inline_secrets"])
    finally:
        container.close()


def test_apply_normalization_moves_endpoints_and_restores_on_undo(tmp_path: Path) -> None:
    container, project_id, config_path = _fixture(tmp_path)
    service = container.create_adopt_service()
    try:
        prior = config_path.read_text(encoding="utf-8")
        result = service.execute_apply_repo_normalization(project_id=project_id)
        normalized = config_path.read_text(encoding="utf-8")
        overlay_path = config_path.parent / "server.cfg.local"
        gitignore_path = config_path.parent / ".gitignore"

        assert "endpoint_add_udp" not in normalized
        assert "endpoint_add_tcp" not in normalized
        assert 'exec server.cfg.local' in normalized
        assert 'sv_licenseKey "CHANGE_ME"' in normalized
        assert overlay_path.exists()
        assert "endpoint_add_udp" in overlay_path.read_text(encoding="utf-8")
        assert "endpoint_add_tcp" in overlay_path.read_text(encoding="utf-8")
        assert "supersecret" not in overlay_path.read_text(encoding="utf-8")
        assert gitignore_path.exists()
        assert "server.cfg.local" in gitignore_path.read_text(encoding="utf-8")
        assert result.undo_plan is not None

        service.undo(result.undo_plan)
        assert config_path.read_text(encoding="utf-8") == prior
        assert not overlay_path.exists()
    finally:
        container.close()


def test_adopt_repository_sets_pathway2_state_and_scorecard(tmp_path: Path) -> None:
    container = create_application_container(tmp_path / "app-data")
    root = _project_root(tmp_path, "team-server")
    (root / "server.cfg").write_text(_prod_config(), encoding="utf-8")
    try:
        result = container.create_adopt_service().execute_adopt_repository(root_path=root)
        project_id = ProjectId(str(result.result["project_id"]))
        status = container.create_adopt_service().get_adopt_status(project_id)
        assert status["structure_scorecard"]["looks_like_fivem_server"] is True
        assert status["pathway2_state"]["origin"] == "adopted_local"
        assert status["pathway2_state"]["normalized"] is False
        assert status["pathway2_state"]["secrets_substituted"] is False
        assert status["pathway2_state"]["run_ready"] is False
        assert status["run_blocked_reason"]
    finally:
        container.close()


def test_wizard_status_resumes_at_normalize_after_adopt(tmp_path: Path) -> None:
    container = create_application_container(tmp_path / "app-data")
    root = _project_root(tmp_path, "wizard-resume")
    (root / "server.cfg").write_text(_prod_config(), encoding="utf-8")
    try:
        service = container.create_adopt_service()
        result = service.execute_adopt_repository(root_path=root)
        project_id = ProjectId(str(result.result["project_id"]))
        wizard = service.get_wizard_status(project_id)
        assert wizard["wizard"]["active_step"] == "normalize"
        assert wizard["wizard"]["gates"]["adopt"] is True
        assert wizard["wizard"]["gates"]["normalize"] is False
        assert wizard["wizard"]["gates"]["run"] is False
    finally:
        container.close()


def _fixture(tmp_path: Path):
    container = create_application_container(tmp_path / "app-data")
    root = _project_root(tmp_path, "adopt-normalize")
    config_path = root / "server.cfg"
    config_path.write_text(_prod_config(), encoding="utf-8")
    project_id = ProjectId(container.create_project_service().execute_import_project(root_path=root).result["project_id"])
    container.create_config_service().execute_rescan_config_files(project_id=project_id)
    container.create_project_service().update_project_settings(
        project_id=project_id,
        patch={
            "pathway2.origin": "adopted_local",
            "pathway2.normalized": False,
            "pathway2.secrets_substituted": False,
            "pathway2.run_ready": False,
        },
    )
    return container, project_id, config_path


def _project_root(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    (root / "resources" / "demo").mkdir(parents=True)
    (root / "resources" / "demo" / "fxmanifest.lua").write_text("fx_version 'cerulean'\n", encoding="utf-8")
    (root / "txData").mkdir(parents=True)
    return root


def _prod_config() -> str:
    token_part_a = "MTIzNDU2Nzg5MDEyMzQ1Njc4OTAx"
    token_part_b = "Ghpcy5pcy5hLnRlc3QudG9rZW4"
    token_part_c = "c2VjcmV0X3ZhbHVlX2hlcmU"
    return (
        'endpoint_add_udp "0.0.0.0:30120"\n'
        'endpoint_add_tcp "0.0.0.0:30120"\n'
        'sv_licenseKey "cfxk_test_production_key_value_123456"\n'
        'ensure mapmanager\n'
        'ensure chat\n'
        f'set mysql_connection_string "mysql://user:supersecret@{token_part_a}.local/db"\n'
        f'set discord_token "{token_part_a}.{token_part_b}.{token_part_c}"\n'
    )
