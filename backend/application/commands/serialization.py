from __future__ import annotations

from typing import Any

from backend.application.commands.compensation import CompositeCompensation, RestorePathFromSnapshotCompensation


def compensation_to_storage(action: Any) -> dict[str, Any]:
    from backend.application.config.service import RestoreConfigFileCompensation
    from backend.application.git.service import RemoveClonedRepositoryCompensation

    if isinstance(action, CompositeCompensation):
        return {
            "action_type": action.action_type,
            "steps": [compensation_to_storage(step) for step in action.actions],
        }
    if isinstance(action, RemoveClonedRepositoryCompensation):
        return {"action_type": action.action_type, "local_path": action.local_path}
    if isinstance(action, RestoreConfigFileCompensation):
        return {
            "action_type": action.action_type,
            "absolute_path": action.absolute_path,
            "prior_content": action.prior_content,
        }
    if isinstance(action, RestorePathFromSnapshotCompensation):
        return {
            "action_type": action.action_type,
            "snapshot_path": action.snapshot_path,
            "target_path": action.target_path,
        }
    raise ValueError(f"Unsupported compensation type for storage: {type(action)!r}")


def compensation_from_storage(payload: dict[str, Any], *, filesystem: Any) -> Any:
    from backend.application.config.service import RestoreConfigFileCompensation
    from backend.application.git.service import RemoveClonedRepositoryCompensation

    action_type = payload.get("action_type")
    if action_type == "composite_compensation":
        steps = tuple(compensation_from_storage(step, filesystem=filesystem) for step in payload.get("steps", []))
        return CompositeCompensation(steps)
    if action_type == "remove_cloned_repository":
        return RemoveClonedRepositoryCompensation(str(payload["local_path"]))
    if action_type == "restore_config_file":
        return RestoreConfigFileCompensation(
            str(payload["absolute_path"]),
            payload.get("prior_content"),
            filesystem,
        )
    if action_type == "restore_path_from_snapshot":
        return RestorePathFromSnapshotCompensation(str(payload["snapshot_path"]), str(payload["target_path"]))
    raise ValueError(f"Unsupported stored compensation action: {action_type!r}")
