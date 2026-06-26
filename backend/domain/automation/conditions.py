from __future__ import annotations

from typing import Any

from backend.domain.automation.types import ConditionType


def evaluate_conditions(conditions: list[dict[str, Any]], event_payload: dict[str, Any]) -> bool:
    if not conditions:
        return True
    for condition in conditions:
        condition_type = condition.get("condition_type")
        config = condition.get("config_json") or {}
        if condition_type == ConditionType.ALWAYS.value:
            continue
        if condition_type == ConditionType.SEVERITY_EQUALS.value:
            expected = config.get("severity")
            if event_payload.get("severity") != expected:
                return False
            continue
        return False
    return True
