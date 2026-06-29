"""Unit tests for FXServer discovery and validation."""

from pathlib import Path

import pytest

from backend.domain.setup.fxserver_paths import (
    detect_fxserver_executable,
    humanize_launch_error,
    validate_fxserver_path,
)


def test_validate_fxserver_path_rejects_empty() -> None:
    valid, message, resolved = validate_fxserver_path("")
    assert valid is False
    assert message == "Set your FXServer executable first."
    assert resolved is None


def test_validate_fxserver_path_rejects_missing(tmp_path: Path) -> None:
    missing = tmp_path / "FXServer.exe"
    valid, message, resolved = validate_fxserver_path(str(missing))
    assert valid is False
    assert "not found" in (message or "").lower()
    assert resolved is None


def test_validate_fxserver_path_accepts_executable(tmp_path: Path) -> None:
    executable = tmp_path / "FXServer.exe"
    executable.write_text("stub", encoding="utf-8")
    valid, message, resolved = validate_fxserver_path(str(executable))
    assert valid is True
    assert message is None
    assert resolved == str(executable.resolve())


def test_validate_fxserver_path_rejects_wrong_name(tmp_path: Path) -> None:
    wrong = tmp_path / "server.exe"
    wrong.write_text("stub", encoding="utf-8")
    valid, message, _ = validate_fxserver_path(str(wrong))
    assert valid is False
    assert "FXServer.exe" in (message or "")


def test_detect_fxserver_finds_common_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install = tmp_path / "FXServer"
    install.mkdir()
    executable = install / "FXServer.exe"
    executable.write_text("stub", encoding="utf-8")
    monkeypatch.setattr("backend.domain.setup.fxserver_paths.fxserver_candidate_roots", lambda project_root=None: [install])
    assert detect_fxserver_executable() == str(executable.resolve())


def test_humanize_launch_error_maps_permission_denied() -> None:
    error = OSError("[WinError 5] Access is denied")
    error.winerror = 5  # type: ignore[attr-defined]
    message = humanize_launch_error(error, r"C:\FXServer\FXServer.exe")
    assert "permission denied" in message.lower()


def test_humanize_launch_error_maps_invalid_directory() -> None:
    error = OSError("[WinError 267] The directory name is invalid")
    error.winerror = 267  # type: ignore[attr-defined]
    message = humanize_launch_error(error)
    assert "working folder" in message.lower() or "server.cfg" in message.lower()
