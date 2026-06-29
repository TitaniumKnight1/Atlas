from __future__ import annotations

import json
from pathlib import Path

from git import Repo

from backend.domain.shared_kernel import ProjectId
from backend.infrastructure.di import create_application_container

PROD_LICENSE = "cfxk_test_production_key_value_123456"


def test_safe_return_commit_blocks_staged_secret(tmp_path: Path) -> None:
    container, project_id, repo_id, root = _pathway2_git_fixture(tmp_path)
    adopt = container.create_adopt_service()
    try:
        (root / "resources" / "demo" / "secret.cfg").write_text(f'sv_licenseKey "{PROD_LICENSE}"\n', encoding="utf-8")
        preview = adopt.preview_safe_return_commit(
            project_id=project_id,
            git_repository_id=repo_id,
            message="blocked secret",
            paths=["resources/demo/secret.cfg"],
        )
        assert preview.preview["contamination_report"]["gate_status"] == "BLOCKED"
        assert PROD_LICENSE not in json.dumps(preview.preview)
        try:
            adopt.execute_safe_return_commit(
                project_id=project_id,
                git_repository_id=repo_id,
                message="blocked secret",
                paths=["resources/demo/secret.cfg"],
            )
        except Exception as error:  # noqa: BLE001
            assert "blocked" in str(error).lower()
        else:
            raise AssertionError("commit should be blocked")
    finally:
        container.close()


def test_safe_return_commit_blocks_real_server_cfg(tmp_path: Path) -> None:
    container, project_id, repo_id, root = _pathway2_git_fixture(tmp_path)
    adopt = container.create_adopt_service()
    try:
        (root / "server.cfg").write_text(f'sv_licenseKey "{PROD_LICENSE}"\nexec server.cfg.local\n', encoding="utf-8")
        preview = adopt.preview_safe_return_commit(
            project_id=project_id,
            git_repository_id=repo_id,
            message="blocked base",
            paths=["server.cfg"],
        )
        assert preview.preview["contamination_report"]["gate_status"] == "BLOCKED"
        assert PROD_LICENSE not in json.dumps(preview.preview)
    finally:
        container.close()


def test_return_path_includes_placeholder_server_cfg_after_normalization(tmp_path: Path) -> None:
    container, project_id, repo_id, root = _pathway2_git_fixture(tmp_path)
    adopt = container.create_adopt_service()
    try:
        adopt.execute_apply_repo_normalization(project_id=project_id)
        status = adopt.get_return_path_status(project_id=project_id, git_repository_id=repo_id)
        paths = status["default_commit_paths"]
        assert "server.cfg.local" not in paths
        assert "server.cfg" in paths
        assert status["gitignore_contains_overlay"] is True
        assert status["contamination_report"]["gate_status"] == "PASS"
        assert status["contamination_report"]["server_cfg_placeholder_only"] is True
        assert PROD_LICENSE not in (root / "server.cfg").read_text(encoding="utf-8")
        assert (root / "server.cfg.local").exists()
        assert PROD_LICENSE not in (root / "server.cfg.local").read_text(encoding="utf-8")
    finally:
        container.close()


def test_safe_return_commit_excludes_overlay_and_commits_safe_resource(tmp_path: Path) -> None:
    container, project_id, repo_id, root = _pathway2_git_fixture(tmp_path)
    adopt = container.create_adopt_service()
    git = container.create_git_service()
    try:
        (root / "resources" / "demo" / "client.lua").write_text("print('safe change')\n", encoding="utf-8")
        status = adopt.get_return_path_status(project_id=project_id, git_repository_id=repo_id)
        assert "server.cfg.local" not in status["default_commit_paths"]
        assert status["gitignore_contains_overlay"] is True
        assert status["contamination_report"]["gate_status"] == "PASS"

        result = adopt.execute_safe_return_commit(
            project_id=project_id,
            git_repository_id=repo_id,
            message="safe resource change",
            paths=["resources/demo/client.lua"],
        )
        assert result.result["commit_sha"]
        worktree = git.get_worktree_status(project_id, repo_id)
        assert worktree["is_dirty"] is False
        overlay = (root / "server.cfg.local").read_text(encoding="utf-8")
        assert PROD_LICENSE in overlay or "cfxk_" in overlay
        assert PROD_LICENSE not in (root / "server.cfg").read_text(encoding="utf-8")
    finally:
        container.close()


def _pathway2_git_fixture(tmp_path: Path):
    container = create_application_container(tmp_path / "app-data")
    root = tmp_path / "return-path-project"
    (root / "resources" / "demo").mkdir(parents=True)
    Repo.init(root)
    (root / ".gitignore").write_text("server.cfg.local\n", encoding="utf-8")
    (root / "server.cfg").write_text('sv_licenseKey "CHANGE_ME"\nexec server.cfg.local\n', encoding="utf-8")
    (root / "server.cfg.local").write_text(f'sv_licenseKey "{PROD_LICENSE}"\n', encoding="utf-8")
    (root / "resources" / "demo" / "fxmanifest.lua").write_text("fx_version 'cerulean'\n", encoding="utf-8")
    repo = Repo(root)
    repo.index.add([".gitignore", "server.cfg", "resources/demo/fxmanifest.lua"])
    repo.index.commit("initial")
    project_id = ProjectId(container.create_project_service().execute_import_project(root_path=root).result["project_id"])
    container.create_project_service().update_project_settings(project_id=project_id, patch={"pathway2.origin": "adopted_local"})
    container.create_git_service().execute_discover_git_repositories(project_id=project_id)
    repos = container.create_git_service().list_git_repositories(project_id)
    repo_id = repos[0]["git_repository_id"]
    return container, project_id, repo_id, root
