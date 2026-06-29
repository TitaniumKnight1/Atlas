"""Tests for tracked server.cfg working-directory resolution."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from backend.domain.setup.server_working_dir import (
    resolve_tracked_server_working_directory,
    validate_server_working_directory,
)


def _write_prevailrp_shape(root: Path) -> None:
    resources = root / "resources"
    resources.mkdir(parents=True)
    (resources / "ox_lib").mkdir()
    (resources / "ox_lib" / "fxmanifest.lua").write_text("fx_version 'cerulean'\n", encoding="utf-8")
    (root / "server.cfg").write_text('endpoint_add_tcp "0.0.0.0:30120"\nensure ox_lib\n', encoding="utf-8")


def test_resolve_prevailrp_shape_uses_project_root(tmp_path: Path) -> None:
    root = tmp_path / "prevailrp"
    root.mkdir()
    _write_prevailrp_shape(root)
    assert not (root / "server-data").exists()

    valid, message, data = resolve_tracked_server_working_directory(root)
    assert valid is True
    assert message is None
    assert data is not None
    assert data["working_directory"] == str(root.resolve())
    assert data["server_cfg_relative"] == "server.cfg"


def test_resolve_server_data_layout_when_present(tmp_path: Path) -> None:
    root = tmp_path / "legacy"
    server_data = root / "server-data"
    server_data.mkdir(parents=True)
    (server_data / "server.cfg").write_text("ensure x\n", encoding="utf-8")

    valid, _, data = resolve_tracked_server_working_directory(root)
    assert valid is True
    assert data is not None
    assert data["working_directory"] == str(server_data.resolve())


def test_validate_rejects_invented_server_data_path(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "server.cfg").write_text("ensure x\n", encoding="utf-8")
    guessed = str(root / "server-data")

    valid, message, resolved = validate_server_working_directory(guessed)
    assert valid is False
    assert resolved is None
    assert message is not None
    assert "not found" in message.lower() or "no server.cfg" in message.lower()


def test_resolve_leaves_tracked_git_tree_clean(tmp_path: Path) -> None:
    root = tmp_path / "prevailrp"
    root.mkdir()
    _write_prevailrp_shape(root)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Atlas Test",
        "GIT_AUTHOR_EMAIL": "atlas@test.local",
        "GIT_COMMITTER_NAME": "Atlas Test",
        "GIT_COMMITTER_EMAIL": "atlas@test.local",
    }
    subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "add", "server.cfg", "resources"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True, env=env)

    valid, message, data = resolve_tracked_server_working_directory(root)
    assert valid is True, message
    assert data is not None
    assert data["working_directory"] == str(root.resolve())

    status = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, check=True)
    assert status.stdout.strip() == ""
