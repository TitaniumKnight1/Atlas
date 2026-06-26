from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.application.commands import CommandPreview, RiskLevel, UndoPlan
from backend.application.commands.recorder import CommandAuditRecorder
from backend.application.config.service import RestoreConfigFileCompensation
from backend.domain.plugin.ipc import capability_response_message
from backend.domain.plugin.runtime_types import CapabilityCallDecision, CapabilityCallOutcome
from backend.domain.plugin.types import PluginCapability
from backend.domain.shared_kernel import ProjectId, StableIdentifier


class PluginCapabilityMediator:
    """Mediates plugin capability requests against M9a grants via Atlas services."""

    def __init__(self, *, container: Any, filesystem: Any) -> None:
        self._container = container
        self._filesystem = filesystem
        self._recorder = CommandAuditRecorder()

    def handle_request(
        self,
        *,
        plugin_id: str,
        project_id: ProjectId,
        runtime_id: str | None,
        message: dict[str, Any],
        is_granted: bool,
    ) -> dict[str, Any]:
        request_id = str(message.get("request_id") or StableIdentifier.new())
        capability = str(message.get("capability") or "")
        params = message.get("params") or {}
        if not is_granted:
            return capability_response_message(
                request_id=request_id,
                granted=False,
                error=f"Capability not granted: {capability}",
            )
        try:
            PluginCapability(capability)
        except ValueError:
            return capability_response_message(
                request_id=request_id,
                granted=False,
                error=f"Unknown capability: {capability}",
            )
        try:
            result = self._execute_granted(plugin_id, project_id, capability, params)
        except Exception as error:  # noqa: BLE001
            return capability_response_message(request_id=request_id, granted=True, error=str(error))
        return capability_response_message(request_id=request_id, granted=True, result=result)

    def _execute_granted(self, plugin_id: str, project_id: ProjectId, capability: str, params: dict[str, Any]) -> dict[str, Any]:
        if capability == PluginCapability.READ_PROJECT_METADATA.value:
            project = self._container.create_project_service().get_project(project_id)
            return {"project": project}
        if capability == PluginCapability.READ_CONFIG.value:
            files = self._container.create_config_service().list_config_files(project_id)
            return {"config_files": files}
        if capability == PluginCapability.READ_INCIDENTS.value:
            incidents = self._container.create_incident_service().list_incidents(project_id, limit=int(params.get("limit", 10)))
            return {"incidents": incidents}
        if capability == PluginCapability.FILESYSTEM_WRITE.value:
            return self._write_file(project_id, params)
        if capability == PluginCapability.NETWORK.value:
            raise PermissionError("Network access is blocked by Atlas plugin host")
        if capability == PluginCapability.TELEMETRY_SUBMIT.value:
            raise PermissionError("Plugins cannot submit telemetry directly; sanitizer boundary enforced")
        raise PermissionError(f"Capability not mediated in M9b: {capability}")

    def _write_file(self, project_id: ProjectId, params: dict[str, Any]) -> dict[str, Any]:
        relative_path = str(params.get("relative_path") or "")
        content = str(params.get("content") or "")
        if not relative_path:
            raise ValueError("relative_path is required")
        from backend.adapters.persistence import ProjectRepository

        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            paths = uow.repository(ProjectRepository).list_paths(project_id, role="root")
            if not paths:
                raise ValueError("Project root not found")
            absolute_path = str((Path(paths[0].absolute_path) / relative_path).resolve())
            path = Path(absolute_path)
            prior_content = path.read_text(encoding="utf-8") if path.exists() else None
            self._filesystem.write_text(path, content)
            compensation = RestoreConfigFileCompensation(absolute_path=absolute_path, prior_content=prior_content, filesystem=self._filesystem)
            undo_plan = UndoPlan(
                command_type="plugin.filesystem_write",
                summary=f"Restore file {relative_path} after plugin write",
                action=compensation,
                payload=compensation.describe(),
            )
            preview = CommandPreview(
                command_type="plugin.filesystem_write",
                summary=f"Plugin-mediated write to {relative_path}",
                preview={"relative_path": relative_path},
                risk_level=RiskLevel.DESTRUCTIVE,
            )
            execution = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="plugin_filesystem",
                entity_id=relative_path,
                summary=preview.summary,
                result={"relative_path": relative_path, "bytes_written": len(content.encode("utf-8"))},
                events=[],
                undo_plan=undo_plan,
                idempotency_key=params.get("idempotency_key"),
            )
            uow.commit()
        return {"relative_path": relative_path, "command_execution_id": str(execution.command_execution_id)}
