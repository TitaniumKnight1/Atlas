from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any

from backend.application.commands import CommandContext, CommandPreview, RiskLevel, UndoPlan
from backend.application.commands.recorder import CommandAuditRecorder
from backend.application.config.service import RestoreConfigFileCompensation
from backend.domain.automation.types import ActionType, RunStatus, SafetyClass
from backend.domain.shared_kernel import ProjectId
from backend.infrastructure.unit_of_work import SingleWriterSQLiteUnitOfWork


class AutomationActionExecutor:
    def __init__(self, *, container: Any, filesystem: Any) -> None:
        self._container = container
        self._filesystem = filesystem
        self._recorder = CommandAuditRecorder()

    def execute(
        self,
        *,
        uow: SingleWriterSQLiteUnitOfWork,
        project_id: ProjectId,
        action_type: str,
        safety_class: str,
        config: dict[str, Any],
        trigger_payload: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        if action_type == ActionType.RECORD_LOCAL_NOTIFICATION.value:
            return self._record_local_notification(config=config, trigger_payload=trigger_payload)
        if action_type == ActionType.APPEND_CONFIG_MARKER.value:
            return self._append_config_marker(
                uow=uow,
                project_id=project_id,
                config=config,
                idempotency_key=idempotency_key,
            )
        raise ValueError(f"Unsupported automation action: {action_type}")

    def undo_step(self, *, uow: SingleWriterSQLiteUnitOfWork, undo_plan_json: dict[str, Any]) -> dict[str, Any]:
        action = _deserialize_compensation(undo_plan_json, filesystem=self._filesystem)
        context = CommandContext(uow=uow)
        return action.apply(context)

    def _record_local_notification(self, *, config: dict[str, Any], trigger_payload: dict[str, Any]) -> dict[str, Any]:
        message = config.get("message") or "Automation notification"
        return {
            "notification": message,
            "trigger_summary": {
                key: trigger_payload.get(key)
                for key in ("alert_event_id", "monitoring_alert_id", "occurrence_id", "process_run_id")
                if key in trigger_payload
            },
        }

    def _append_config_marker(
        self,
        *,
        uow: SingleWriterSQLiteUnitOfWork,
        project_id: ProjectId,
        config: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        from pathlib import Path

        relative_path = config["relative_path"]
        marker_line = config.get("marker_line", "# atlas-automation-marker")
        from backend.adapters.persistence import ProjectRepository

        paths = uow.repository(ProjectRepository).list_paths(project_id, role="root")
        if not paths:
            raise ValueError(f"Project root not found for {project_id}")
        absolute_path = str((Path(paths[0].absolute_path) / relative_path).resolve())
        path = Path(absolute_path)
        prior_content: str | None
        if path.exists():
            prior_content = path.read_text(encoding="utf-8")
            new_content = prior_content + ("\n" if prior_content and not prior_content.endswith("\n") else "") + marker_line + "\n"
        else:
            prior_content = None
            new_content = marker_line + "\n"
        self._filesystem.write_text(path, new_content)
        compensation = RestoreConfigFileCompensation(absolute_path=absolute_path, prior_content=prior_content, filesystem=self._filesystem)
        undo_plan = UndoPlan(
            command_type="automation.append_config_marker",
            summary=f"Restore config file {relative_path}",
            action=compensation,
            payload=compensation.describe(),
        )
        preview = CommandPreview(
            command_type="automation.append_config_marker",
            summary=f"Append marker to {relative_path}",
            preview={"relative_path": relative_path, "marker_line": marker_line},
            risk_level=RiskLevel.DESTRUCTIVE,
        )
        execution = self._recorder.record_success(
            uow=uow,
            preview=preview,
            project_id=project_id,
            entity_type="config_file",
            entity_id=relative_path,
            summary=preview.summary,
            result={"relative_path": relative_path, "appended": True},
            events=[],
            undo_plan=undo_plan,
            idempotency_key=idempotency_key,
        )
        return {
            "relative_path": relative_path,
            "command_execution_id": str(execution.command_execution_id),
            "undo_plan_json": _serialize_undo_plan(compensation),
        }


def _serialize_undo_plan(compensation: RestoreConfigFileCompensation) -> dict[str, Any]:
    return {
        "action_type": compensation.action_type,
        "absolute_path": compensation.absolute_path,
        "prior_content": compensation.prior_content,
    }


def _deserialize_compensation(undo_plan_json: dict[str, Any], *, filesystem: Any) -> RestoreConfigFileCompensation:
    return RestoreConfigFileCompensation(
        absolute_path=undo_plan_json["absolute_path"],
        prior_content=undo_plan_json.get("prior_content"),
        filesystem=filesystem,
    )
