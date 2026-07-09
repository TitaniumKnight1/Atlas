from __future__ import annotations

import os
import subprocess
from pathlib import Path

from backend.domain.shared_kernel import ProjectId
from backend.infrastructure.di import create_application_container


def _init_git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True)
    (path / "README.md").write_text("fixture\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)


def _junction(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.exists():
        return
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)
    else:
        link.symlink_to(target, target_is_directory=True)


def _assembly_fixture(tmp_path: Path):
    container = create_application_container(tmp_path / "app-data")
    root = tmp_path / "prevailrp"
    root.mkdir()
    (root / "server.cfg").write_text('sv_licenseKey "CHANGE_ME"\nexec server.cfg.local\n', encoding="utf-8")
    (root / "server.cfg.local").write_text("sv_licenseKey dev\n", encoding="utf-8")
    (root / ".gitignore").write_text("server.cfg.local\n", encoding="utf-8")

    _init_git_repo(root / "PrevailRP-main")
    vehicles = root / "assets" / "PrevailRP-vehicles"
    _init_git_repo(vehicles)
    resource_target = vehicles / "prp-vehicles-1"
    resource_target.mkdir(parents=True)
    (resource_target / "fxmanifest.lua").write_text("fx_version 'cerulean'\n", encoding="utf-8")
    _junction(root / "resources" / "prp-vehicles-1", resource_target)

    project_id = ProjectId(container.create_project_service().execute_import_project(root_path=root).result["project_id"])
    container.create_project_service().update_project_settings(
        project_id=project_id,
        patch={"pathway2.origin": "adopted_local", "pathway2.server_cfg_path": "server.cfg", "pathway2.normalized": True},
    )
    return container, project_id, root


def test_local_dev_boundary_no_commit_fields(tmp_path: Path) -> None:
    container, project_id, root = _assembly_fixture(tmp_path)
    adopt = container.create_adopt_service()
    try:
        boundary = adopt.get_local_dev_boundary(project_id=project_id)
        wizard = adopt.get_wizard_status(project_id=project_id)

        assert boundary["structure_kind"] == "assembly_no_root_repo"
        assert any(item["path"] == "server.cfg" for item in boundary["unowned_local_paths"])
        assert len(boundary["tracked_repos"]) >= 2
        assert "default_commit_paths" not in boundary
        assert "contamination_report" not in boundary
        assert "repos" not in boundary

        wizard_status = wizard["wizard"]
        assert wizard_status["active_step"] != "return"
        assert "return" not in wizard_status["gates"]
        assert wizard.get("local_dev_boundary") is not None
        assert wizard.get("return_path") is None

        # Flood under parent resources/ must not appear as commit paths — field removed entirely.
        for index in range(20):
            bulk = root / "resources" / f"bulk{index}"
            bulk.mkdir(parents=True, exist_ok=True)
            (bulk / "fxmanifest.lua").write_text("fx_version 'cerulean'\n", encoding="utf-8")
        after = adopt.get_local_dev_boundary(project_id=project_id)
        assert "default_commit_paths" not in after
    finally:
        container.close()


def test_wizard_status_done_after_server_started(tmp_path: Path) -> None:
    container, project_id, _root = _assembly_fixture(tmp_path)
    adopt = container.create_adopt_service()
    try:
        container.create_project_service().update_project_settings(
            project_id=project_id,
            patch={
                "pathway2.secrets_substituted": True,
                "pathway2.run_ready": True,
                "pathway2.dev_transformed": True,
                "pathway2.server_started": True,
            },
        )
        wizard = adopt.get_wizard_status(project_id=project_id)
        assert wizard["wizard"]["active_step"] == "done"
        assert wizard["wizard"]["gates"]["done"] is True
    finally:
        container.close()
