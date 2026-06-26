from __future__ import annotations

from typing import Any

from backend.domain.backup.types import ConsistencyGuarantee


RUNNING_SERVER_WARNING = (
    "Server process is running; files and databases may change during capture. "
    "Stop the server for a crash-consistent backup."
)


def assess_backup_consistency(*, server_running: bool) -> dict[str, Any]:
    if server_running:
        return {
            "guarantee": ConsistencyGuarantee.BEST_EFFORT.value,
            "server_running": True,
            "warning": RUNNING_SERVER_WARNING,
        }
    return {
        "guarantee": ConsistencyGuarantee.QUIESCED.value,
        "server_running": False,
        "warning": None,
    }
