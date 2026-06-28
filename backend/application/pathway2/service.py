from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.adapters.config import LocalConfigSecretScanner
from backend.adapters.git import GitPythonProvider, redact_remote_url
from backend.adapters.persistence import AuditRepository, ProjectRepository
from backend.application.commands import CommandContext, CommandExecutionResult, CommandPreview, DryRunResult, RiskLevel, UndoPlan
from backend.application.commands.compensation import CompositeCompensation, RestorePathFromSnapshotCompensation
from backend.application.commands.recorder import CommandAuditRecorder
from backend.application.commands.serialization import compensation_from_storage
from backend.application.config.service import RestoreConfigFileCompensation
from backend.application.pathway2.audit_remediation import validate_undo_snapshots_available
from backend.application.pathway2.compensation import pathway2_audit_undo_payload, pathway2_undo_root, snapshot_config_compensation
from backend.domain.pathway2 import (
    GITIGNORE_OVERLAY_ENTRY,
    OVERLAY_EXAMPLE_FILENAME,
    OVERLAY_FILENAME,
    Pathway2SettingKeys,
    build_normalization_diff,
    build_overlay_example_content,
    build_structure_scorecard,
    find_server_cfg,
    plan_repo_normalization,
    redact_config_text,
    scan_inline_secrets,
)
from backend.domain.pathway2.run_gate import evaluate_pathway2_run_readiness, load_overlay_content
from backend.domain.pathway2.substitution import (
    apply_dev_value_to_overlay,
    build_substitution_diff,
    build_substitution_preview,
    compute_run_gate,
    plan_overlay_substitution,
    slot_preview_for_dev_value,
)
from backend.domain.shared_kernel import ErrorCode, ProjectId, StableIdentifier
from backend.infrastructure.unit_of_work import RepositoryContext


class Pathway2ApplicationError(RuntimeError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


class AdoptApplicationService:
    def __init__(
        self,
        *,
        container: Any,
        filesystem: Any,
        secret_scanner: LocalConfigSecretScanner,
        git_provider: GitPythonProvider,
    ) -> None:
        self._container = container
        self.filesystem = filesystem
        self.secret_scanner = secret_scanner
        self.git_provider = git_provider
        self._recorder = CommandAuditRecorder()

    def preview_adopt_repository(self, *, root_path: Path, remote_url: str | None = None) -> CommandPreview:
        resolved = root_path.expanduser().resolve()
        warnings: list[str] = []
        if remote_url and resolved.exists() and any(resolved.iterdir()):
            warnings.append("Destination exists and is not empty; clone may fail.")
        server_cfg = find_server_cfg(resolved)
        content = self.filesystem.read_text(server_cfg) if server_cfg else None
        scorecard = build_structure_scorecard(root=resolved, server_cfg_content=content)
        if not scorecard["looks_like_fivem_server"]:
            warnings.append("Path does not look like a FiveM server yet; import may still proceed after clone.")
        return CommandPreview(
            "AdoptRepository",
            f"Adopt FiveM repository at {resolved}",
            {
                "root_path": str(resolved),
                "remote_url": redact_remote_url(remote_url) if remote_url else None,
                "structure_scorecard": scorecard,
            },
            warnings=warnings,
            risk_level=RiskLevel.MEDIUM,
        )

    def dry_run_adopt_repository(self, *, root_path: Path, remote_url: str | None = None) -> DryRunResult:
        preview = self.preview_adopt_repository(root_path=root_path, remote_url=remote_url)
        warnings = list(preview.warnings)
        valid = True
        if remote_url:
            try:
                refs = self.git_provider.ls_remote(remote_url=remote_url)
                if not refs:
                    warnings.append("Remote reachable but returned no refs.")
            except RuntimeError as error:
                valid = False
                warnings.append(str(error))
        return DryRunResult(preview.command_type, valid, preview.preview, warnings)

    def execute_adopt_repository(
        self,
        *,
        root_path: Path,
        remote_url: str | None = None,
        idempotency_key: str | None = None,
    ) -> CommandExecutionResult:
        preview = self.preview_adopt_repository(root_path=root_path, remote_url=remote_url)
        resolved = Path(str(preview.preview["root_path"]))
        if remote_url:
            if resolved.exists() and any(resolved.iterdir()):
                raise Pathway2ApplicationError(ErrorCode.VALIDATION_FAILED, "Destination path exists and is not empty")
            resolved.mkdir(parents=True, exist_ok=True)
            self.git_provider.clone(remote_url=remote_url, destination=resolved, progress=None)

        import_result = self._container.create_project_service().execute_import_project(root_path=resolved, idempotency_key=idempotency_key)
        project_id = ProjectId(str(import_result.result["project_id"]))

        config_service = self._container.create_config_service()
        resource_service = self._container.create_resource_service()
        git_service = self._container.create_git_service()

        config_service.execute_rescan_config_files(project_id=project_id)
        resource_scan = resource_service.execute_rescan_resources(project_id=project_id)
        git_service.execute_discover_git_repositories(project_id=project_id)

        project_root = self._project_root(project_id)
        server_cfg = find_server_cfg(project_root) if project_root else None
        server_cfg_content = self.filesystem.read_text(server_cfg) if server_cfg else None
        git_remote = self._primary_git_remote(project_id)
        scorecard = build_structure_scorecard(
            root=project_root or resolved,
            server_cfg_content=server_cfg_content,
            git_remote_redacted=git_remote,
            resource_count=resource_scan.get("total"),
        )
        inline_secrets = self._scan_repo_secrets(project_root or resolved, server_cfg)

        settings_patch = {
            Pathway2SettingKeys.ORIGIN: "adopted_clone" if remote_url else "adopted_local",
            Pathway2SettingKeys.NORMALIZED: False,
            Pathway2SettingKeys.SECRETS_SUBSTITUTED: False,
            Pathway2SettingKeys.RUN_READY: False,
            Pathway2SettingKeys.SERVER_CFG_PATH: scorecard.get("server_cfg_path"),
            Pathway2SettingKeys.OVERLAY_PATH: OVERLAY_FILENAME,
            Pathway2SettingKeys.REMOTE_URL_REDACTED: redact_remote_url(remote_url) if remote_url else None,
        }
        self._container.create_project_service().update_project_settings(project_id=project_id, patch=settings_patch)

        adopt_preview = CommandPreview(
            "AdoptRepository",
            preview.summary,
            {
                **preview.preview,
                "project_id": str(project_id),
                "structure_scorecard": scorecard,
                "inline_secrets": inline_secrets,
                "pathway2_state": _pathway2_state(settings_patch),
                "run_blocked_reason": "Dev secrets not yet set — complete P2-2 substitution before running.",
            },
            warnings=preview.warnings,
            risk_level=RiskLevel.MEDIUM,
        )
        return CommandExecutionResult(
            command_type=adopt_preview.command_type,
            command_plan_id=import_result.command_plan_id,
            command_execution_id=import_result.command_execution_id,
            audit_ref=import_result.audit_ref,
            result=adopt_preview.preview,
            undo_plan=import_result.undo_plan,
            project_id=project_id,
        )

    def get_adopt_status(self, project_id: ProjectId) -> dict[str, Any]:
        project_root = self._project_root(project_id)
        if project_root is None:
            raise Pathway2ApplicationError(ErrorCode.NOT_FOUND, f"Project root not found: {project_id}")
        settings = self._pathway2_settings(project_id)
        server_cfg = find_server_cfg(project_root)
        server_cfg_content = self.filesystem.read_text(server_cfg) if server_cfg else None
        git_remote = self._primary_git_remote(project_id)
        resource_count = len(self._container.create_resource_service().list_resources(project_id))
        scorecard = build_structure_scorecard(
            root=project_root,
            server_cfg_content=server_cfg_content,
            git_remote_redacted=git_remote,
            resource_count=resource_count,
        )
        inline_secrets = self._scan_repo_secrets(project_root, server_cfg)
        state = _pathway2_state(settings)
        overlay_content = load_overlay_content(self.filesystem, project_root)
        run_ready, run_blocked_reason = evaluate_pathway2_run_readiness(settings=settings, overlay_content=overlay_content)
        state["run_ready"] = run_ready
        substitution_slots = settings.get(Pathway2SettingKeys.SUBSTITUTION_SLOTS, [])
        if not substitution_slots and settings.get(Pathway2SettingKeys.NORMALIZED) and overlay_content:
            _, slots, _ = plan_overlay_substitution(overlay_content)
            substitution_slots = build_substitution_preview(slots)
        unset_dev_slots = settings.get(Pathway2SettingKeys.UNSET_DEV_SLOTS, [])
        if not unset_dev_slots and substitution_slots:
            _, unset_dev_slots = compute_run_gate(overlay_content)
        return {
            "project_id": str(project_id),
            "structure_scorecard": scorecard,
            "inline_secrets": inline_secrets,
            "pathway2_state": state,
            "substitution_slots": substitution_slots,
            "unset_dev_slots": unset_dev_slots,
            "run_blocked_reason": run_blocked_reason,
        }

    def preview_repo_normalization(self, *, project_id: ProjectId) -> CommandPreview:
        server_cfg, rel_path, current = self._load_server_cfg(project_id)
        normalized_base, overlay_content, meta = plan_repo_normalization(current)
        diff = build_normalization_diff(current=current, proposed=normalized_base, path=rel_path)
        overlay_diff = redact_config_text(overlay_content)
        inline_secrets = scan_inline_secrets(path=rel_path, content=current, scanner=self.secret_scanner)
        warnings: list[str] = []
        if meta["secrets_placeholderized"] == 0 and not meta["endpoints_moved"]:
            warnings.append("No inline secrets or endpoints detected to relocate; exec trailer will still be appended if missing.")
        return CommandPreview(
            "PlanRepoNormalization",
            f"Normalize {rel_path} for Pathway 2 overlay structure",
            {
                "project_id": str(project_id),
                "server_cfg_path": rel_path,
                "diff": diff,
                "overlay_preview": overlay_diff,
                "overlay_path": OVERLAY_FILENAME,
                "inline_secrets": inline_secrets,
                "normalization": meta,
                "gitignore_entry": GITIGNORE_OVERLAY_ENTRY,
            },
            warnings=warnings,
            risk_level=RiskLevel.HIGH,
        )

    def dry_run_repo_normalization(self, *, project_id: ProjectId) -> DryRunResult:
        preview = self.preview_repo_normalization(project_id=project_id)
        server_cfg = find_server_cfg(self._require_project_root(project_id))
        if server_cfg is None:
            return DryRunResult(preview.command_type, False, preview.preview, ["server.cfg not found"])
        return DryRunResult(preview.command_type, True, preview.preview, preview.warnings)

    def execute_apply_repo_normalization(self, *, project_id: ProjectId, idempotency_key: str | None = None) -> CommandExecutionResult:
        preview = self.preview_repo_normalization(project_id=project_id)
        dry_run = self.dry_run_repo_normalization(project_id=project_id)
        if not dry_run.valid:
            raise Pathway2ApplicationError(ErrorCode.VALIDATION_FAILED, "Repository normalization preconditions failed")

        server_cfg, rel_path, current = self._load_server_cfg(project_id)
        normalized_base, overlay_content, meta = plan_repo_normalization(current)
        project_root = self._require_project_root(project_id)
        overlay_path = server_cfg.parent / OVERLAY_FILENAME
        example_path = server_cfg.parent / OVERLAY_EXAMPLE_FILENAME
        gitignore_path = project_root / ".gitignore"

        prior_server_cfg = current
        prior_overlay = self.filesystem.read_text(overlay_path)
        prior_example = self.filesystem.read_text(example_path)
        prior_gitignore = self.filesystem.read_text(gitignore_path)

        new_gitignore, gitignore_changed = _ensure_gitignore_entry(prior_gitignore, GITIGNORE_OVERLAY_ENTRY)
        example_content = build_overlay_example_content()

        self.filesystem.write_text(server_cfg, normalized_base)
        self.filesystem.write_text(overlay_path, overlay_content)
        self.filesystem.write_text(example_path, example_content)
        if gitignore_changed:
            self.filesystem.write_text(gitignore_path, new_gitignore)

        compensations: list[RestoreConfigFileCompensation | RestorePathFromSnapshotCompensation] = []
        undo_root = pathway2_undo_root(self._container.app_data_dir, project_id)
        compensations.append(
            snapshot_config_compensation(
                undo_root=undo_root,
                absolute_path=server_cfg,
                prior_content=prior_server_cfg,
                filesystem=self.filesystem,
            )
        )
        compensations.append(
            snapshot_config_compensation(
                undo_root=undo_root,
                absolute_path=overlay_path,
                prior_content=prior_overlay,
                filesystem=self.filesystem,
            )
        )
        compensations.append(
            snapshot_config_compensation(
                undo_root=undo_root,
                absolute_path=example_path,
                prior_content=prior_example,
                filesystem=self.filesystem,
            )
        )
        if gitignore_changed:
            compensations.append(
                snapshot_config_compensation(
                    undo_root=undo_root,
                    absolute_path=gitignore_path,
                    prior_content=prior_gitignore,
                    filesystem=self.filesystem,
                )
            )
        compensation = CompositeCompensation(tuple(compensations))

        self._container.create_config_service().execute_rescan_config_files(project_id=project_id)

        settings_patch = {
            Pathway2SettingKeys.NORMALIZED: True,
            Pathway2SettingKeys.SECRETS_SUBSTITUTED: False,
            Pathway2SettingKeys.RUN_READY: False,
            Pathway2SettingKeys.SERVER_CFG_PATH: rel_path,
            Pathway2SettingKeys.OVERLAY_PATH: str(overlay_path.relative_to(project_root)).replace("\\", "/"),
        }
        self._container.create_project_service().update_project_settings(project_id=project_id, patch=settings_patch)

        undo_payload = pathway2_audit_undo_payload(compensation, project_id)
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            result = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="Pathway2Normalization",
                entity_id=str(project_id),
                summary=f"Applied Pathway 2 normalization to {rel_path}",
                result={
                    "project_id": str(project_id),
                    "server_cfg_path": rel_path,
                    "overlay_path": settings_patch[Pathway2SettingKeys.OVERLAY_PATH],
                    "normalization": meta,
                    "pathway2_state": _pathway2_state({**self._pathway2_settings(project_id), **settings_patch}),
                    "run_blocked_reason": "Dev secrets not yet set — complete P2-2 substitution before running.",
                    "diff": preview.preview["diff"],
                },
                events=[],
                undo_plan=UndoPlan(
                    "RevertRepoNormalization",
                    f"Restore prior {rel_path} and overlay structure",
                    compensation,
                    undo_payload,
                ),
                idempotency_key=idempotency_key,
            )
            uow.commit()
            return result

    def preview_secret_substitution(self, *, project_id: ProjectId) -> CommandPreview:
        self._require_normalized(project_id)
        overlay_path, current = self._load_overlay(project_id)
        proposed, slots, meta = plan_overlay_substitution(current)
        diff = build_substitution_diff(current=current, proposed=proposed)
        return CommandPreview(
            "PlanSecretSubstitution",
            f"Substitute dev secrets into {OVERLAY_FILENAME}",
            {
                "project_id": str(project_id),
                "overlay_path": str(overlay_path.relative_to(self._require_project_root(project_id))).replace("\\", "/"),
                "diff": diff,
                "slots": build_substitution_preview(slots),
                "substitution": meta,
            },
            warnings=[],
            risk_level=RiskLevel.HIGH,
        )

    def dry_run_secret_substitution(self, *, project_id: ProjectId) -> DryRunResult:
        preview = self.preview_secret_substitution(project_id=project_id)
        return DryRunResult(preview.command_type, bool(preview.preview["slots"]), preview.preview, preview.warnings)

    def execute_apply_secret_substitution(self, *, project_id: ProjectId, idempotency_key: str | None = None) -> CommandExecutionResult:
        preview = self.preview_secret_substitution(project_id=project_id)
        dry_run = self.dry_run_secret_substitution(project_id=project_id)
        if not dry_run.valid:
            raise Pathway2ApplicationError(ErrorCode.VALIDATION_FAILED, "No substitution slots found in overlay")

        overlay_path, prior_overlay = self._load_overlay(project_id)
        proposed, slots, meta = plan_overlay_substitution(prior_overlay)
        self.filesystem.write_text(overlay_path, proposed)

        run_ready, unset = compute_run_gate(proposed)
        settings_patch = {
            Pathway2SettingKeys.SECRETS_SUBSTITUTED: True,
            Pathway2SettingKeys.RUN_READY: run_ready,
            Pathway2SettingKeys.SUBSTITUTION_SLOTS: build_substitution_preview(slots),
            Pathway2SettingKeys.UNSET_DEV_SLOTS: unset,
        }
        self._container.create_project_service().update_project_settings(project_id=project_id, patch=settings_patch)

        undo_root = pathway2_undo_root(self._container.app_data_dir, project_id)
        compensation = snapshot_config_compensation(
            undo_root=undo_root,
            absolute_path=overlay_path,
            prior_content=prior_overlay,
            filesystem=self.filesystem,
        )
        undo_payload = pathway2_audit_undo_payload(compensation, project_id)
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            result = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="Pathway2Substitution",
                entity_id=str(project_id),
                summary=f"Applied secret substitution to {OVERLAY_FILENAME}",
                result={
                    "project_id": str(project_id),
                    "substitution": meta,
                    "pathway2_state": _pathway2_state({**self._pathway2_settings(project_id), **settings_patch}),
                    "run_ready": run_ready,
                    "unset_dev_slots": unset,
                    "diff": preview.preview["diff"],
                },
                events=[],
                undo_plan=UndoPlan(
                    "RevertSecretSubstitution",
                    f"Restore prior {OVERLAY_FILENAME}",
                    compensation,
                    undo_payload,
                ),
                idempotency_key=idempotency_key,
            )
            uow.commit()
            return result

    def preview_apply_dev_secret(self, *, project_id: ProjectId, slot_id: str, dev_value: str) -> CommandPreview:
        self._require_substituted(project_id)
        _, current = self._load_overlay(project_id)
        try:
            proposed = apply_dev_value_to_overlay(overlay_content=current, slot_id=slot_id, dev_value=dev_value)
        except ValueError as error:
            raise Pathway2ApplicationError(ErrorCode.VALIDATION_FAILED, str(error)) from error
        diff = build_substitution_diff(current=current, proposed=proposed)
        return CommandPreview(
            "PlanApplyDevSecret",
            f"Apply dev value for {slot_id}",
            {
                "project_id": str(project_id),
                "slot_id": slot_id,
                "masked_value": slot_preview_for_dev_value(slot_id=slot_id, dev_value=dev_value)["masked_value"],
                "diff": diff,
            },
            risk_level=RiskLevel.HIGH,
        )

    def execute_apply_dev_secret(
        self,
        *,
        project_id: ProjectId,
        slot_id: str,
        dev_value: str,
        idempotency_key: str | None = None,
    ) -> CommandExecutionResult:
        preview = self.preview_apply_dev_secret(project_id=project_id, slot_id=slot_id, dev_value=dev_value)
        overlay_path, prior_overlay = self._load_overlay(project_id)
        proposed = apply_dev_value_to_overlay(overlay_content=prior_overlay, slot_id=slot_id, dev_value=dev_value)
        self.filesystem.write_text(overlay_path, proposed)

        run_ready, unset = compute_run_gate(proposed)
        settings_patch = {
            Pathway2SettingKeys.RUN_READY: run_ready,
            Pathway2SettingKeys.UNSET_DEV_SLOTS: unset,
        }
        self._container.create_project_service().update_project_settings(project_id=project_id, patch=settings_patch)

        undo_root = pathway2_undo_root(self._container.app_data_dir, project_id)
        compensation = snapshot_config_compensation(
            undo_root=undo_root,
            absolute_path=overlay_path,
            prior_content=prior_overlay,
            filesystem=self.filesystem,
        )
        undo_payload = pathway2_audit_undo_payload(compensation, project_id)
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            result = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="Pathway2DevSecret",
                entity_id=slot_id,
                summary=f"Applied dev secret for {slot_id}",
                result={
                    "project_id": str(project_id),
                    "slot_id": slot_id,
                    "masked_value": preview.preview["masked_value"],
                    "run_ready": run_ready,
                    "unset_dev_slots": unset,
                },
                events=[],
                undo_plan=UndoPlan(
                    "RevertDevSecretApply",
                    f"Restore prior overlay before dev secret apply for {slot_id}",
                    compensation,
                    undo_payload,
                ),
                idempotency_key=idempotency_key,
            )
            uow.commit()
            return result

    def undo(self, undo_plan: UndoPlan) -> CommandExecutionResult:
        project_id_value = undo_plan.payload.get("project_id")
        project_id = ProjectId(str(project_id_value)) if project_id_value else None
        snapshot_block = validate_undo_snapshots_available(undo_plan.payload)
        if snapshot_block:
            raise Pathway2ApplicationError(ErrorCode.PRECONDITION_FAILED, snapshot_block)
        preview = CommandPreview(undo_plan.command_type, undo_plan.summary, {"undo": _redact_undo_payload(undo_plan.payload)}, risk_level=RiskLevel.HIGH)
        action = (
            compensation_from_storage(undo_plan.payload, filesystem=self.filesystem)
            if undo_plan.payload.get("action_type") == "composite_compensation"
            else undo_plan.action
        )
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            action_result = action.apply(CommandContext(uow=uow))
            if project_id is not None:
                patch = _undo_settings_patch(undo_plan.command_type, overlay_content=load_overlay_content(self.filesystem, self._require_project_root(project_id)))
                if patch:
                    self._container.create_project_service().update_project_settings(project_id=project_id, patch=patch)
                self._container.create_config_service().execute_rescan_config_files(project_id=project_id)
            result = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="Pathway2Undo",
                entity_id=str(project_id) if project_id else None,
                summary=undo_plan.summary,
                result=action_result,
                events=[],
                undo_plan=None,
            )
            uow.commit()
            return result

    def undo_command_execution(self, command_execution_id: StableIdentifier) -> CommandExecutionResult:
        undo_plan = self._resolve_undo_plan(command_execution_id)
        return self.undo(undo_plan)

    def _resolve_undo_plan(self, command_execution_id: StableIdentifier) -> UndoPlan:
        with self._container.create_unit_of_work() as uow:
            uow.begin()
            try:
                audit_repository = uow.repository(AuditRepository)
                execution = audit_repository.get_command_execution(str(command_execution_id))
                if execution is None:
                    raise Pathway2ApplicationError(ErrorCode.NOT_FOUND, f"Command execution not found: {command_execution_id}")
                if execution.status != "succeeded":
                    raise Pathway2ApplicationError(ErrorCode.PRECONDITION_FAILED, "Command execution did not succeed and cannot be undone")
                audit_event = audit_repository.get_audit_event(execution.audit_event_id) if execution.audit_event_id else None
                if audit_event is None:
                    raise Pathway2ApplicationError(ErrorCode.NOT_FOUND, "Audit record not found for command execution")
                undo_payload = (audit_event.details_json or {}).get("undo")
                if not undo_payload:
                    raise Pathway2ApplicationError(ErrorCode.PRECONDITION_FAILED, "Command execution is not undoable")
                snapshot_block = validate_undo_snapshots_available(undo_payload)
                if snapshot_block:
                    raise Pathway2ApplicationError(ErrorCode.PRECONDITION_FAILED, snapshot_block)
                action = compensation_from_storage(undo_payload, filesystem=self.filesystem)
                return UndoPlan(
                    command_type="RevertRepoNormalization",
                    summary="Restore prior repository normalization",
                    action=action,
                    payload=undo_payload,
                )
            finally:
                uow.rollback()

    def _load_server_cfg(self, project_id: ProjectId) -> tuple[Path, str, str]:
        project_root = self._require_project_root(project_id)
        server_cfg = find_server_cfg(project_root)
        if server_cfg is None:
            raise Pathway2ApplicationError(ErrorCode.NOT_FOUND, "server.cfg not found for project")
        rel_path = str(server_cfg.relative_to(project_root)).replace("\\", "/")
        content = self.filesystem.read_text(server_cfg) or ""
        return server_cfg, rel_path, content

    def _require_project_root(self, project_id: ProjectId) -> Path:
        project_root = self._project_root(project_id)
        if project_root is None:
            raise Pathway2ApplicationError(ErrorCode.NOT_FOUND, f"Project root not found: {project_id}")
        return project_root

    def _project_root(self, project_id: ProjectId) -> Path | None:
        with self._container.session_factory() as session:
            repository = ProjectRepository(RepositoryContext(session=session, project_id=project_id))
            project = repository.get_project(project_id)
            if project is None:
                return None
            for path in repository.list_paths(project_id):
                if path.path_role == "root":
                    return Path(path.absolute_path).resolve()
        return None

    def _pathway2_settings(self, project_id: ProjectId) -> dict[str, Any]:
        settings = self._container.create_project_service().get_project_settings(project_id)
        return {key: value for key, value in settings.items() if key.startswith("pathway2.")}

    def _primary_git_remote(self, project_id: ProjectId) -> str | None:
        repos = self._container.create_git_service().list_git_repositories(project_id)
        if not repos:
            return None
        return repos[0].get("remote_url")

    def _scan_repo_secrets(self, project_root: Path, server_cfg: Path | None) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        if server_cfg and server_cfg.is_file():
            content = self.filesystem.read_text(server_cfg) or ""
            rel = str(server_cfg.relative_to(project_root)).replace("\\", "/")
            findings.extend(scan_inline_secrets(path=rel, content=content, scanner=self.secret_scanner))
        return findings

    def _load_overlay(self, project_id: ProjectId) -> tuple[Path, str]:
        project_root = self._require_project_root(project_id)
        server_cfg = find_server_cfg(project_root)
        if server_cfg is None:
            raise Pathway2ApplicationError(ErrorCode.NOT_FOUND, "server.cfg not found for project")
        overlay_path = server_cfg.parent / OVERLAY_FILENAME
        if not overlay_path.is_file():
            raise Pathway2ApplicationError(ErrorCode.PRECONDITION_FAILED, f"{OVERLAY_FILENAME} not found; complete P2-1 normalization first")
        content = self.filesystem.read_text(overlay_path) or ""
        return overlay_path, content

    def _require_normalized(self, project_id: ProjectId) -> None:
        settings = self._pathway2_settings(project_id)
        if not settings.get(Pathway2SettingKeys.NORMALIZED):
            raise Pathway2ApplicationError(ErrorCode.PRECONDITION_FAILED, "Complete P2-1 normalization before secret substitution")

    def _require_substituted(self, project_id: ProjectId) -> None:
        settings = self._pathway2_settings(project_id)
        if not settings.get(Pathway2SettingKeys.SECRETS_SUBSTITUTED):
            raise Pathway2ApplicationError(ErrorCode.PRECONDITION_FAILED, "Apply P2-2 secret substitution before entering dev secrets")


def _undo_settings_patch(command_type: str, *, overlay_content: str | None) -> dict[str, Any] | None:
    if command_type == "RevertRepoNormalization":
        return {
            Pathway2SettingKeys.NORMALIZED: False,
            Pathway2SettingKeys.SECRETS_SUBSTITUTED: False,
            Pathway2SettingKeys.RUN_READY: False,
            Pathway2SettingKeys.SUBSTITUTION_SLOTS: [],
            Pathway2SettingKeys.UNSET_DEV_SLOTS: [],
        }
    if command_type == "RevertSecretSubstitution":
        return {
            Pathway2SettingKeys.SECRETS_SUBSTITUTED: False,
            Pathway2SettingKeys.RUN_READY: False,
            Pathway2SettingKeys.SUBSTITUTION_SLOTS: [],
            Pathway2SettingKeys.UNSET_DEV_SLOTS: [],
        }
    if command_type == "RevertDevSecretApply":
        run_ready, unset = compute_run_gate(overlay_content or "")
        return {
            Pathway2SettingKeys.RUN_READY: run_ready,
            Pathway2SettingKeys.UNSET_DEV_SLOTS: unset,
        }
    return None


def _ensure_gitignore_entry(prior: str | None, entry: str) -> tuple[str, bool]:
    lines = (prior or "").splitlines()
    if any(line.strip() == entry for line in lines):
        return prior or "", False
    prefix = prior or ""
    if prefix and not prefix.endswith("\n"):
        prefix += "\n"
    return f"{prefix}{entry}\n", True


def _pathway2_state(settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "origin": settings.get(Pathway2SettingKeys.ORIGIN),
        "normalized": bool(settings.get(Pathway2SettingKeys.NORMALIZED)),
        "secrets_substituted": bool(settings.get(Pathway2SettingKeys.SECRETS_SUBSTITUTED)),
        "run_ready": bool(settings.get(Pathway2SettingKeys.RUN_READY)),
        "server_cfg_path": settings.get(Pathway2SettingKeys.SERVER_CFG_PATH),
        "overlay_path": settings.get(Pathway2SettingKeys.OVERLAY_PATH),
    }


def _redact_undo_payload(payload: dict[str, Any]) -> dict[str, Any]:
    redacted = dict(payload)
    if "steps" in redacted:
        redacted["steps"] = [
            {key: ("[stored locally]" if key == "prior_content" else value) for key, value in step.items()}
            for step in redacted["steps"]
        ]
    if "prior_content" in redacted:
        redacted["prior_content"] = "[stored locally]"
    return redacted
