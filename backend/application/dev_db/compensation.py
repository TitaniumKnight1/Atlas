from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.application.commands.contracts import CommandContext


@dataclass(frozen=True, slots=True)
class ClearDevDatabaseSettingsCompensation:
    project_id: str
    action_type: str = "clear_dev_database_settings"

    def describe(self) -> dict[str, Any]:
        return {"action_type": self.action_type, "project_id": self.project_id}

    def apply(self, context: CommandContext) -> dict[str, Any]:
        return {"project_id": self.project_id, "cleared": True}


@dataclass(frozen=True, slots=True)
class RestoreDevDatabaseSettingsCompensation:
    project_id: str
    prior_settings: dict[str, Any]
    action_type: str = "restore_dev_database_settings"

    def describe(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "project_id": self.project_id,
            "prior_settings": self.prior_settings,
        }

    def apply(self, context: CommandContext) -> dict[str, Any]:
        return {"project_id": self.project_id, "restored_keys": list(self.prior_settings.keys())}
