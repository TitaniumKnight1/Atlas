"""Resolve FXServer working directory from the tracked server.cfg layout (read-only)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.domain.config.server_cfg_discovery import find_server_cfg


def resolve_tracked_server_working_directory(project_root: Path) -> tuple[bool, str | None, dict[str, str] | None]:
    """Locate the tracked server.cfg and return its parent as the FXServer cwd.

    Never creates, moves, or mutates tracked files — detection only.
    """
    root = project_root.expanduser().resolve()
    server_cfg = find_server_cfg(root)
    if server_cfg is None:
        return False, "No tracked server.cfg found under this project.", None
    working = server_cfg.parent.resolve()
    if not working.is_dir():
        return False, f"Working directory does not exist: {working}", None
    return True, None, {
        "working_directory": str(working),
        "server_cfg_path": str(server_cfg.resolve()),
        "server_cfg_relative": str(server_cfg.relative_to(root)).replace("\\", "/"),
        "project_root": str(root),
    }


def validate_server_working_directory(path: str) -> tuple[bool, str | None, str | None]:
    """Validate an FXServer working directory: must exist and contain server.cfg."""
    stripped = (path or "").strip()
    if not stripped:
        return False, "Set the folder containing your tracked server.cfg.", None
    try:
        resolved = Path(stripped).expanduser().resolve()
    except OSError as error:
        from backend.domain.setup.fxserver_paths import humanize_launch_error

        return False, humanize_launch_error(error, stripped), None
    if not resolved.exists():
        return (
            False,
            (
                f"Folder not found: {stripped}. "
                "Pick the directory that already contains your tracked server.cfg — Atlas won't invent a server-data folder."
            ),
            None,
        )
    if not resolved.is_dir():
        return False, f"Working folder must be a directory: {stripped}", None
    server_cfg = resolved / "server.cfg"
    if server_cfg.is_file():
        return True, None, str(resolved)
    found = find_server_cfg(resolved)
    if found is None:
        return (
            False,
            (
                f"No server.cfg in {stripped}. "
                "Atlas runs FXServer from the folder containing your tracked server.cfg."
            ),
            None,
        )
    if found.parent.resolve() != resolved.resolve():
        return (
            False,
            f"server.cfg is in {found.parent}. Use that folder as the working directory.",
            None,
        )
    return True, None, str(resolved)


def working_directory_payload(project_root: Path) -> dict[str, Any]:
    valid, message, data = resolve_tracked_server_working_directory(project_root)
    if not valid or data is None:
        raise ValueError(message or "Could not resolve server working directory.")
    return data
