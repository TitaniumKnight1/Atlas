from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from backend.domain.automation.capabilities import is_capability_available
from backend.domain.automation.recipes import catalog_recipes, get_recipe, list_recipe_catalog
from backend.domain.automation.types import ExecutionTier, RecipeInstanceStatus, RecipeKey
from backend.domain.shared_kernel import ErrorCode, ProjectId


class RecipeInstantiationError(RuntimeError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


def list_available_recipes() -> list[dict[str, Any]]:
    return list_recipe_catalog()


def instantiate_recipe(
    service: Any,
    project_id: ProjectId,
    recipe_key: str,
    *,
    params: dict[str, Any] | None = None,
    is_enabled: bool = True,
) -> dict[str, Any]:
    recipe = get_recipe(recipe_key)
    if recipe is None:
        raise RecipeInstantiationError(ErrorCode.NOT_FOUND, f"Unknown recipe: {recipe_key}")
    params = dict(params or {})
    deferred = recipe.deferred_capabilities()
    resolved_actions = recipe.resolved_actions()
    if not resolved_actions:
        raise RecipeInstantiationError(
            ErrorCode.PRECONDITION_FAILED,
            f"Recipe {recipe_key} is deferred; missing capabilities: {', '.join(deferred)}",
        )
    actions = []
    for template in resolved_actions:
        actions.append(
            {
                "action_type": template.action_type,
                "safety_class": template.safety_class,
                "config_json": {
                    **template.config_json,
                    "execution_tier": template.execution_tier,
                    **params,
                },
            }
        )
    workflow = service.create_workflow(
        project_id,
        name=recipe.name,
        description=f"recipe:{recipe.recipe_key}",
        trigger_type=recipe.trigger_type,
        trigger_config={**recipe.trigger_config, **params},
        conditions=recipe.conditions or None,
        actions=actions,
        schedule_interval_seconds=recipe.schedule_interval_seconds,
        is_enabled=is_enabled,
    )
    from backend.adapters.persistence import AutomationRepository
    from backend.domain.shared_kernel import StableIdentifier

    now = datetime.now(UTC)
    instance_status = RecipeInstanceStatus.ACTIVE.value
    if deferred and not resolved_actions:
        instance_status = RecipeInstanceStatus.DEFERRED.value
    with service._container.create_unit_of_work(project_id) as uow:
        uow.begin()
        uow.repository(AutomationRepository).create_recipe_instance(
            instance_id=StableIdentifier.new(),
            project_id=project_id,
            recipe_key=recipe_key,
            workflow_id=workflow["automation_workflow_id"],
            params_json=params,
            instance_status=instance_status,
            deferred_capabilities=deferred,
            created_at=now,
        )
        uow.commit()
    return {
        **workflow,
        "recipe_key": recipe_key,
        "instance_status": instance_status,
        "deferred_capabilities": deferred,
        "resolved_action_count": len(resolved_actions),
    }
