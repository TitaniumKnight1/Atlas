from __future__ import annotations

import os
import subprocess
from pathlib import Path

from backend.domain.pathway2.local_boundary import build_local_dev_boundary


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


def test_assembly_boundary_marks_parent_files_local(tmp_path: Path) -> None:
    root = tmp_path / "prevailrp"
    root.mkdir()
    (root / "server.cfg").write_text("endpoint_add_tcp\n", encoding="utf-8")
    (root / "server.cfg.local").write_text("sv_licenseKey secret\n", encoding="utf-8")

    _init_git_repo(root / "PrevailRP-main")
    vehicles = root / "assets" / "PrevailRP-vehicles"
    _init_git_repo(vehicles)
    resource_target = vehicles / "prp-vehicles-1"
    resource_target.mkdir(parents=True)
    _junction(root / "resources" / "prp-vehicles-1", resource_target)

    boundary = build_local_dev_boundary(
        project_root=root,
        server_cfg_rel="server.cfg",
        normalized=True,
        overlay_gitignored=True,
    )

    assert boundary["structure_kind"] == "assembly_no_root_repo"
    assert any(item["path"] == "server.cfg" for item in boundary["unowned_local_paths"])
    assert any(item["path"] == "server.cfg.local" for item in boundary["unowned_local_paths"])
    assert len(boundary["tracked_repos"]) == 2
    assert "does not commit" in boundary["git_handoff_message"].lower()
    assert "default_commit_paths" not in boundary


def test_single_repo_boundary_lists_tracked_repo(tmp_path: Path) -> None:
    root = tmp_path / "single"
    _init_git_repo(root)
    (root / "server.cfg").write_text('sv_licenseKey "CHANGE_ME"\nexec server.cfg.local\n', encoding="utf-8")
    (root / ".gitignore").write_text("server.cfg.local\n", encoding="utf-8")

    boundary = build_local_dev_boundary(
        project_root=root,
        server_cfg_rel="server.cfg",
        normalized=True,
        overlay_gitignored=True,
    )

    assert boundary["structure_kind"] == "single_repo"
    assert len(boundary["tracked_repos"]) == 1
    assert boundary["tracked_repos"][0]["repo_path"] == "."
    assert boundary["normalization_note"] is not None
    assert "your own git tools" in boundary["normalization_note"]
