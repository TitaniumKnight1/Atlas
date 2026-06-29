from __future__ import annotations

import os
from pathlib import Path

from backend.adapters.config import LocalConfigSecretScanner
from backend.application.config.structural_validation import enrich_validation_payload, run_structural_validation
from backend.domain.config.remediation_prompts import build_all_issues_prompt, build_fix_prompt
from backend.domain.config.structural import ConfigFindingType
from backend.domain.shared_kernel import ProjectId
from backend.infrastructure.di import create_application_container


PREVAILRP_CFG = """\
endpoint_add_tcp "0.0.0.0:30120"
endpoint_add_udp "0.0.0.0:30120"
set mysql_connection_string "mysql://user:FAKEpass@prod-host/prevail_db?charset=utf8mb4"
sv_licenseKey "cfxk_FAKE1234567890abcdef_abc123"
setr ox:custom_dir "C:/Users/Ryan/projects/PrevailRP/some_custom_dir"
ensure ox_lib
ensure prp-vehicles-1
ensure missing_custom_map_resource
ensure this_resource_is_missing
"""


def _write_prevailrp_fixture(root: Path) -> None:
    resources = root / "resources"
    resources.mkdir(parents=True)
    (resources / "ox_lib").mkdir()
    (resources / "ox_lib" / "fxmanifest.lua").write_text("fx_version 'cerulean'\n", encoding="utf-8")
    vehicles = resources / "prp-vehicles-1"
    vehicles.mkdir()
    (vehicles / "fxmanifest.lua.bak").write_text("fx_version 'cerulean'\n", encoding="utf-8")
    (root / "server.cfg").write_text(PREVAILRP_CFG, encoding="utf-8")


def test_prevailrp_fixture_detects_all_rough_edges(tmp_path: Path) -> None:
    root = tmp_path / "prevailrp"
    root.mkdir()
    _write_prevailrp_fixture(root)
    scanner = LocalConfigSecretScanner()
    result = run_structural_validation(root=root, filesystem=_LocalFs(), secret_scanner=scanner)
    payload = enrich_validation_payload(result, root_path=str(root))
    types = {item["type"] for item in payload["findings"]}
    assert ConfigFindingType.DANGLING_RESOURCE_REFERENCE.value in types
    dangling = [item for item in payload["findings"] if item["type"] == ConfigFindingType.DANGLING_RESOURCE_REFERENCE.value]
    assert len(dangling) == 2
    assert all(item["path"] == "server.cfg" for item in dangling)
    assert any(item["type"] == ConfigFindingType.MISSING_MANIFEST.value for item in payload["findings"])
    assert any(item["type"] == ConfigFindingType.ABSOLUTE_PATH.value for item in payload["findings"])
    secrets = [item for item in payload["findings"] if item["type"] == ConfigFindingType.INLINE_SECRET.value]
    assert len(secrets) == 2
    assert all("FAKEpass" not in item.get("context", {}).get("redacted_preview", "") for item in secrets)
    assert payload["finding_count"] <= 10


def test_nested_resource_subfolders_not_flagged_as_missing_manifest(tmp_path: Path) -> None:
    root = tmp_path / "nested-server"
    root.mkdir()
    resource = root / "resources" / "[jobs]" / "my-job"
    (resource / "data").mkdir(parents=True)
    (resource / "data" / "config.lua").write_text("return {}\n", encoding="utf-8")
    (resource / "fxmanifest.lua").write_text("fx_version 'cerulean'\n", encoding="utf-8")
    (root / "server.cfg").write_text('sv_licenseKey "cfxk_test_placeholder_key_value"\nensure my-job\n', encoding="utf-8")
    result = run_structural_validation(root=root, filesystem=_LocalFs(), secret_scanner=LocalConfigSecretScanner())
    missing = [item for item in result.findings if item.type == ConfigFindingType.MISSING_MANIFEST]
    assert missing == []


def test_exec_fragment_dangling_ensure_not_flagged(tmp_path: Path) -> None:
    root = tmp_path / "exec-server"
    root.mkdir()
    resources = root / "resources"
    resources.mkdir()
    (resources / "ox_lib").mkdir()
    (resources / "ox_lib" / "fxmanifest.lua").write_text("fx_version 'cerulean'\n", encoding="utf-8")
    (root / "fragments").mkdir()
    (root / "fragments" / "extra.cfg").write_text("ensure ghost_resource\n", encoding="utf-8")
    (root / "server.cfg").write_text(
        'sv_licenseKey "cfxk_test_placeholder_key_value"\nexec fragments/extra.cfg\nensure ox_lib\n',
        encoding="utf-8",
    )
    result = run_structural_validation(root=root, filesystem=_LocalFs(), secret_scanner=LocalConfigSecretScanner())
    dangling = [item for item in result.findings if item.type == ConfigFindingType.DANGLING_RESOURCE_REFERENCE]
    assert dangling == []


def test_junctioned_resource_not_flagged_dangling(tmp_path: Path) -> None:
    root = tmp_path / "junction-server"
    root.mkdir()
    resources = root / "resources"
    resources.mkdir()
    target = tmp_path / "linked-target"
    target.mkdir()
    (target / "fxmanifest.lua").write_text("fx_version 'cerulean'\n", encoding="utf-8")
    link = resources / "linked-res"
    if os.name == "nt":
        import subprocess

        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)
    else:
        link.symlink_to(target, target_is_directory=True)
    cfg = root / "server.cfg"
    cfg.write_text('sv_licenseKey "cfxk_test_placeholder_key_value"\nensure linked-res\n', encoding="utf-8")
    result = run_structural_validation(root=root, filesystem=_LocalFs(), secret_scanner=LocalConfigSecretScanner())
    dangling = [item for item in result.findings if item.type == ConfigFindingType.DANGLING_RESOURCE_REFERENCE]
    assert dangling == []


def test_prompt_export_masks_secrets(tmp_path: Path) -> None:
    root = tmp_path / "prompt-server"
    root.mkdir()
    _write_prevailrp_fixture(root)
    result = run_structural_validation(root=root, filesystem=_LocalFs(), secret_scanner=LocalConfigSecretScanner())
    payload = enrich_validation_payload(result, root_path=str(root))
    all_prompt = payload["all_issues_prompt"]
    assert "cfxk_FAKE" not in all_prompt
    assert "FAKEpass" not in all_prompt
    assert "[a secret of type" in all_prompt
    secret_finding = next(item for item in result.findings if item.type == ConfigFindingType.INLINE_SECRET)
    prompt = build_fix_prompt(secret_finding, server_root_hint=str(root))
    assert "cfxk_" not in prompt


def test_import_preview_surfaces_findings(tmp_path: Path) -> None:
    container = create_application_container(tmp_path / "app-data")
    root = tmp_path / "import-preview"
    root.mkdir()
    _write_prevailrp_fixture(root)
    try:
        preview = container.create_project_service().preview_import_project(root)
        validation = preview.preview["config_validation"]
        assert validation["status"] == "validated"
        assert validation["finding_count"] >= 5
        assert preview.warnings
        assert "structural config" in preview.warnings[0].lower()
    finally:
        container.close()


def test_adopt_status_includes_config_validation(tmp_path: Path) -> None:
    container = create_application_container(tmp_path / "app-data")
    root = tmp_path / "adopt-status"
    root.mkdir()
    _write_prevailrp_fixture(root)
    try:
        adopt = container.create_adopt_service().execute_adopt_repository(root_path=root)
        project_id = adopt.result["project_id"]
        status = container.create_adopt_service().get_adopt_status(ProjectId(str(project_id)))
        validation = status["config_validation"]
        assert validation["finding_count"] >= 5
        assert validation["finding_count"] <= 10
        assert any(item["type"] == "MISSING_MANIFEST" for item in validation["findings"])
    finally:
        container.close()


def test_adopt_execute_completes_with_nested_resource_tree(tmp_path: Path) -> None:
    container = create_application_container(tmp_path / "app-data")
    root = tmp_path / "nested-adopt"
    root.mkdir()
    _write_prevailrp_fixture(root)
    resource = root / "resources" / "[jobs]" / "my-job"
    nested = resource / "modules" / "deep" / "child"
    nested.mkdir(parents=True)
    (nested / "logic.lua").write_text("return {}\n", encoding="utf-8")
    (resource / "fxmanifest.lua").write_text("fx_version 'cerulean'\n", encoding="utf-8")
    try:
        adopt = container.create_adopt_service().execute_adopt_repository(root_path=root)
        validation = adopt.result["config_validation"]
        assert validation["finding_count"] <= 12
        assert adopt.result["project_id"]
    finally:
        container.close()


def test_comment_out_dangling_preview_apply_undo(tmp_path: Path) -> None:
    container = create_application_container(tmp_path / "app-data")
    root = tmp_path / "remediation"
    root.mkdir()
    _write_prevailrp_fixture(root)
    try:
        adopt = container.create_adopt_service().execute_adopt_repository(root_path=root)
        project_id = adopt.result["project_id"]
        remediation = container.create_config_remediation_service()
        validation = run_structural_validation(root=root, filesystem=_LocalFs(), secret_scanner=LocalConfigSecretScanner())
        dangling = next(item for item in validation.findings if item.type == ConfigFindingType.DANGLING_RESOURCE_REFERENCE)
        prior = (root / "server.cfg").read_text(encoding="utf-8")
        preview = remediation.preview_comment_out_dangling_ensure(project_id=ProjectId(str(project_id)), finding_id=dangling.finding_id)
        assert "missing_custom_map_resource" in preview.preview.get("diff", "")
        result = remediation.execute_comment_out_dangling_ensure(project_id=ProjectId(str(project_id)), finding_id=dangling.finding_id)
        assert result.undo_plan is not None
        modified = (root / "server.cfg").read_text(encoding="utf-8")
        assert "commented by Atlas" in modified
        container.create_project_service().undo_command_execution(result.command_execution_id)
        assert (root / "server.cfg").read_text(encoding="utf-8") == prior
    finally:
        container.close()


class _LocalFs:
    def read_text(self, path: Path) -> str | None:
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8")
