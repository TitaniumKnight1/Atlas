from __future__ import annotations

from backend.adapters.config import LocalConfigSecretScanner
from backend.domain.pathway2.commit_safety import (
    StagedFile,
    evaluate_commit_safety,
    is_overlay_path,
    select_default_return_commit_paths,
    server_cfg_eligible_for_return_commit,
)
from backend.domain.git import ChangeStatus
from types import SimpleNamespace


def test_overlay_path_detection() -> None:
    assert is_overlay_path("server.cfg.local")
    assert is_overlay_path("config/server.cfg.local")


def test_evaluate_commit_safety_blocks_overlay() -> None:
    result = evaluate_commit_safety(
        staged_files=[StagedFile(path="server.cfg.local", content='sv_licenseKey "cfxk_secret"')],
        scanner=LocalConfigSecretScanner(),
    )
    assert result.allowed is False
    assert result.findings[0].secret_type == "overlay_contamination"


def test_evaluate_commit_safety_blocks_secret_in_resource() -> None:
    result = evaluate_commit_safety(
        staged_files=[
            StagedFile(
                path="resources/demo/config.lua",
                content='license = "cfxk_test_production_key_value_123456"\n',
            )
        ],
        scanner=LocalConfigSecretScanner(),
    )
    assert result.allowed is False
    assert result.findings[0].secret_type
    assert "cfxk_test" not in result.to_report()["findings"][0]["redacted_preview"]


def test_evaluate_commit_safety_allows_placeholder_server_cfg() -> None:
    result = evaluate_commit_safety(
        staged_files=[StagedFile(path="server.cfg", content='sv_licenseKey "CHANGE_ME"\nexec server.cfg.local\n')],
        scanner=LocalConfigSecretScanner(),
    )
    assert result.allowed is True
    assert result.server_cfg_placeholder_only is True


def test_evaluate_commit_safety_blocks_real_server_cfg_secret() -> None:
    result = evaluate_commit_safety(
        staged_files=[
            StagedFile(
                path="server.cfg",
                content='sv_licenseKey "cfxk_test_production_key_value_123456"\n',
            )
        ],
        scanner=LocalConfigSecretScanner(),
    )
    assert result.allowed is False
    assert result.server_cfg_placeholder_only is False


def test_default_paths_exclude_overlay_and_server_cfg() -> None:
    changes = [
        SimpleNamespace(path="resources/demo/file.lua", change_status=ChangeStatus.MODIFIED),
        SimpleNamespace(path="server.cfg.local", change_status=ChangeStatus.MODIFIED),
        SimpleNamespace(path="server.cfg", change_status=ChangeStatus.MODIFIED),
    ]
    paths = select_default_return_commit_paths(file_changes=changes)
    assert paths == ["resources/demo/file.lua"]


def test_default_paths_include_placeholder_server_cfg_when_requested() -> None:
    changes = [
        SimpleNamespace(path="server.cfg", change_status=ChangeStatus.MODIFIED),
        SimpleNamespace(path=".gitignore", change_status=ChangeStatus.MODIFIED),
        SimpleNamespace(path="server.cfg.local", change_status=ChangeStatus.UNTRACKED),
    ]
    paths = select_default_return_commit_paths(file_changes=changes, include_server_cfg=True)
    assert paths == [".gitignore", "server.cfg"]
    assert "server.cfg.local" not in paths


def test_default_paths_exclude_bulk_untracked_import_tree() -> None:
    changes = [
        SimpleNamespace(path="server.cfg", change_status=ChangeStatus.MODIFIED),
        SimpleNamespace(path=".gitignore", change_status=ChangeStatus.UNTRACKED),
        SimpleNamespace(path="server.cfg.local.example", change_status=ChangeStatus.UNTRACKED),
    ]
    changes.extend(
        SimpleNamespace(path=f"resources/pkg{i}/file.lua", change_status=ChangeStatus.UNTRACKED)
        for i in range(1000)
    )
    paths = select_default_return_commit_paths(
        file_changes=changes,
        include_server_cfg=True,
        normalization_paths={".gitignore", "server.cfg", "server.cfg.local.example"},
    )
    assert len(paths) == 3
    assert paths == [".gitignore", "server.cfg", "server.cfg.local.example"]


def test_server_cfg_eligible_for_return_commit_requires_placeholders(tmp_path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    cfg = root / "server.cfg"
    cfg.write_text('sv_licenseKey "CHANGE_ME"\nexec server.cfg.local\n', encoding="utf-8")
    changes = [SimpleNamespace(path="server.cfg", change_status=ChangeStatus.MODIFIED)]

    def read_text(path: Path) -> str:
        return path.read_text(encoding="utf-8")

    assert server_cfg_eligible_for_return_commit(file_changes=changes, project_root=root, read_text=read_text) is True

    cfg.write_text('sv_licenseKey "cfxk_test_production_key_value_123456"\n', encoding="utf-8")
    assert server_cfg_eligible_for_return_commit(file_changes=changes, project_root=root, read_text=read_text) is False
