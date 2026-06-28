from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.domain.pathway2.normalization import OVERLAY_FILENAME, find_server_cfg
from backend.domain.pathway2.settings import Pathway2SettingKeys
from backend.domain.pathway2.substitution import compute_run_gate


def evaluate_pathway2_run_readiness(
    *,
    settings: dict[str, Any],
    overlay_content: str | None,
) -> tuple[bool, str | None]:
    if not settings.get(Pathway2SettingKeys.NORMALIZED):
        return False, "Complete adopt normalization (P2-1) before running the server."
    if not settings.get(Pathway2SettingKeys.SECRETS_SUBSTITUTED):
        return False, "Complete P2-2 secret substitution before running the server."
    if overlay_content is None:
        return False, f"Missing gitignored overlay file ({OVERLAY_FILENAME})."
    ready, unset = compute_run_gate(overlay_content)
    if not ready:
        return False, f"Set dev values for: {', '.join(unset)}"
    return True, None


def load_overlay_content(filesystem: Any, project_root: Path) -> str | None:
    server_cfg = find_server_cfg(project_root)
    if server_cfg is None:
        return None
    overlay_path = server_cfg.parent / OVERLAY_FILENAME
    if not overlay_path.is_file():
        return None
    return filesystem.read_text(overlay_path)
