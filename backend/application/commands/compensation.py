from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.application.commands.contracts import CommandContext, CompensatingAction


@dataclass(frozen=True, slots=True)
class CompositeCompensation:
    """Runs multiple compensations in reverse order (LIFO) for atomic multi-effect undo."""

    actions: tuple[CompensatingAction, ...]
    action_type: str = "composite_compensation"

    def describe(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "steps": [action.describe() for action in self.actions],
        }

    def apply(self, context: CommandContext) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        for action in reversed(self.actions):
            results.append(action.apply(context))
        return {"steps": results}


@dataclass(frozen=True, slots=True)
class RestorePathFromSnapshotCompensation:
    snapshot_path: str
    target_path: str
    action_type: str = "restore_path_from_snapshot"

    def describe(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "snapshot_path": self.snapshot_path,
            "target_path": self.target_path,
        }

    def apply(self, context: CommandContext) -> dict[str, Any]:
        snapshot = Path(self.snapshot_path)
        target = Path(self.target_path)
        if not snapshot.exists():
            return {"restored": False, "reason": "snapshot_missing"}
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        if snapshot.is_dir():
            shutil.copytree(snapshot, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(snapshot, target)
        return {"restored": True, "target_path": str(target)}
