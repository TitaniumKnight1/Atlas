from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from typing import Any

from backend.domain.automation.capabilities import inventory_capabilities, is_capability_available
from backend.domain.automation.types import ActionType, ConditionType, ExecutionTier, RecipeKey, TriggerType


@dataclass(frozen=True, slots=True)
class RecipeActionTemplate:
    action_type: str
    execution_tier: str
    safety_class: str
    config_json: dict[str, Any] = field(default_factory=dict)
    capability_id: str | None = None


@dataclass(frozen=True, slots=True)
class RecipeTemplate:
    recipe_key: str
    name: str
    description: str
    trigger_type: str
    trigger_config: dict[str, Any] = field(default_factory=dict)
    conditions: list[dict[str, Any]] = field(default_factory=list)
    actions: tuple[RecipeActionTemplate, ...] = ()
    schedule_interval_seconds: int | None = None
    required_capabilities: tuple[str, ...] = ()

    def deferred_capabilities(self) -> list[str]:
        return [cap for cap in self.required_capabilities if not is_capability_available(cap)]

    def is_fully_available(self) -> bool:
        return not self.deferred_capabilities()

    def resolved_actions(self) -> list[RecipeActionTemplate]:
        """Actions that can run; omits steps whose capability is missing."""
        resolved: list[RecipeActionTemplate] = []
        for action in self.actions:
            if action.capability_id and not is_capability_available(action.capability_id):
                continue
            resolved.append(action)
        return resolved


def catalog_recipes() -> dict[str, RecipeTemplate]:
    return {recipe.recipe_key: recipe for recipe in _BUILTIN_RECIPES}


def get_recipe(recipe_key: str) -> RecipeTemplate | None:
    return catalog_recipes().get(recipe_key)


_BUILTIN_RECIPES: tuple[RecipeTemplate, ...] = (
    RecipeTemplate(
        recipe_key=RecipeKey.RESTART_ON_CRASH.value,
        name="Restart on crash",
        description="When the server crashes, request approval to restart via M3b process supervision.",
        trigger_type=TriggerType.SERVER_CRASHED.value,
        required_capabilities=("process_restart",),
        actions=(
            RecipeActionTemplate(
                action_type=ActionType.RESTART_SERVER.value,
                execution_tier=ExecutionTier.APPROVAL_GATED.value,
                safety_class="process_control",
            ),
        ),
    ),
    RecipeTemplate(
        recipe_key=RecipeKey.POST_GIT_PULL_VALIDATION.value,
        name="Post git-pull validation",
        description="After a successful git pull, validate config and rescan resources; optional gated restart.",
        trigger_type=TriggerType.GIT_PULL_COMPLETED.value,
        required_capabilities=("config_validation", "resource_rescan"),
        actions=(
            RecipeActionTemplate(
                action_type=ActionType.RUN_CONFIG_VALIDATION.value,
                execution_tier=ExecutionTier.AUTO.value,
                safety_class="read_only",
                capability_id="config_validation",
            ),
            RecipeActionTemplate(
                action_type=ActionType.RESCAN_RESOURCES.value,
                execution_tier=ExecutionTier.AUTO.value,
                safety_class="read_only",
                capability_id="resource_rescan",
            ),
            RecipeActionTemplate(
                action_type=ActionType.RESTART_SERVER.value,
                execution_tier=ExecutionTier.APPROVAL_GATED.value,
                safety_class="process_control",
                config_json={"optional": True},
                capability_id="process_restart",
            ),
        ),
    ),
    RecipeTemplate(
        recipe_key=RecipeKey.NIGHTLY_MAINTENANCE.value,
        name="Nightly maintenance",
        description="Scheduled validation and git status; backup deferred until backup module exists.",
        trigger_type=TriggerType.SCHEDULE.value,
        trigger_config={"interval_seconds": 86400},
        schedule_interval_seconds=86400,
        required_capabilities=("config_validation", "git_status", "backup"),
        actions=(
            RecipeActionTemplate(
                action_type=ActionType.RUN_CONFIG_VALIDATION.value,
                execution_tier=ExecutionTier.AUTO.value,
                safety_class="read_only",
                capability_id="config_validation",
            ),
            RecipeActionTemplate(
                action_type=ActionType.GIT_CAPTURE_STATUS.value,
                execution_tier=ExecutionTier.AUTO.value,
                safety_class="read_only",
                capability_id="git_status",
            ),
            RecipeActionTemplate(
                action_type=ActionType.CREATE_BACKUP.value,
                execution_tier=ExecutionTier.APPROVAL_GATED.value,
                safety_class="destructive",
                capability_id="backup",
            ),
        ),
    ),
    RecipeTemplate(
        recipe_key=RecipeKey.ON_ALERT_REMEDIATION.value,
        name="On-alert remediation",
        description="Notify on any alert; request approval to restart when severity is critical.",
        trigger_type=TriggerType.ALERT_FIRED.value,
        conditions=[{"condition_type": ConditionType.ALWAYS.value}],
        required_capabilities=("process_restart",),
        actions=(
            RecipeActionTemplate(
                action_type=ActionType.RECORD_LOCAL_NOTIFICATION.value,
                execution_tier=ExecutionTier.AUTO.value,
                safety_class="read_only",
                config_json={"message": "Alert fired"},
            ),
            RecipeActionTemplate(
                action_type=ActionType.RESTART_SERVER.value,
                execution_tier=ExecutionTier.APPROVAL_GATED.value,
                safety_class="process_control",
                config_json={"require_severity": "critical"},
                capability_id="process_restart",
            ),
        ),
    ),
)


def list_recipe_catalog() -> list[dict[str, Any]]:
    caps = inventory_capabilities()
    items: list[dict[str, Any]] = []
    for recipe in _BUILTIN_RECIPES:
        deferred = recipe.deferred_capabilities()
        items.append(
            {
                "recipe_key": recipe.recipe_key,
                "name": recipe.name,
                "description": recipe.description,
                "trigger_type": recipe.trigger_type,
                "required_capabilities": list(recipe.required_capabilities),
                "deferred_capabilities": deferred,
                "instantiation_status": "deferred" if deferred else "available",
                "actions": [
                    {
                        "action_type": action.action_type,
                        "execution_tier": action.execution_tier,
                        "safety_class": action.safety_class,
                        "capability_id": action.capability_id,
                        "deferred": action.capability_id in deferred if action.capability_id else False,
                    }
                    for action in recipe.actions
                ],
                "capabilities": {
                    cap: {
                        "capability_id": caps[cap].capability_id,
                        "available": caps[cap].available,
                        "reason": caps[cap].reason,
                    }
                    for cap in recipe.required_capabilities
                    if cap in caps
                },
            }
        )
    return items
