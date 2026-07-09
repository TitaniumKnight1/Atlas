from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from git import Repo

from backend.domain.shared_kernel import ProjectId
from backend.infrastructure.di import create_application_container

PROD_LICENSE = "cfxk_test_production_key_value_123456"


def _init_git_repo(path: Path, *, remote: str | None = None, branch: str = "main") -> Repo:
    path.mkdir(parents=True, exist_ok=True)
    repo = Repo.init(path)
    if branch and repo.active_branch.name != branch:
        repo.git.checkout("-b", branch)
    (path / "README.md").write_text("fixture\n", encoding="utf-8")
    repo.index.add(["README.md"])
    repo.index.commit("init")
    if remote:
        repo.create_remote("origin", remote)
    return repo


def _junction(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.exists():
        return
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)
    else:
        link.symlink_to(target, target_is_directory=True)


def _build_prevailrp_assembly(root: Path) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    (root / "server.cfg").write_text('sv_licenseKey "CHANGE_ME"\nexec server.cfg.local\n', encoding="utf-8")
    (root / "server.cfg.local").write_text(f'sv_licenseKey "{PROD_LICENSE}"\n', encoding="utf-8")
    (root / ".gitignore").write_text("server.cfg.local\n", encoding="utf-8")

    main = _init_git_repo(root / "PrevailRP-main", remote="https://github.com/Prevail-RP/PrevailRP-main.git")
    clothing = _init_git_repo(
        root / "assets" / "PrevailRP-clothing",
        remote="https://github.com/Prevail-RP/PrevailRP-clothing.git",
    )
    maps = _init_git_repo(
        root / "assets" / "PrevailRP-maps",
        remote="https://github.com/Prevail-RP/PrevailRP-maps.git",
    )
    vehicles_path = root / "assets" / "PrevailRP-vehicles"
    vehicles = _init_git_repo(vehicles_path, remote="https://github.com/Prevail-RP/PrevailRP-vehicles.git")

    resource_target = vehicles_path / "prp-vehicles-1"
    resource_target.mkdir(parents=True)
    (resource_target / "fxmanifest.lua").write_text("fx_version 'cerulean'\n", encoding="utf-8")
    vehicles.index.add(["prp-vehicles-1/fxmanifest.lua"])
    vehicles.index.commit("add vehicles resource")

    maps_resource = root / "assets" / "PrevailRP-maps" / "prp-maps-1"
    maps_resource.mkdir(parents=True)
    (maps_resource / "fxmanifest.lua").write_text("fx_version 'cerulean'\n", encoding="utf-8")
    maps.index.add(["prp-maps-1/fxmanifest.lua"])
    maps.index.commit("add maps resource")

    _junction(root / "resources" / "prp-vehicles-1", resource_target)
    _junction(root / "resources" / "prp-maps-1", maps_resource)

    return {
        "main": Path(main.working_tree_dir),
        "clothing": Path(clothing.working_tree_dir),
        "maps": Path(maps.working_tree_dir),
        "vehicles": Path(vehicles.working_tree_dir),
    }


def _adopt_assembly(tmp_path: Path):
    container = create_application_container(tmp_path / "app-data")
    root = tmp_path / "prevailrp"
    repos = _build_prevailrp_assembly(root)
    project_id = ProjectId(container.create_project_service().execute_import_project(root_path=root).result["project_id"])
    container.create_project_service().update_project_settings(
        project_id=project_id,
        patch={"pathway2.origin": "adopted_local", "pathway2.server_cfg_path": "server.cfg"},
    )
    container.create_git_service().execute_discover_git_repositories(project_id=project_id)
    return container, project_id, root, repos


def _repo_slice_by_suffix(status: dict, suffix: str) -> dict:
    for repo in status["repos"]:
        if repo["repo_path"].replace("\\", "/").endswith(suffix):
            return repo
    raise AssertionError(f"repo ending with {suffix} not found in {status['repos']}")


def test_assembly_return_path_groups_junction_change_to_owning_repo(tmp_path: Path) -> None:
    container, project_id, root, _repos = _adopt_assembly(tmp_path)
    adopt = container.create_adopt_service()
    try:
        # Dev change via junction path — must attribute to vehicles repo baseline.
        (root / "resources" / "prp-vehicles-1" / "client.lua").write_text("print('vehicles change')\n", encoding="utf-8")
        (root / "resources" / "prp-maps-1" / "client.lua").write_text("print('maps change')\n", encoding="utf-8")
        (root / "server.cfg").write_text('sv_licenseKey "CHANGE_ME"\nexec server.cfg.local\n# local tweak\n', encoding="utf-8")

        status = adopt.get_return_path_status(project_id=project_id)
        assert status["structure_kind"] == "assembly_no_root_repo"
        assert status["nothing_to_return"] is False

        vehicles = _repo_slice_by_suffix(status, "assets/PrevailRP-vehicles")
        maps = _repo_slice_by_suffix(status, "assets/PrevailRP-maps")
        assert vehicles["has_changes"] is True
        assert "prp-vehicles-1/client.lua" in vehicles["default_commit_paths"]
        assert vehicles["contamination_report"]["gate_status"] == "PASS"
        assert maps["has_changes"] is True
        assert "prp-maps-1/client.lua" in maps["default_commit_paths"]

        # Unowned parent-level server.cfg stays local — never in any commit set.
        all_paths = [path for repo in status["repos"] for path in repo["default_commit_paths"]]
        assert "server.cfg" not in all_paths
        assert any(item["path"] == "server.cfg" for item in status["unowned_local_paths"])

        # Commit vehicles only — maps remains dirty.
        result = adopt.execute_safe_return_commit(
            project_id=project_id,
            git_repository_id=vehicles["git_repository_id"],
            message="vehicles change",
            paths=list(vehicles["default_commit_paths"]),
        )
        assert result.result["commit_sha"]
        after = adopt.get_return_path_status(project_id=project_id)
        vehicles_after = _repo_slice_by_suffix(after, "assets/PrevailRP-vehicles")
        maps_after = _repo_slice_by_suffix(after, "assets/PrevailRP-maps")
        assert vehicles_after["has_changes"] is False
        assert maps_after["has_changes"] is True
    finally:
        container.close()


def test_assembly_fresh_adoption_nothing_to_return_not_flood(tmp_path: Path) -> None:
    container, project_id, root, _repos = _adopt_assembly(tmp_path)
    adopt = container.create_adopt_service()
    try:
        # Flood of untracked files under parent (no root .git) must not appear as commit paths.
        for index in range(50):
            resource_dir = root / "resources" / f"bulk{index}"
            resource_dir.mkdir(parents=True, exist_ok=True)
            (resource_dir / "fxmanifest.lua").write_text("fx_version 'cerulean'\n", encoding="utf-8")

        status = adopt.get_return_path_status(project_id=project_id)
        assert status["structure_kind"] == "assembly_no_root_repo"
        assert status["nothing_to_return"] is True
        total_paths = sum(len(repo["default_commit_paths"]) for repo in status["repos"])
        assert total_paths == 0
        assert all(not repo["has_changes"] for repo in status["repos"])
        assert any(item["path"] == "server.cfg" for item in status["unowned_local_paths"])
    finally:
        container.close()


def test_assembly_per_repo_gate_blocks_only_contaminated_repo(tmp_path: Path) -> None:
    container, project_id, root, _repos = _adopt_assembly(tmp_path)
    adopt = container.create_adopt_service()
    try:
        (root / "resources" / "prp-vehicles-1" / "secret.cfg").write_text(
            f'sv_licenseKey "{PROD_LICENSE}"\n',
            encoding="utf-8",
        )
        (root / "resources" / "prp-maps-1" / "client.lua").write_text("print('safe')\n", encoding="utf-8")

        status = adopt.get_return_path_status(project_id=project_id)
        vehicles = _repo_slice_by_suffix(status, "assets/PrevailRP-vehicles")
        maps = _repo_slice_by_suffix(status, "assets/PrevailRP-maps")
        assert vehicles["contamination_report"]["gate_status"] == "BLOCKED"
        assert maps["contamination_report"]["gate_status"] == "PASS"
        assert PROD_LICENSE not in json.dumps(status)

        # Maps can still commit while vehicles is blocked.
        result = adopt.execute_safe_return_commit(
            project_id=project_id,
            git_repository_id=maps["git_repository_id"],
            message="safe maps",
            paths=list(maps["default_commit_paths"]),
        )
        assert result.result["commit_sha"]

        with pytest.raises(Exception) as blocked:
            adopt.execute_safe_return_commit(
                project_id=project_id,
                git_repository_id=vehicles["git_repository_id"],
                message="blocked",
                paths=list(vehicles["default_commit_paths"]),
            )
        assert "blocked" in str(blocked.value).lower()
    finally:
        container.close()


def test_single_repo_return_path_unregressed(tmp_path: Path) -> None:
    container = create_application_container(tmp_path / "app-data")
    root = tmp_path / "single"
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
    adopt = container.create_adopt_service()
    try:
        (root / "resources" / "demo" / "client.lua").write_text("print('safe')\n", encoding="utf-8")
        status = adopt.get_return_path_status(project_id=project_id)
        assert status["structure_kind"] == "single_repo"
        assert len(status["repos"]) == 1
        assert status["repos"][0]["has_changes"] is True
        assert "resources/demo/client.lua" in status["default_commit_paths"]
        assert status["contamination_report"]["gate_status"] == "PASS"

        result = adopt.execute_safe_return_commit(
            project_id=project_id,
            git_repository_id=status["git_repository_id"],
            message="safe resource change",
            paths=["resources/demo/client.lua"],
        )
        assert result.result["commit_sha"]
    finally:
        container.close()
