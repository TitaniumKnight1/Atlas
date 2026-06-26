from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.application.commands import CommandPreview, RiskLevel, UndoPlan
from backend.application.commands.recorder import CommandAuditRecorder
from backend.application.config.service import RestoreConfigFileCompensation
from backend.domain.automation.types import ActionType, ExecutionTier
from backend.domain.shared_kernel import ProjectId
from backend.infrastructure.unit_of_work import SingleWriterSQLiteUnitOfWork


class ActionDeferredError(RuntimeError):
    """Raised when a recipe action depends on a capability that is not available."""


class AutomationActionExecutor:
    def __init__(self, *, container: Any, filesystem: Any) -> None:
        self._container = container
        self._filesystem = filesystem
        self._recorder = CommandAuditRecorder()

    def preview(
        self,
        *,
        project_id: ProjectId,
        action_type: str,
        config: dict[str, Any],
        trigger_payload: dict[str, Any],
    ) -> dict[str, Any]:
        if self._should_skip_action(action_type, config, trigger_payload):
            return {"skipped": True, "reason": "conditions_not_met"}
        if action_type == ActionType.CREATE_BACKUP.value:
            return {"action_type": action_type, "summary": "Create local project backup", "preview": {"scope": "full"}}
        if action_type == ActionType.RESTART_SERVER.value:
            process_run_id = trigger_payload.get("process_run_id") or config.get("process_run_id")
            return {
                "action_type": action_type,
                "summary": "Restart supervised FXServer process",
                "risk_level": RiskLevel.HIGH.value,
                "preview": {
                    "process_run_id": process_run_id,
                    "fxserver_path": config.get("fxserver_path"),
                    "server_data_path": config.get("server_data_path"),
                },
            }
        if action_type == ActionType.RUN_CONFIG_VALIDATION.value:
            return {"action_type": action_type, "summary": "Run config validation", "preview": {"scope": "project"}}
        if action_type == ActionType.RESCAN_RESOURCES.value:
            return {"action_type": action_type, "summary": "Rescan resource inventory", "preview": {}}
        if action_type == ActionType.GIT_CAPTURE_STATUS.value:
            return {
                "action_type": action_type,
                "summary": "Capture git worktree status",
                "preview": {"git_repository_id": config.get("git_repository_id") or trigger_payload.get("git_repository_id")},
            }
        if action_type == ActionType.RECORD_LOCAL_NOTIFICATION.value:
            return {"action_type": action_type, "summary": config.get("message", "Automation notification"), "preview": {}}
        if action_type == ActionType.APPEND_CONFIG_MARKER.value:
            return {"action_type": action_type, "summary": f"Append marker to {config.get('relative_path')}", "preview": config}
        raise ValueError(f"Unsupported automation action: {action_type}")

    def execute(
        self,
        *,
        project_id: ProjectId,
        action_type: str,
        safety_class: str,
        config: dict[str, Any],
        trigger_payload: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        if self._should_skip_action(action_type, config, trigger_payload):
            return {"skipped": True, "reason": "conditions_not_met"}
        if action_type in {ActionType.RECORD_LOCAL_NOTIFICATION.value}:
            return self._record_local_notification(config=config, trigger_payload=trigger_payload)
        if action_type == ActionType.APPEND_CONFIG_MARKER.value:
            with self._container.create_unit_of_work(project_id) as uow:
                uow.begin()
                result = self._append_config_marker(
                    uow=uow,
                    project_id=project_id,
                    config=config,
                    idempotency_key=idempotency_key,
                )
                uow.commit()
            return result
        if action_type == ActionType.RUN_CONFIG_VALIDATION.value:
            result = self._container.create_config_service().execute_run_validation(
                project_id=project_id,
                config_file_id=config.get("config_file_id"),
            )
            return {"validation": result}
        if action_type == ActionType.RESCAN_RESOURCES.value:
            result = self._container.create_resource_service().execute_rescan_resources(
                project_id=project_id,
                path_filters=config.get("path_filters"),
            )
            return {"rescan": result}
        if action_type == ActionType.GIT_CAPTURE_STATUS.value:
            git_repository_id = config.get("git_repository_id") or trigger_payload.get("git_repository_id")
            if not git_repository_id:
                raise ValueError("git_repository_id is required for git_capture_status")
            result = self._container.create_git_service().execute_capture_git_status_snapshot(
                project_id=project_id,
                git_repository_id=git_repository_id,
            )
            return {"git_status": result}
        if action_type == ActionType.RESTART_SERVER.value:
            process_run_id = trigger_payload.get("process_run_id") or config.get("process_run_id")
            if not process_run_id:
                raise ValueError("process_run_id is required to restart server")
            fxserver_path = config.get("fxserver_path")
            server_data_path = config.get("server_data_path")
            if not fxserver_path or not server_data_path:
                raise ValueError("fxserver_path and server_data_path are required to restart server")
            execution = self._container.create_setup_service().execute_restart_server(
                project_id=project_id,
                process_run_id=process_run_id,
                fxserver_path=fxserver_path,
                server_data_path=server_data_path,
                txadmin_mode=bool(config.get("txadmin_mode", False)),
                extra_args=config.get("extra_args"),
            )
            return {
                "restarted": True,
                "process_run_id": execution.result.get("process_run_id"),
                "command_execution_id": str(execution.command_execution_id),
            }
        if action_type == ActionType.CREATE_BACKUP.value:
            from backend.domain.backup.types import BackupTriggerType

            result = self._container.create_backup_service().execute_run_backup(
                project_id=project_id,
                trigger_type=BackupTriggerType.AUTOMATION.value,
                idempotency_key=idempotency_key,
            )
            return {"backup": result}
        raise ValueError(f"Unsupported automation action: {action_type}")

    def undo_step(self, *, uow: SingleWriterSQLiteUnitOfWork, undo_plan_json: dict[str, Any]) -> dict[str, Any]:
        from backend.application.commands import CommandContext

        action = _deserialize_compensation(undo_plan_json, filesystem=self._filesystem)
        context = CommandContext(uow=uow)
        return action.apply(context)

    def _should_skip_action(self, action_type: str, config: dict[str, Any], trigger_payload: dict[str, Any]) -> bool:
        required_severity = config.get("require_severity")
        if required_severity and trigger_payload.get("severity") != required_severity:
            return True
        if config.get("optional") and action_type == ActionType.RESTART_SERVER.value:
            if not config.get("enable_optional_restart", False):
                return True
        return False

    def _record_local_notification(self, *, config: dict[str, Any], trigger_payload: dict[str, Any]) -> dict[str, Any]:
        message = config.get("message") or "Automation notification"
        return {
            "notification": message,
            "trigger_summary": {
                key: trigger_payload.get(key)
                for key in ("alert_event_id", "monitoring_alert_id", "occurrence_id", "process_run_id", "git_operation_id")
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
        from backend.adapters.persistence import ProjectRepository

        relative_path = config["relative_path"]
        marker_line = config.get("marker_line", "# atlas-automation-marker")
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


def action_execution_tier(config: dict[str, Any] | None) -> str:
    payload = config or {}
    return payload.get("execution_tier", ExecutionTier.AUTO.value)


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
