"""FXServer.exe discovery and launch-path validation (Windows-focused)."""

from __future__ import annotations

import os
from pathlib import Path

FXSERVER_EXE = "FXServer.exe"
FIVEM_ARTIFACTS_URL = "https://runtime.fivem.net/artifacts/fivem/build_server_windows/master/"


def fxserver_candidate_roots(project_root: Path | None = None) -> list[Path]:
    home = Path.home()
    roots = [
        Path("C:/FXServer"),
        Path("C:/FXServer/server"),
        Path("C:/FiveM"),
        Path("C:/FiveM/artifact"),
        home / "Desktop" / "FXServer",
        home / "FXServer",
    ]
    if project_root is not None:
        resolved = project_root.expanduser().resolve()
        roots.extend(
            [
                resolved,
                resolved.parent / "FXServer",
                resolved.parent / "artifact",
                resolved / "artifact",
                resolved.parent / "server",
            ]
        )
    return roots


def _is_valid_fxserver(path: Path) -> bool:
    try:
        return path.is_file() and path.name.lower() == FXSERVER_EXE.lower()
    except OSError:
        return False


def detect_fxserver_executable(*, project_root: Path | None = None) -> str | None:
    seen: set[Path] = set()
    for root in fxserver_candidate_roots(project_root):
        candidates = [root / FXSERVER_EXE, root / "server" / FXSERVER_EXE]
        for candidate in candidates:
            try:
                resolved = candidate.expanduser().resolve()
            except OSError:
                continue
            if resolved in seen:
                continue
            seen.add(resolved)
            if _is_valid_fxserver(resolved):
                return str(resolved)
    return None


def validate_fxserver_path(path: str) -> tuple[bool, str | None, str | None]:
    stripped = (path or "").strip()
    if not stripped:
        return False, "Set your FXServer executable first.", None
    try:
        resolved = Path(stripped).expanduser().resolve()
    except OSError as error:
        return False, humanize_launch_error(error, stripped), None
    if not resolved.exists():
        return False, f"FXServer.exe not found at {stripped}", None
    if resolved.name.lower() != FXSERVER_EXE.lower():
        return False, f"Select FXServer.exe — this file is named {resolved.name}", None
    if not resolved.is_file():
        return False, f"FXServer.exe not found at {stripped}", None
    return True, None, str(resolved)


def humanize_launch_error(error: BaseException, fxserver_path: str = "") -> str:
    message = str(error).strip()
    lowered = message.lower()
    winerror = getattr(error, "winerror", None)
    errno = getattr(error, "errno", None)

    if isinstance(error, FileNotFoundError) or "cannot find the file" in lowered or errno == 2:
        if fxserver_path.strip():
            return f"FXServer.exe not found at {fxserver_path.strip()}"
        return "Set your FXServer executable first."

    if winerror == 5 or errno == 13 or "permission denied" in lowered or "access is denied" in lowered:
        return (
            "Atlas couldn't run FXServer (permission denied) — try running as administrator "
            "or check the file isn't blocked by Windows."
        )

    if "not a valid win32 application" in lowered:
        return "That file is not a valid Windows executable. Point Atlas at FXServer.exe from the FiveM server artifact."

    if fxserver_path.strip() and fxserver_path.strip() in message:
        return message

    if message:
        return message

    return "Atlas couldn't start FXServer. Check the executable path and try again."


def validate_server_data_path(path: str) -> tuple[bool, str | None, str | None]:
    stripped = (path or "").strip()
    if not stripped:
        return False, "Set your server-data folder first.", None
    try:
        resolved = Path(stripped).expanduser().resolve()
    except OSError as error:
        return False, humanize_launch_error(error, stripped), None
    if resolved.exists() and not resolved.is_dir():
        return False, f"Server-data path must be a folder: {stripped}", None
    return True, None, str(resolved)
