from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from backend.domain.project.topology import (
    StructureKind,
    discover_project_repo_topology,
    resolve_path_owning_repo,
    resolve_path_owner_detail,
)


def _init_git_repo(path: Path, *, remote: str | None = None, branch: str = "main") -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", branch], cwd=path, check=True, capture_output=True)
    (path / "README.md").write_text("fixture\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)
    if remote:
        subprocess.run(["git", "remote", "add", "origin", remote], cwd=path, check=True, capture_output=True)


def _junction(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.exists():
        return
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)
    else:
        link.symlink_to(target, target_is_directory=True)


def _build_prevailrp_shape(root: Path) -> Path:
    (root / "server.cfg").write_text("endpoint_add_tcp\n", encoding="utf-8")
    (root / "server.cfg.local").write_text("sv_licenseKey secret\n", encoding="utf-8")

    _init_git_repo(
        root / "PrevailRP-main",
        remote="https://github.com/Prevail-RP/PrevailRP-main.git",
    )
    assets = root / "assets"
    _init_git_repo(
        assets / "PrevailRP-clothing",
        remote="https://github.com/Prevail-RP/PrevailRP-clothing.git",
    )
    _init_git_repo(
        assets / "PrevailRP-maps",
        remote="https://github.com/Prevail-RP/PrevailRP-maps.git",
    )
    vehicles = assets / "PrevailRP-vehicles"
    _init_git_repo(
        vehicles,
        remote="https://github.com/Prevail-RP/PrevailRP-vehicles.git",
    )

    resource_target = vehicles / "prp-vehicles-1"
    resource_target.mkdir(parents=True)
    (resource_target / "fxmanifest.lua").write_text("fx_version 'cerulean'\n", encoding="utf-8")
    _junction(root / "resources" / "prp-vehicles-1", resource_target)
    return resource_target / "fxmanifest.lua"


def test_plain_no_repo_folder(tmp_path: Path) -> None:
    root = tmp_path / "plain"
    root.mkdir()
    (root / "server.cfg").write_text("test\n", encoding="utf-8")

    topology = discover_project_repo_topology(root)

    assert topology.structure_kind == StructureKind.PLAIN_NO_REPO
    assert topology.root_is_repo is False
    assert topology.repos == ()
    assert str(root / "server.cfg") in topology.unowned_paths


def test_single_repo_at_root(tmp_path: Path) -> None:
    root = tmp_path / "single"
    _init_git_repo(root, remote="https://github.com/example/single.git")

    topology = discover_project_repo_topology(root)

    assert topology.structure_kind == StructureKind.SINGLE_REPO
    assert topology.root_is_repo is True
    assert len(topology.repos) == 1
    assert topology.repos[0].kind.value == "root"
    assert topology.repos[0].branch == "main"
    assert topology.repos[0].remote_redacted == "https://github.com/example/single.git"


def test_prevailrp_shape_assembly_without_root_repo(tmp_path: Path) -> None:
    root = tmp_path / "prevailrp"
    root.mkdir()
    junctioned_manifest = _build_prevailrp_shape(root)

    topology = discover_project_repo_topology(root)

    assert topology.root_is_repo is False
    assert topology.structure_kind == StructureKind.ASSEMBLY_NO_ROOT_REPO
    repo_paths = {repo.path for repo in topology.repos}
    assert repo_paths == {
        str(root / "PrevailRP-main"),
        str(root / "assets" / "PrevailRP-clothing"),
        str(root / "assets" / "PrevailRP-maps"),
        str(root / "assets" / "PrevailRP-vehicles"),
    }
    assert str(root / "server.cfg") in topology.unowned_paths
    assert str(root / "server.cfg.local") in topology.unowned_paths
    assert all(repo.remote_redacted and "github.com" in repo.remote_redacted for repo in topology.repos)

    owner = resolve_path_owning_repo(root, junctioned_manifest, topology)
    assert owner == str(root / "assets" / "PrevailRP-vehicles")
    detail = resolve_path_owner_detail(root, root / "resources" / "prp-vehicles-1" / "fxmanifest.lua", topology)
    assert detail["owner"] == str(root / "assets" / "PrevailRP-vehicles")
    assert detail["owner_kind"] == "nested"


def test_linked_repo_discovered_via_junction(tmp_path: Path) -> None:
    root = tmp_path / "assembly"
    root.mkdir()
    (root / "server.cfg").write_text("test\n", encoding="utf-8")

    external = tmp_path / "external-repo"
    _init_git_repo(external, remote="https://github.com/example/external.git")

    _junction(root / "resources" / "linked-repo", external)

    topology = discover_project_repo_topology(root)

    assert topology.structure_kind == StructureKind.MULTI_REPO_LINKED
    assert len(topology.repos) == 1
    assert topology.repos[0].kind.value == "linked_in"
    assert topology.repos[0].is_junction is True
    assert topology.repos[0].real_target == str(external.resolve())


def test_remote_redaction_masks_credentials(tmp_path: Path) -> None:
    root = tmp_path / "cred-repo"
    _init_git_repo(root, remote="https://user:secret@github.com/org/private.git")

    topology = discover_project_repo_topology(root)

    assert topology.repos[0].remote_redacted == "https://[REDACTED]@github.com/org/private.git"


def test_path_owner_returns_none_for_parent_level_file(tmp_path: Path) -> None:
    root = tmp_path / "assembly"
    root.mkdir()
    _build_prevailrp_shape(root)

    topology = discover_project_repo_topology(root)
    assert resolve_path_owning_repo(root, root / "server.cfg", topology) is None
