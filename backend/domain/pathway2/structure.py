from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.domain.pathway2.normalization import EXEC_TRAILER, OVERLAY_FILENAME, find_server_cfg


def build_structure_scorecard(
    *,
    root: Path,
    server_cfg_content: str | None = None,
    git_remote_redacted: str | None = None,
    resource_count: int | None = None,
) -> dict[str, Any]:
    resolved = root.expanduser().resolve()
    server_cfg = find_server_cfg(resolved)
    overlay_path = server_cfg.parent / OVERLAY_FILENAME if server_cfg else resolved / OVERLAY_FILENAME
    checks = {
        "server_cfg": _check(server_cfg is not None and server_cfg.exists()),
        "resources_dir": _check((resolved / "resources").is_dir()),
        "txdata_dir": _check((resolved / "txData").is_dir()),
        "artifacts_dir": _check((resolved / "artifacts").is_dir() or _find_artifact_hint(resolved)),
        "logs_dir": _check((resolved / "logs").is_dir()),
        "git_remote": _check(git_remote_redacted is not None),
        "overlay_file": _check(overlay_path.exists()),
        "exec_trailer": _check(_has_exec_trailer(server_cfg_content)),
    }
    present = sum(1 for item in checks.values() if item["present"])
    total = len(checks)
    confidence = "high" if checks["server_cfg"]["present"] and checks["resources_dir"]["present"] else "low"
    if checks["server_cfg"]["present"] and (checks["resources_dir"]["present"] or checks["txdata_dir"]["present"]):
        confidence = "high"
    elif checks["server_cfg"]["present"]:
        confidence = "medium"
    return {
        "looks_like_fivem_server": checks["server_cfg"]["present"] and (checks["resources_dir"]["present"] or checks["txdata_dir"]["present"]),
        "confidence": confidence,
        "score": f"{present}/{total}",
        "checks": checks,
        "server_cfg_path": str(server_cfg.relative_to(resolved)).replace("\\", "/") if server_cfg else None,
        "overlay_path": str(overlay_path.relative_to(resolved)).replace("\\", "/") if overlay_path.exists() else OVERLAY_FILENAME,
        "git_remote_redacted": git_remote_redacted,
        "resource_count": resource_count,
    }


def _check(present: bool) -> dict[str, bool]:
    return {"present": present}


def _has_exec_trailer(content: str | None) -> bool:
    if not content:
        return False
    return any(line.strip() == EXEC_TRAILER for line in content.splitlines())


def _find_artifact_hint(root: Path) -> bool:
    for name in ("FXServer.exe", "run.cmd", "run.sh"):
        if next(root.rglob(name), None) is not None:
            return True
    return False
