from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.adapters.filesystem.resource_scanner import LocalResourceScanner, infer_resource_type
from backend.adapters.git import GitPythonProvider
from backend.adapters.persistence import ProjectRepository, ResourceRepository
from backend.application.commands import (
    CommandContext,
    CommandExecutionResult,
    CommandPreview,
    CompositeCompensation,
    DryRunResult,
    RestorePathFromSnapshotCompensation,
    RiskLevel,
    UndoPlan,
)
from backend.application.commands.serialization import compensation_to_storage
from backend.application.commands.recorder import CommandAuditRecorder
from backend.application.config.service import RestoreConfigFileCompensation
from backend.application.git.service import RemoveClonedRepositoryCompensation
from backend.application.resources.server_cfg_ops import add_ensure_line, list_ensure_lines, remove_ensure_line
from backend.application.resources.service import ResourceApplicationService
from backend.domain.resources.events import (
    resource_deleted,
    resource_enabled_state_changed,
    resource_installed,
    resource_inventory_changed,
    resource_updated,
)
from backend.domain.resources.types import EnabledState
from backend.domain.shared_kernel import ErrorCode, ProjectId, StableIdentifier


class ResourceLifecycleError(RuntimeError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class InstallSource:
    source_type: str
    source_uri: str


class ResourceLifecycleService:
    """M5b single-resource lifecycle mutations composing M3a/M4a/M4b with composite undo."""

    def __init__(self, *, container: Any, filesystem: Any, stream_publisher: Any | None = None) -> None:
        self._container = container
        self._filesystem = filesystem
        self._scanner = LocalResourceScanner(filesystem)
        self._resources = ResourceApplicationService(container=container, filesystem=filesystem)
        self._git_provider = GitPythonProvider()
        self._stream_publisher = stream_publisher
        self._recorder = CommandAuditRecorder()

    def preview_install_resource(
        self,
        *,
        project_id: ProjectId,
        source: InstallSource,
        resource_name: str | None = None,
        enable: bool = True,
    ) -> CommandPreview:
        manifest_info, target_name, target_path, warnings = self._resolve_install_target(project_id, source, resource_name)
        server_cfg = self._server_cfg_binding(project_id)
        proposed = server_cfg["content"]
        ensure_index = None
        if enable:
            proposed, ensure_index = add_ensure_line(
                proposed,
                target_name,
                dependency_names=manifest_info["dependencies"],
            )
        config_preview = self._config_service().preview_plan_config_change(
            project_id=project_id,
            config_file_id=server_cfg["config_file_id"],
            proposed_content=proposed,
        )
        warnings.extend(self._missing_dependency_warnings(project_id, manifest_info["dependencies"]))
        if self._resources.list_resources(project_id):
            existing = self._existing_by_name(project_id, target_name)
            if existing is not None:
                warnings.append(f"Resource name collision: {target_name} already exists in inventory.")
        return CommandPreview(
            "PlanInstallResource",
            f"Install resource {target_name} from {source.source_type}",
            {
                "project_id": str(project_id),
                "source_type": source.source_type,
                "source_uri": source.source_uri,
                "resource_name": target_name,
                "target_path": str(target_path),
                "manifest": manifest_info,
                "enable": enable,
                "server_cfg_diff": config_preview.preview.get("diff"),
                "ensure_line_index": ensure_index,
            },
            warnings=warnings,
            risk_level=RiskLevel.HIGH,
        )

    def dry_run_install_resource(
        self,
        *,
        project_id: ProjectId,
        source: InstallSource,
        resource_name: str | None = None,
        enable: bool = True,
    ) -> DryRunResult:
        preview = self.preview_install_resource(
            project_id=project_id,
            source=source,
            resource_name=resource_name,
            enable=enable,
        )
        valid = self._validate_install_source(source) and self._existing_by_name(project_id, preview.preview["resource_name"]) is None
        if not preview.preview["manifest"]["manifest_valid"]:
            valid = False
        return DryRunResult(preview.command_type, valid, preview.preview, preview.warnings)

    def execute_install_resource(
        self,
        *,
        project_id: ProjectId,
        source: InstallSource,
        resource_name: str | None = None,
        enable: bool = True,
        idempotency_key: str | None = None,
    ) -> CommandExecutionResult:
        dry_run = self.dry_run_install_resource(
            project_id=project_id,
            source=source,
            resource_name=resource_name,
            enable=enable,
        )
        if not dry_run.valid:
            raise ResourceLifecycleError(ErrorCode.VALIDATION_FAILED, "Install resource dry-run failed validation")
        preview = self.preview_install_resource(
            project_id=project_id,
            source=source,
            resource_name=resource_name,
            enable=enable,
        )
        target_name = preview.preview["resource_name"]
        target_path = Path(preview.preview["target_path"])
        operation_id = StableIdentifier.new()
        self._materialize_install_source(project_id, source, target_path, str(operation_id))
        discovered = next(
            item
            for item in self._scanner.discover_resources([target_path.parent])
            if item.resource_name == target_name or Path(item.absolute_path).resolve() == target_path.resolve()
        )
        compensations: list[Any] = [RemoveClonedRepositoryCompensation(str(target_path))]
        server_cfg = self._server_cfg_binding(project_id)
        proposed = server_cfg["content"]
        if enable:
            proposed, _ = add_ensure_line(
                proposed,
                target_name,
                dependency_names=list(discovered.manifest.dependencies),
            )
        config_compensation = self._write_server_cfg(server_cfg["absolute_path"], proposed)
        compensations.append(config_compensation)
        composite = CompositeCompensation(tuple(compensations))
        now = datetime.now(UTC)
        resource_id = StableIdentifier.new()
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            self._require_project(uow.repository(ProjectRepository), project_id)
            repository = uow.repository(ResourceRepository)
            record = repository.upsert_resource(
                resource_id=resource_id,
                project_id=project_id,
                resource_name=target_name,
                relative_path=str(target_path.relative_to(self._resources_root(project_id))).replace("\\", "/"),
                resource_type=infer_resource_type(discovered.manifest, target_name),
                enabled_state=EnabledState.ENABLED.value if enable else EnabledState.DISABLED.value,
                startup_order=list_ensure_lines(proposed).index(target_name) + 1 if enable and target_name in list_ensure_lines(proposed) else None,
                current_version_id=None,
                git_repository_id=None,
                created_at=now,
                updated_at=now,
            )
            uow.session.flush()
            version = repository.add_version(
                version_id=StableIdentifier.new(),
                resource_id=record.resource_id,
                version_label=discovered.manifest.version,
                content_hash=discovered.content_hash,
                manifest_json=_manifest_json(discovered),
                detected_at=now,
                source_ref=source.source_uri,
            )
            record.current_version_id = version.resource_version_id
            repository.upsert_install_source(
                resource_id=record.resource_id,
                source_type=source.source_type,
                source_uri=source.source_uri,
                metadata={"target_path": str(target_path)},
                trusted_at=now,
            )
            execution = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="Resource",
                entity_id=record.resource_id,
                summary=f"Installed resource {target_name}",
                result={
                    "project_id": str(project_id),
                    "resource_id": record.resource_id,
                    "resource_name": target_name,
                    "operation_id": str(operation_id),
                },
                events=[
                    resource_installed(project_id, record.resource_id, target_name),
                    resource_inventory_changed(project_id, 1, 0, 0),
                ],
                undo_plan=UndoPlan(
                    "UndoInstallResource",
                    f"Remove installed resource {target_name} and restore server.cfg",
                    composite,
                    {**compensation_to_storage(composite), "project_id": str(project_id)},
                ),
                idempotency_key=idempotency_key,
            )
            repository.add_state_change(
                state_change_id=StableIdentifier.new(),
                resource_id=record.resource_id,
                change_type="install",
                from_state=None,
                to_state=EnabledState.ENABLED.value if enable else EnabledState.DISABLED.value,
                command_execution_id=str(execution.command_execution_id),
                changed_at=now,
                details={"source_type": source.source_type},
            )
            uow.commit()
        return execution

    def preview_update_resource(
        self,
        *,
        project_id: ProjectId,
        resource_id: str,
        source: InstallSource,
    ) -> CommandPreview:
        record = self._get_resource(project_id, resource_id)
        manifest_info, _, target_path, warnings = self._resolve_install_target(
            project_id, source, record.resource_name, existing_path=Path(self._absolute_resource_path(project_id, record))
        )
        return CommandPreview(
            "PlanUpdateResource",
            f"Update resource {record.resource_name}",
            {
                "project_id": str(project_id),
                "resource_id": resource_id,
                "resource_name": record.resource_name,
                "target_path": str(target_path),
                "source_type": source.source_type,
                "source_uri": source.source_uri,
                "manifest": manifest_info,
            },
            warnings=warnings,
            risk_level=RiskLevel.HIGH,
        )

    def dry_run_update_resource(self, *, project_id: ProjectId, resource_id: str, source: InstallSource) -> DryRunResult:
        preview = self.preview_update_resource(project_id=project_id, resource_id=resource_id, source=source)
        valid = self._validate_install_source(source) and preview.preview["manifest"]["manifest_valid"]
        return DryRunResult(preview.command_type, valid, preview.preview, preview.warnings)

    def execute_update_resource(
        self,
        *,
        project_id: ProjectId,
        resource_id: str,
        source: InstallSource,
        idempotency_key: str | None = None,
    ) -> CommandExecutionResult:
        dry_run = self.dry_run_update_resource(project_id=project_id, resource_id=resource_id, source=source)
        if not dry_run.valid:
            raise ResourceLifecycleError(ErrorCode.VALIDATION_FAILED, "Update resource dry-run failed validation")
        preview = self.preview_update_resource(project_id=project_id, resource_id=resource_id, source=source)
        record = self._get_resource(project_id, resource_id)
        target_path = Path(preview.preview["target_path"])
        operation_id = StableIdentifier.new()
        snapshot_path = self._snapshot_path(project_id, str(operation_id))
        shutil.copytree(target_path, snapshot_path)
        self._materialize_install_source(project_id, source, target_path, str(operation_id), replace=True)
        compensation = CompositeCompensation(
            (RestorePathFromSnapshotCompensation(str(snapshot_path), str(target_path)),)
        )
        discovered = self._scanner.discover_resources([target_path.parent])
        item = next(entry for entry in discovered if entry.resource_name == record.resource_name)
        now = datetime.now(UTC)
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(ResourceRepository)
            version = repository.add_version(
                version_id=StableIdentifier.new(),
                resource_id=record.resource_id,
                version_label=item.manifest.version,
                content_hash=item.content_hash,
                manifest_json=_manifest_json(item),
                detected_at=now,
                source_ref=source.source_uri,
            )
            record.current_version_id = version.resource_version_id
            record.updated_at = now.isoformat()
            execution = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="Resource",
                entity_id=record.resource_id,
                summary=f"Updated resource {record.resource_name}",
                result={
                    "project_id": str(project_id),
                    "resource_id": record.resource_id,
                    "resource_version_id": version.resource_version_id,
                    "operation_id": str(operation_id),
                },
                events=[resource_updated(project_id, record.resource_id, item.manifest.version)],
                undo_plan=UndoPlan(
                    "UndoUpdateResource",
                    f"Restore prior files for {record.resource_name}",
                    compensation,
                    {**compensation_to_storage(compensation), "project_id": str(project_id)},
                ),
                idempotency_key=idempotency_key,
            )
            repository.add_state_change(
                state_change_id=StableIdentifier.new(),
                resource_id=record.resource_id,
                change_type="update",
                from_state=record.enabled_state,
                to_state=record.enabled_state,
                command_execution_id=str(execution.command_execution_id),
                changed_at=now,
                details={"version_label": item.manifest.version},
            )
            uow.commit()
        return execution

    def preview_set_enabled_state(self, *, project_id: ProjectId, resource_id: str, enabled: bool) -> CommandPreview:
        record = self._get_resource(project_id, resource_id)
        server_cfg = self._server_cfg_binding(project_id)
        enabled_map = self._scanner.parse_server_cfg_enabled(server_cfg["content"])
        currently_enabled = enabled_map.get(record.resource_name, False)
        proposed = server_cfg["content"]
        warnings: list[str] = []
        if enabled and not currently_enabled:
            deps = self._resources.get_resource_dependencies(project_id, resource_id)
            warnings.extend(self._missing_dependency_warnings(project_id, deps))
            proposed, _ = add_ensure_line(proposed, record.resource_name, dependency_names=deps)
        elif not enabled and currently_enabled:
            proposed = remove_ensure_line(proposed, record.resource_name)
            warnings.extend(self._enabled_dependent_warnings(project_id, resource_id))
        config_preview = self._config_service().preview_plan_config_change(
            project_id=project_id,
            config_file_id=server_cfg["config_file_id"],
            proposed_content=proposed,
        )
        return CommandPreview(
            "SetResourceEnabledState",
            f"{'Enable' if enabled else 'Disable'} resource {record.resource_name}",
            {
                "project_id": str(project_id),
                "resource_id": resource_id,
                "resource_name": record.resource_name,
                "from_enabled": currently_enabled,
                "to_enabled": enabled,
                "server_cfg_diff": config_preview.preview.get("diff"),
            },
            warnings=warnings,
            risk_level=RiskLevel.MEDIUM if enabled else RiskLevel.HIGH,
        )

    def dry_run_set_enabled_state(self, *, project_id: ProjectId, resource_id: str, enabled: bool) -> DryRunResult:
        preview = self.preview_set_enabled_state(project_id=project_id, resource_id=resource_id, enabled=enabled)
        valid = True
        if not enabled and any("enabled dependent" in warning.lower() for warning in preview.warnings):
            valid = False
        return DryRunResult(preview.command_type, valid, preview.preview, preview.warnings)

    def execute_set_enabled_state(
        self,
        *,
        project_id: ProjectId,
        resource_id: str,
        enabled: bool,
        idempotency_key: str | None = None,
    ) -> CommandExecutionResult:
        dry_run = self.dry_run_set_enabled_state(project_id=project_id, resource_id=resource_id, enabled=enabled)
        if not dry_run.valid:
            raise ResourceLifecycleError(ErrorCode.PRECONDITION_FAILED, "Cannot disable resource with enabled dependents")
        preview = self.preview_set_enabled_state(project_id=project_id, resource_id=resource_id, enabled=enabled)
        record = self._get_resource(project_id, resource_id)
        server_cfg = self._server_cfg_binding(project_id)
        proposed_content = server_cfg["content"]
        if enabled:
            proposed_content, _ = add_ensure_line(
                proposed_content,
                record.resource_name,
                dependency_names=self._resources.get_resource_dependencies(project_id, resource_id),
            )
        else:
            proposed_content = remove_ensure_line(proposed_content, record.resource_name)
        compensation = self._write_server_cfg(server_cfg["absolute_path"], proposed_content)
        now = datetime.now(UTC)
        new_state = EnabledState.ENABLED.value if enabled else EnabledState.DISABLED.value
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(ResourceRepository)
            prior_state = record.enabled_state
            record.enabled_state = new_state
            record.startup_order = (
                list_ensure_lines(proposed_content).index(record.resource_name) + 1
                if enabled and record.resource_name in list_ensure_lines(proposed_content)
                else None
            )
            record.updated_at = now.isoformat()
            execution = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="Resource",
                entity_id=record.resource_id,
                summary=f"Set {record.resource_name} enabled={enabled}",
                result={"project_id": str(project_id), "resource_id": resource_id, "enabled_state": new_state},
                events=[resource_enabled_state_changed(project_id, resource_id, new_state)],
                undo_plan=UndoPlan(
                    "UndoSetResourceEnabledState",
                    f"Restore server.cfg for {record.resource_name}",
                    compensation,
                    {**compensation_to_storage(compensation), "project_id": str(project_id)},
                ),
                idempotency_key=idempotency_key,
            )
            repository.add_state_change(
                state_change_id=StableIdentifier.new(),
                resource_id=record.resource_id,
                change_type="enable" if enabled else "disable",
                from_state=prior_state,
                to_state=new_state,
                command_execution_id=str(execution.command_execution_id),
                changed_at=now,
                details={},
            )
            uow.commit()
        return execution

    def preview_delete_resource(self, *, project_id: ProjectId, resource_id: str) -> CommandPreview:
        record = self._get_resource(project_id, resource_id)
        server_cfg = self._server_cfg_binding(project_id)
        proposed = remove_ensure_line(server_cfg["content"], record.resource_name)
        warnings = self._enabled_dependent_warnings(project_id, resource_id)
        target_path = self._absolute_resource_path(project_id, record)
        reversible = Path(target_path).exists()
        if not reversible:
            warnings.append("Resource files are missing; undo cannot restore deleted files.")
        config_preview = self._config_service().preview_plan_config_change(
            project_id=project_id,
            config_file_id=server_cfg["config_file_id"],
            proposed_content=proposed,
        )
        return CommandPreview(
            "DeleteResource",
            f"Delete resource {record.resource_name}",
            {
                "project_id": str(project_id),
                "resource_id": resource_id,
                "resource_name": record.resource_name,
                "target_path": target_path,
                "reversible": reversible,
                "server_cfg_diff": config_preview.preview.get("diff"),
            },
            warnings=warnings,
            risk_level=RiskLevel.DESTRUCTIVE,
        )

    def dry_run_delete_resource(self, *, project_id: ProjectId, resource_id: str) -> DryRunResult:
        preview = self.preview_delete_resource(project_id=project_id, resource_id=resource_id)
        valid = not any("enabled dependent" in warning.lower() for warning in preview.warnings)
        return DryRunResult(preview.command_type, valid, preview.preview, preview.warnings)

    def execute_delete_resource(
        self,
        *,
        project_id: ProjectId,
        resource_id: str,
        idempotency_key: str | None = None,
    ) -> CommandExecutionResult:
        dry_run = self.dry_run_delete_resource(project_id=project_id, resource_id=resource_id)
        if not dry_run.valid:
            raise ResourceLifecycleError(ErrorCode.PRECONDITION_FAILED, "Cannot delete resource with enabled dependents")
        preview = self.preview_delete_resource(project_id=project_id, resource_id=resource_id)
        record = self._get_resource(project_id, resource_id)
        target_path = Path(self._absolute_resource_path(project_id, record))
        snapshot_path = self._snapshot_path(project_id, StableIdentifier.new().value)
        compensations: list[Any] = []
        if target_path.exists():
            shutil.copytree(target_path, snapshot_path)
            compensations.append(RestorePathFromSnapshotCompensation(str(snapshot_path), str(target_path)))
            self._filesystem.remove_path(target_path)
        server_cfg = self._server_cfg_binding(project_id)
        proposed = remove_ensure_line(server_cfg["content"], record.resource_name)
        config_compensation = self._write_server_cfg(server_cfg["absolute_path"], proposed)
        compensations.append(config_compensation)
        composite = CompositeCompensation(tuple(compensations))
        now = datetime.now(UTC)
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(ResourceRepository)
            # Do not add a state change because the resource and its state changes will be physically deleted,
            # which would cause a foreign key constraint violation on flush.
            # The deletion is still fully audited via the CommandExecutionRecord and AuditEventRecord.
            resource_name = record.resource_name
            repository.delete_resource(project_id, record.resource_id)
            execution = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="Resource",
                entity_id=resource_id,
                summary=f"Deleted resource {resource_name}",
                result={"project_id": str(project_id), "resource_id": resource_id, "resource_name": resource_name},
                events=[
                    resource_deleted(project_id, resource_id, resource_name),
                    resource_inventory_changed(project_id, 0, 1, 0),
                ],
                undo_plan=UndoPlan(
                    "UndoDeleteResource",
                    f"Restore deleted resource {resource_name}",
                    composite,
                    {**compensation_to_storage(composite), "project_id": str(project_id)},
                    warnings=[] if preview.preview["reversible"] else ["File restore may be incomplete."],
                ),
                idempotency_key=idempotency_key,
            )
            uow.commit()
        return execution

    def undo(self, undo_plan: UndoPlan) -> CommandExecutionResult:
        project_id_value = undo_plan.payload.get("project_id")
        project_id = ProjectId(project_id_value) if project_id_value else None
        preview = CommandPreview(undo_plan.command_type, undo_plan.summary, {"undo": undo_plan.payload}, risk_level=RiskLevel.HIGH)
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            action_result = undo_plan.action.apply(CommandContext(uow=uow))
            execution = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="ResourceUndo",
                entity_id=None,
                summary=undo_plan.summary,
                result=action_result,
                events=[],
                undo_plan=None,
            )
            uow.commit()
        return execution

    def _resolve_install_target(
        self,
        project_id: ProjectId,
        source: InstallSource,
        resource_name: str | None,
        existing_path: Path | None = None,
    ) -> tuple[dict[str, Any], str, Path, list[str]]:
        warnings: list[str] = []
        resources_root = self._resources_root(project_id)
        if source.source_type == "git":
            target_name = resource_name or Path(source.source_uri.rstrip("/")).name.replace(".git", "")
            target_path = existing_path or (resources_root / target_name)
            manifest_info = {
                "resource_name": target_name,
                "version": None,
                "dependencies": [],
                "manifest_valid": True,
                "errors": [],
            }
            warnings.append("Manifest details for git sources are resolved at execute time.")
            return manifest_info, target_name, target_path, warnings
        source_path = Path(source.source_uri).expanduser().resolve()
        if source.source_type == "zip":
            temp_parent = resources_root.parent / ".atlas-preview"
            temp_parent.mkdir(parents=True, exist_ok=True)
            extract_dir = temp_parent / "preview"
            if extract_dir.exists():
                shutil.rmtree(extract_dir)
            self._filesystem.extract_zip(source_path, extract_dir)
            discovered = self._scanner.discover_resources([extract_dir])
            shutil.rmtree(temp_parent, ignore_errors=True)
        elif _is_resource_dir(source_path):
            discovered = self._scanner.discover_resources([source_path.parent])
            discovered = [item for item in discovered if Path(item.absolute_path).resolve() == source_path.resolve()]
        else:
            discovered = self._scanner.discover_resources([source_path])
        if not discovered:
            raise ResourceLifecycleError(ErrorCode.VALIDATION_FAILED, "No valid resource manifest found at source")
        item = discovered[0]
        target_name = resource_name or item.resource_name
        target_path = existing_path or (resources_root / target_name)
        manifest_info = {
            "resource_name": target_name,
            "version": item.manifest.version,
            "dependencies": list(item.manifest.dependencies),
            "manifest_valid": item.manifest.manifest_valid,
            "errors": item.manifest.errors,
        }
        return manifest_info, target_name, target_path, warnings

    def _materialize_install_source(
        self,
        project_id: ProjectId,
        source: InstallSource,
        target_path: Path,
        operation_id: str,
        *,
        replace: bool = False,
    ) -> None:
        if replace and target_path.exists():
            self._filesystem.remove_path(target_path)
        if source.source_type == "git":
            self._publish_progress(project_id, operation_id, "Starting clone", 0, None)
            self._git_provider.clone(
                remote_url=source.source_uri,
                destination=target_path,
                progress=lambda update: self._publish_progress(
                    project_id,
                    operation_id,
                    update.get("message", "Cloning"),
                    update.get("bytes_received"),
                    update.get("total_bytes"),
                ),
            )
            self._publish_progress(project_id, operation_id, "Clone complete", None, None)
            return
        if source.source_type == "zip":
            self._publish_progress(project_id, operation_id, "Extracting archive", 0, None)
            temp_parent = target_path.parent / f".atlas-extract-{operation_id}"
            if temp_parent.exists():
                self._filesystem.remove_path(temp_parent)
            self._filesystem.extract_zip(Path(source.source_uri), temp_parent)
            extracted_root = next(path for path in temp_parent.iterdir() if path.is_dir())
            if target_path.exists():
                self._filesystem.remove_path(target_path)
            shutil.move(str(extracted_root), str(target_path))
            self._filesystem.remove_path(temp_parent)
            self._publish_progress(project_id, operation_id, "Extract complete", None, None)
            return
        source_path = Path(source.source_uri).expanduser().resolve()
        if source_path.resolve() == target_path.resolve():
            return
        shutil.copytree(source_path, target_path)

    def _validate_install_source(self, source: InstallSource) -> bool:
        if source.source_type == "git":
            return bool(source.source_uri)
        path = Path(source.source_uri)
        return path.exists()

    def _write_server_cfg(self, absolute_path: str, proposed_content: str) -> RestoreConfigFileCompensation:
        prior_content = self._filesystem.read_text(Path(absolute_path))
        self._filesystem.write_text(Path(absolute_path), proposed_content)
        return RestoreConfigFileCompensation(absolute_path, prior_content, self._filesystem)

    def _server_cfg_binding(self, project_id: ProjectId) -> dict[str, Any]:
        config_service = self._config_service()
        files = config_service.list_config_files(project_id)
        server_cfg = next((item for item in files if item["path"].endswith("server.cfg")), None)
        if server_cfg is None:
            raise ResourceLifecycleError(ErrorCode.NOT_FOUND, "server.cfg not found for project")
        view = config_service.get_config_file_view(project_id, server_cfg["config_file_id"])
        return {
            "config_file_id": server_cfg["config_file_id"],
            "absolute_path": view["absolute_path"],
            "content": view.get("content") or "",
        }

    def _config_service(self):
        return self._container.create_config_service()

    def _resources_root(self, project_id: ProjectId) -> Path:
        roots = self._resources._resource_roots(project_id)
        if not roots:
            raise ResourceLifecycleError(ErrorCode.NOT_FOUND, "Project resources directory not found")
        return Path(roots[0])

    def _absolute_resource_path(self, project_id: ProjectId, record: Any) -> str:
        return str(self._resources_root(project_id) / record.relative_path)

    def _snapshot_path(self, project_id: ProjectId, token: str) -> Path:
        path = self._resources_root(project_id).parent / ".atlas-snapshots" / token
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _source_path(self, source: InstallSource) -> Path:
        return Path(source.source_uri).expanduser().resolve()

    def _existing_by_name(self, project_id: ProjectId, resource_name: str):
        with self._container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext

            return ResourceRepository(RepositoryContext(session=session, project_id=project_id)).get_resource_by_name(
                project_id, resource_name
            )

    def _get_resource(self, project_id: ProjectId, resource_id: str):
        return self._resources._get_resource(project_id, resource_id)

    def _require_project(self, repository: ProjectRepository, project_id: ProjectId) -> None:
        if repository.get_project(project_id) is None:
            raise ResourceLifecycleError(ErrorCode.NOT_FOUND, f"Project not found: {project_id}")

    def _missing_dependency_warnings(self, project_id: ProjectId, dependencies: list[str]) -> list[str]:
        warnings: list[str] = []
        known = {item["resource_name"] for item in self._resources.list_resources(project_id)}
        for dependency in dependencies:
            if dependency not in known:
                warnings.append(f"Declared dependency '{dependency}' is not present in inventory.")
        return warnings

    def _enabled_dependent_warnings(self, project_id: ProjectId, resource_id: str) -> list[str]:
        server_cfg = self._server_cfg_binding(project_id)
        enabled_map = self._scanner.parse_server_cfg_enabled(server_cfg["content"])
        dependents = self._resources.get_resource_dependents(project_id, resource_id, transitive=False)
        enabled_dependents = [name for name in dependents if enabled_map.get(name)]
        if not enabled_dependents:
            return []
        joined = ", ".join(enabled_dependents)
        return [f"Enabled dependent resources rely on this resource: {joined}"]

    def _publish_progress(
        self,
        project_id: ProjectId,
        operation_id: str,
        message: str,
        bytes_received: int | None,
        total_bytes: int | None,
    ) -> None:
        if self._stream_publisher is None:
            return
        self._stream_publisher.publish_operation_progress(
            project_id=project_id,
            operation_id=operation_id,
            message=message,
            bytes_received=bytes_received,
            total_bytes=total_bytes,
        )


def _is_resource_dir(path: Path) -> bool:
    return (path / "fxmanifest.lua").exists() or (path / "__resource.lua").exists()


def _manifest_json(item: Any) -> dict[str, Any]:
    return {
        "manifest_kind": item.manifest_kind,
        "fx_version": item.manifest.fx_version,
        "games": item.manifest.games,
        "version": item.manifest.version,
        "dependencies": item.manifest.dependencies,
        "provides": item.manifest.provides,
        "manifest_valid": item.manifest.manifest_valid,
        "errors": item.manifest.errors,
    }

