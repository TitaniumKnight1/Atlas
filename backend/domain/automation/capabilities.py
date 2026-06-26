from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CapabilityStatus:
    capability_id: str
    available: bool
    reason: str | None = None


def inventory_capabilities() -> dict[str, CapabilityStatus]:
    """M8b capability map — recipes invoke only what exists."""
    return {
        "process_restart": CapabilityStatus("process_restart", True),
        "config_validation": CapabilityStatus("config_validation", True),
        "git_status": CapabilityStatus("git_status", True),
        "resource_rescan": CapabilityStatus("resource_rescan", True),
        "resource_lifecycle": CapabilityStatus("resource_lifecycle", True),
        "resource_rollback": CapabilityStatus("resource_rollback", True),
        "backup": CapabilityStatus("backup", True),
    }


def is_capability_available(capability_id: str) -> bool:
    return inventory_capabilities()[capability_id].available
