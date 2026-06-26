from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.adapters.persistence import AuditRepository, ProjectRepository
from backend.application.commands import (
    CommandContext,
    CommandExecutionResult,
    CommandPreview,
    CompensatingAction,
    DryRunResult,
    RiskLevel,
    UndoPlan,
)
from backend.application.commands.recorder import CommandAuditRecorder
from backend.domain.project import ProjectStatus, TrustScope, TrustState, slug_from_path
from backend.domain.project.events import (
    environment_profile_created,
    environment_profile_updated,
    project_archived,
    project_imported,
    project_opened,
    project_settings_updated,
    workspace_trust_changed,
)
from backend.domain.project.ports import ProjectFilesystemInspectionPort
from backend.domain.shared_kernel import ErrorCode, ProjectId, StableIdentifier
from backend.infrastructure.unit_of_work import RepositoryContext


class ProjectApplicationError(RuntimeError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ArchiveImportedProjectCompensation:
    project_id: ProjectId
    reason: str = "Undo imported project metadata"
    action_type: str = "archive_imported_project"

    def describe(self) -> dict[str, Any]:
        return {"action_type": self.action_type, "project_id": str(self.project_id), "reason": self.reason}

    def apply(self, context: CommandContext) -> dict[str, Any]:
        repository = context.uow.repository(ProjectRepository)
        archived_at = context.now()
        repository.archive_project(self.project_id, archived_at)
        return {"project_id": str(self.project_id), "status": ProjectStatus.ARCHIVED.value, "archived_at": archived_at.isoformat()}


def rehydrate_compensating_action(payload: dict[str, Any]) -> CompensatingAction:
    action_type = payload.get("action_type")
    if action_type == "archive_imported_project":
        project_id = payload.get("project_id")
        if not project_id:
            raise ProjectApplicationError(ErrorCode.VALIDATION_FAILED, "Stored undo payload is missing project_id")
        return ArchiveImportedProjectCompensation(
            ProjectId(str(project_id)),
            reason=str(payload.get("reason", "Undo imported project metadata")),
        )
    raise ProjectApplicationError(ErrorCode.PRECONDITION_FAILED, f"Command execution is not undoable: unsupported action {action_type!r}")


class ProjectApplicationService:
    def __init__(self, *, container: Any, filesystem_inspector: ProjectFilesystemInspectionPort) -> None:
        self._container = container
        self._filesystem_inspector = filesystem_inspector
        self._recorder = CommandAuditRecorder()

    def preview_import_project(self, root_path: Path, template_id: str | None = None) -> CommandPreview:
        detected_paths = self._inspect_import_root(root_path)
        return CommandPreview(
            command_type="ImportProject",
            summary=f"Import project metadata from {root_path}",
            preview={
                "root_path": str(root_path.expanduser().resolve()),
                "template_id": template_id,
                "detected_paths": [_path_dict(path) for path in detected_paths],
            },
        )

    def dry_run_import_project(self, root_path: Path, template_id: str | None = None) -> DryRunResult:
        preview = self.preview_import_project(root_path, template_id)
        return DryRunResult(
            command_type=preview.command_type,
            valid=True,
            simulation=preview.preview,
            warnings=preview.warnings,
        )

    def execute_import_project(
        self,
        *,
        root_path: Path,
        template_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> CommandExecutionResult:
        preview = self.preview_import_project(root_path, template_id)
        detected_paths = preview.preview["detected_paths"]
        resolved_root = Path(str(preview.preview["root_path"]))
        project_id = ProjectId.new()
        slug = slug_from_path(resolved_root)
        now = datetime.now(UTC)

        with self._container.create_unit_of_work() as uow:
            uow.begin()
            repository = uow.repository(ProjectRepository)
            if repository.slug_exists(slug):
                raise ProjectApplicationError(ErrorCode.CONFLICT, f"Project slug already exists: {slug}")

            repository.add_project(
                project_id=project_id,
                slug=slug,
                display_name=resolved_root.name,
                description=None,
                created_at=now,
            )
            uow.session.flush()
            for path in detected_paths:
                repository.add_path(
                    project_id=project_id,
                    role=str(path["role"]),
                    absolute_path=str(path["absolute_path"]),
                    exists=bool(path["exists"]),
                    created_at=now,
                )
            undo_plan = UndoPlan(
                command_type="UndoImportProject",
                summary="Archive imported project metadata",
                action=ArchiveImportedProjectCompensation(project_id),
                payload=ArchiveImportedProjectCompensation(project_id).describe(),
            )
            event = project_imported(project_id, list(detected_paths))
            result = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="Project",
                entity_id=str(project_id),
                summary=f"Imported project {resolved_root.name}",
                result={"project_id": str(project_id), "detected_paths": detected_paths},
                events=[event],
                undo_plan=undo_plan,
                idempotency_key=idempotency_key,
            )
            uow.commit()
            return result

    def undo(self, undo_plan: UndoPlan) -> CommandExecutionResult:
        project_id_value = undo_plan.payload.get("project_id")
        project_id = ProjectId(str(project_id_value)) if project_id_value else None
        preview = CommandPreview(
            command_type=undo_plan.command_type,
            summary=undo_plan.summary,
            preview={"undo": undo_plan.payload},
            risk_level=RiskLevel.MEDIUM,
        )
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            action_result = undo_plan.action.apply(CommandContext(uow=uow))
            events = [project_archived(project_id, str(action_result.get("reason", undo_plan.summary)))] if project_id else []
            result = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="Project",
                entity_id=str(project_id) if project_id else None,
                summary=undo_plan.summary,
                result=action_result,
                events=events,
                undo_plan=None,
            )
            uow.commit()
            return result

    def undo_command_execution(self, command_execution_id: StableIdentifier) -> CommandExecutionResult:
        undo_plan = self._resolve_undo_plan_from_execution(command_execution_id)
        return self.undo(undo_plan)

    def _resolve_undo_plan_from_execution(self, command_execution_id: StableIdentifier) -> UndoPlan:
        with self._container.create_unit_of_work() as uow:
            uow.begin()
            try:
                audit_repository = uow.repository(AuditRepository)
                execution = audit_repository.get_command_execution(str(command_execution_id))
                if execution is None:
                    raise ProjectApplicationError(
                        ErrorCode.NOT_FOUND,
                        f"Command execution not found: {command_execution_id}",
                    )
                if execution.status != "succeeded":
                    raise ProjectApplicationError(
                        ErrorCode.PRECONDITION_FAILED,
                        f"Command execution {command_execution_id} did not succeed and cannot be undone",
                    )

                result_json = execution.result_json or {}
                original_command_type = result_json.get("command_type")
                if original_command_type == "UndoImportProject":
                    raise ProjectApplicationError(
                        ErrorCode.PRECONDITION_FAILED,
                        "Undo commands cannot be undone through this endpoint",
                    )

                if not execution.audit_event_id:
                    raise ProjectApplicationError(
                        ErrorCode.PRECONDITION_FAILED,
                        f"Command execution {command_execution_id} has no audit record and is not undoable",
                    )

                audit_event = audit_repository.get_audit_event(execution.audit_event_id)
                if audit_event is None:
                    raise ProjectApplicationError(
                        ErrorCode.NOT_FOUND,
                        f"Audit record not found for command execution: {command_execution_id}",
                    )

                undo_payload = (audit_event.details_json or {}).get("undo")
                if not undo_payload:
                    raise ProjectApplicationError(
                        ErrorCode.PRECONDITION_FAILED,
                        f"Command execution {command_execution_id} is not undoable",
                    )

                if execution.project_id and execution.started_at:
                    if audit_repository.has_undo_execution_since(
                        project_id=execution.project_id,
                        since_started_at=execution.started_at,
                        undo_command_type="UndoImportProject",
                    ):
                        raise ProjectApplicationError(
                            ErrorCode.CONFLICT,
                            f"Command execution {command_execution_id} was already undone",
                        )

                action = rehydrate_compensating_action(undo_payload)
                return UndoPlan(
                    command_type="UndoImportProject",
                    summary=str(undo_payload.get("reason", "Undo prior command")),
                    action=action,
                    payload=undo_payload,
                )
            finally:
                uow.rollback()

    def open_project(self, project_id: ProjectId) -> CommandExecutionResult:
        preview = CommandPreview("OpenProject", "Open project and update last_opened_at", {"project_id": str(project_id)})
        opened_at = datetime.now(UTC)
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(ProjectRepository)
            project = repository.get_project(project_id)
            if project is None:
                raise ProjectApplicationError(ErrorCode.NOT_FOUND, f"Project not found: {project_id}")
            repository.mark_opened(project_id, opened_at)
            result = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="Project",
                entity_id=str(project_id),
                summary=f"Opened project {project.display_name}",
                result={"project_id": str(project_id), "last_opened_at": opened_at.isoformat()},
                events=[project_opened(project_id)],
            )
            uow.commit()
            return result

    def archive_project(self, project_id: ProjectId, reason: str) -> CommandExecutionResult:
        if not reason.strip():
            raise ProjectApplicationError(ErrorCode.VALIDATION_FAILED, "archive reason cannot be empty")
        preview = CommandPreview("ArchiveProject", "Archive project metadata without deleting files", {"project_id": str(project_id), "reason": reason})
        archived_at = datetime.now(UTC)
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(ProjectRepository)
            self._require_project(repository, project_id)
            repository.archive_project(project_id, archived_at)
            result = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="Project",
                entity_id=str(project_id),
                summary=f"Archived project: {reason}",
                result={"project_id": str(project_id), "status": ProjectStatus.ARCHIVED.value, "reason": reason},
                events=[project_archived(project_id, reason)],
            )
            uow.commit()
            return result

    def update_project_settings(
        self,
        *,
        project_id: ProjectId,
        patch: dict[str, Any],
        expected_version: str | None = None,
    ) -> CommandExecutionResult:
        if not patch:
            raise ProjectApplicationError(ErrorCode.VALIDATION_FAILED, "settings patch cannot be empty")
        current_version = self.settings_revision(project_id)
        if expected_version is not None and expected_version != current_version:
            raise ProjectApplicationError(ErrorCode.CONFLICT, "project settings version changed")

        preview = CommandPreview("UpdateProjectSettings", "Update project settings", {"project_id": str(project_id), "patch": patch})
        now = datetime.now(UTC)
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(ProjectRepository)
            self._require_project(repository, project_id)
            changed_keys = repository.upsert_settings(project_id=project_id, patch=patch, updated_at=now)
            result = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="Project",
                entity_id=str(project_id),
                summary="Updated project settings",
                result={"project_id": str(project_id), "changed_keys": changed_keys, "version": now.isoformat()},
                events=[project_settings_updated(project_id, changed_keys)],
            )
            uow.commit()
            return result

    def create_environment_profile(
        self,
        *,
        project_id: ProjectId,
        name: str,
        display_name: str | None = None,
        settings: dict[str, Any] | None = None,
        artifact_channel: str | None = None,
        is_default: bool = False,
    ) -> CommandExecutionResult:
        if not name.strip():
            raise ProjectApplicationError(ErrorCode.VALIDATION_FAILED, "environment name cannot be empty")
        environment_id = StableIdentifier.new()
        preview = CommandPreview(
            "CreateEnvironmentProfile",
            "Create environment profile",
            {"project_id": str(project_id), "name": name},
        )
        now = datetime.now(UTC)
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(ProjectRepository)
            self._require_project(repository, project_id)
            repository.create_environment(
                project_id=project_id,
                environment_id=environment_id,
                name=name,
                display_name=display_name or name.title(),
                artifact_channel=artifact_channel,
                settings=settings or {},
                is_default=is_default,
                created_at=now,
            )
            result = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="EnvironmentProfile",
                entity_id=str(environment_id),
                summary=f"Created environment profile {name}",
                result={"project_id": str(project_id), "environment_id": str(environment_id), "name": name},
                events=[environment_profile_created(project_id, str(environment_id), name)],
            )
            uow.commit()
            return result

    def update_environment_profile(
        self,
        *,
        project_id: ProjectId,
        environment_id: StableIdentifier,
        display_name: str | None = None,
        artifact_channel: str | None = None,
        settings: dict[str, Any] | None = None,
    ) -> CommandExecutionResult:
        preview = CommandPreview(
            "UpdateEnvironmentProfile",
            "Update environment profile",
            {"project_id": str(project_id), "environment_id": str(environment_id)},
        )
        now = datetime.now(UTC)
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(ProjectRepository)
            self._require_project(repository, project_id)
            profile = repository.update_environment(
                project_id=project_id,
                environment_id=environment_id,
                display_name=display_name,
                artifact_channel=artifact_channel,
                settings=settings,
                updated_at=now,
            )
            if profile is None:
                raise ProjectApplicationError(ErrorCode.NOT_FOUND, f"Environment profile not found: {environment_id}")
            result = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="EnvironmentProfile",
                entity_id=str(environment_id),
                summary=f"Updated environment profile {profile.name}",
                result={"project_id": str(project_id), "environment_id": str(environment_id)},
                events=[environment_profile_updated(project_id, str(environment_id))],
            )
            uow.commit()
            return result

    def record_workspace_trust_decision(
        self,
        *,
        project_id: ProjectId,
        scope: str,
        trust_state: str,
        scope_ref: str | None = None,
        reason: str | None = None,
        decided_by: str | None = None,
    ) -> CommandExecutionResult:
        if scope not in {item.value for item in TrustScope}:
            raise ProjectApplicationError(ErrorCode.VALIDATION_FAILED, f"Invalid trust scope: {scope}")
        if trust_state not in {item.value for item in TrustState}:
            raise ProjectApplicationError(ErrorCode.VALIDATION_FAILED, f"Invalid trust state: {trust_state}")
        trust_decision_id = StableIdentifier.new()
        preview = CommandPreview(
            "RecordWorkspaceTrustDecision",
            "Record workspace trust decision",
            {"project_id": str(project_id), "scope": scope, "trust_state": trust_state},
        )
        now = datetime.now(UTC)
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(ProjectRepository)
            self._require_project(repository, project_id)
            actual_id = repository.upsert_trust_decision(
                project_id=project_id,
                trust_decision_id=trust_decision_id,
                trust_state=trust_state,
                scope=scope,
                scope_ref=scope_ref,
                reason=reason,
                decided_at=now,
                decided_by=decided_by,
            )
            result = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="WorkspaceTrustDecision",
                entity_id=str(actual_id),
                summary="Recorded workspace trust decision",
                result={"project_id": str(project_id), "trust_decision_id": str(actual_id)},
                events=[workspace_trust_changed(project_id, scope, trust_state)],
            )
            uow.commit()
            return result

    def list_projects(self) -> list[dict[str, Any]]:
        with self._container.session_factory() as session:
            repository = ProjectRepository(RepositoryContext(session=session))
            return [_project_summary(project) for project in repository.list_projects()]

    def get_project(self, project_id: ProjectId) -> dict[str, Any]:
        with self._container.session_factory() as session:
            repository = ProjectRepository(RepositoryContext(session=session, project_id=project_id))
            project = repository.get_project()
            if project is None:
                raise ProjectApplicationError(ErrorCode.NOT_FOUND, f"Project not found: {project_id}")
            return {
                **_project_summary(project),
                "paths": [_path_record(path) for path in repository.list_paths()],
                "default_environment_id": project.default_environment_id,
            }

    def list_environment_profiles(self, project_id: ProjectId) -> list[dict[str, Any]]:
        with self._container.session_factory() as session:
            repository = ProjectRepository(RepositoryContext(session=session, project_id=project_id))
            self._require_project(repository, project_id)
            return [_environment_record(profile) for profile in repository.list_environments()]

    def get_project_settings(self, project_id: ProjectId, keys: list[str] | None = None) -> dict[str, Any]:
        with self._container.session_factory() as session:
            repository = ProjectRepository(RepositoryContext(session=session, project_id=project_id))
            self._require_project(repository, project_id)
            return {setting.setting_key: setting.value_json for setting in repository.list_settings(keys=keys)}

    def settings_revision(self, project_id: ProjectId) -> str:
        with self._container.session_factory() as session:
            repository = ProjectRepository(RepositoryContext(session=session, project_id=project_id))
            settings = repository.list_settings()
            return max((setting.updated_at for setting in settings), default="0")

    def list_trust_decisions(self, project_id: ProjectId) -> list[dict[str, Any]]:
        with self._container.session_factory() as session:
            repository = ProjectRepository(RepositoryContext(session=session, project_id=project_id))
            self._require_project(repository, project_id)
            return [_trust_record(decision) for decision in repository.list_trust_decisions()]

    def list_project_templates(self) -> list[dict[str, Any]]:
        with self._container.session_factory() as session:
            repository = ProjectRepository(RepositoryContext(session=session))
            return [
                {
                    "template_id": template.template_id,
                    "template_slug": template.template_slug,
                    "display_name": template.display_name,
                    "source_type": template.source_type,
                    "source_ref": template.source_ref,
                    "template": template.template_json,
                }
                for template in repository.list_templates()
            ]

    def _inspect_import_root(self, root_path: Path) -> list[Any]:
        resolved = root_path.expanduser().resolve()
        if not resolved.exists() or not resolved.is_dir():
            raise ProjectApplicationError(ErrorCode.VALIDATION_FAILED, f"Project root does not exist: {resolved}")
        return self._filesystem_inspector.inspect_root(resolved)

    def _require_project(self, repository: ProjectRepository, project_id: ProjectId) -> None:
        if repository.get_project(project_id) is None:
            raise ProjectApplicationError(ErrorCode.NOT_FOUND, f"Project not found: {project_id}")


def _path_dict(path: Any) -> dict[str, object]:
    return {"role": path.role.value, "absolute_path": path.absolute_path, "exists": path.exists}


def _project_summary(project: Any) -> dict[str, Any]:
    return {
        "project_id": project.project_id,
        "slug": project.slug,
        "display_name": project.display_name,
        "description": project.description,
        "status": project.status,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
        "last_opened_at": project.last_opened_at,
    }


def _path_record(path: Any) -> dict[str, Any]:
    return {
        "project_path_id": path.project_path_id,
        "project_id": path.project_id,
        "path_role": path.path_role,
        "absolute_path": path.absolute_path,
        "exists_last_checked": bool(path.exists_last_checked),
        "last_checked_at": path.last_checked_at,
    }


def _environment_record(profile: Any) -> dict[str, Any]:
    return {
        "environment_id": profile.environment_id,
        "project_id": profile.project_id,
        "name": profile.name,
        "display_name": profile.display_name,
        "artifact_channel": profile.artifact_channel,
        "settings": profile.settings_json or {},
        "is_default": bool(profile.is_default),
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }


def _trust_record(decision: Any) -> dict[str, Any]:
    return {
        "trust_decision_id": decision.trust_decision_id,
        "project_id": decision.project_id,
        "trust_state": decision.trust_state,
        "scope": decision.scope,
        "scope_ref": decision.scope_ref,
        "reason": decision.reason,
        "decided_at": decision.decided_at,
        "decided_by": decision.decided_by,
    }
