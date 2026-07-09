from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.adapters.config import LocalConfigSecretScanner
from backend.adapters.git import GitPythonProvider, redact_remote_url
from backend.adapters.persistence import AuditRepository, ProjectRepository
from backend.application.config.structural_validation import enrich_validation_payload, run_structural_validation
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
from backend.domain.pathway2.wizard import build_wizard_status
from backend.domain.pathway2.substitution import (
    apply_dev_value_to_overlay,
    build_substitution_diff,
    build_substitution_preview,
    compute_run_gate,
    plan_overlay_substitution,
    slot_preview_for_dev_value,
)
from backend.domain.pathway2.supervisor_fallback import (
    build_plus_set_arguments,
    mask_launch_arguments,
    plus_set_preview,
    resolve_plus_set_overrides,
)
from backend.domain.pathway2.commit_safety import (
    evaluate_commit_safety,
    is_overlay_path,
    load_staged_files,
)
from backend.domain.pathway2.return_grouping import (
    aggregate_return_gate,
    build_repo_return_slice,
    build_unowned_local_entries,
    match_registered_repo,
)
from backend.domain.project.topology import discover_project_repo_topology
from backend.domain.pathway2.transform import DevTransformOptions, build_transform_diff, default_transform_options, plan_dev_config_transform
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
        server_cfg = find_server_cfg(resolved)
        content = self.filesystem.read_text(server_cfg) if server_cfg else None
        scorecard = build_structure_scorecard(root=resolved, server_cfg_content=content)
        config_validation, validation_warnings = self._structural_validation_block(resolved)
        warnings: list[str] = list(validation_warnings)
        if remote_url and resolved.exists() and any(resolved.iterdir()):
            warnings.append("Destination exists and is not empty; clone may fail.")
        if not scorecard["looks_like_fivem_server"]:
            warnings.append("Path does not look like a FiveM server yet; import may still proceed after clone.")
        return CommandPreview(
            "AdoptRepository",
            f"Adopt FiveM repository at {resolved}",
            {
                "root_path": str(resolved),
                "remote_url": redact_remote_url(remote_url) if remote_url else None,
                "structure_scorecard": scorecard,
                "config_validation": config_validation,
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
        resolved = root_path.expanduser().resolve()
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
        config_validation, adopt_validation_warnings = self._structural_validation_block(project_root or resolved, for_response=True)

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
            f"Adopt FiveM repository at {resolved}",
            {
                "root_path": str(resolved),
                "remote_url": redact_remote_url(remote_url) if remote_url else None,
                "project_id": str(project_id),
                "structure_scorecard": scorecard,
                "inline_secrets": inline_secrets,
                "config_validation": config_validation,
                "pathway2_state": _pathway2_state(settings_patch),
                "run_blocked_reason": "Dev secrets not yet set — complete P2-2 substitution before running.",
            },
            warnings=adopt_validation_warnings,
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
        config_validation, _ = self._structural_validation_block(project_root)
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
            "config_validation": config_validation,
            "pathway2_state": state,
            "substitution_slots": substitution_slots,
            "unset_dev_slots": unset_dev_slots,
            "run_blocked_reason": run_blocked_reason,
        }

    def get_wizard_status(self, project_id: ProjectId) -> dict[str, Any]:
        adopt_status = self.get_adopt_status(project_id)
        return_path: dict[str, Any] | None = None
        state = adopt_status.get("pathway2_state") or {}
        if state.get("origin"):
            try:
                return_path = self.get_return_path_status(project_id=project_id)
            except Pathway2ApplicationError:
                return_path = None
        wizard = build_wizard_status(adopt_status=adopt_status, return_path=return_path)
        payload = dict(adopt_status)
        payload["wizard"] = wizard
        if return_path is not None:
            payload["return_path"] = return_path
        return payload

    def preview_repo_normalization(self, *, project_id: ProjectId) -> CommandPreview:
        server_cfg, rel_path, current = self._load_server_cfg(project_id)
        normalized_base, overlay_content, meta = plan_repo_normalization(current)
        diff = build_normalization_diff(current=current, proposed=normalized_base, path=rel_path)
        overlay_diff = redact_config_text(overlay_content)
        inline_secrets = scan_inline_secrets(path=rel_path, content=current, scanner=self.secret_scanner)
        config_validation, validation_warnings = self._structural_validation_block(self._require_project_root(project_id))
        warnings: list[str] = list(validation_warnings)
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
                "config_validation": config_validation,
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
        slots = preview.preview["slots"]
        warnings = list(preview.warnings)
        if not slots:
            warnings.append(
                "No CHANGE_ME placeholders in server.cfg.local. Re-run normalization or add secret placeholders before applying."
            )
            return DryRunResult(preview.command_type, False, preview.preview, warnings)
        return DryRunResult(preview.command_type, True, preview.preview, warnings)

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
        masked_value = slot_preview_for_dev_value(slot_id=slot_id, dev_value=dev_value)["masked_value"]
        stripped = dev_value.strip()
        if stripped and stripped in diff:
            diff = diff.replace(stripped, masked_value)
        return CommandPreview(
            "PlanApplyDevSecret",
            f"Apply dev value for {slot_id}",
            {
                "project_id": str(project_id),
                "slot_id": slot_id,
                "masked_value": masked_value,
                "diff": diff,
            },
            risk_level=RiskLevel.HIGH,
        )

    def dry_run_apply_dev_secret(self, *, project_id: ProjectId, slot_id: str, dev_value: str) -> DryRunResult:
        preview = self.preview_apply_dev_secret(project_id=project_id, slot_id=slot_id, dev_value=dev_value)
        warnings = list(preview.warnings)
        stripped = dev_value.strip()
        if stripped and not stripped.startswith("cfxk_"):
            warnings.append("Dev license keys usually start with cfxk_; continue only if you are sure this value is correct.")
        return DryRunResult(preview.command_type, True, preview.preview, warnings)

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

    def preview_dev_config_transform(
        self,
        *,
        project_id: ProjectId,
        options: DevTransformOptions | None = None,
    ) -> CommandPreview:
        self._require_substituted(project_id)
        overlay_path, current = self._load_overlay(project_id)
        resolved = options or self._default_transform_options(project_id)
        proposed, meta = plan_dev_config_transform(current, resolved)
        diff = build_transform_diff(current=current, proposed=proposed)
        rel_overlay = str(overlay_path.relative_to(self._require_project_root(project_id))).replace("\\", "/")
        base_content = self._base_server_cfg_content(project_id)
        plus_set = resolve_plus_set_overrides(overlay_content=proposed, base_content=base_content)
        return CommandPreview(
            "PlanDevConfigTransform",
            f"Apply dev tuning to {OVERLAY_FILENAME}",
            {
                "project_id": str(project_id),
                "overlay_path": rel_overlay,
                "diff": diff,
                "transform": meta,
                "plus_set_overrides": plus_set_preview(plus_set),
                "plus_set_arguments_masked": mask_launch_arguments(build_plus_set_arguments(plus_set)),
            },
            warnings=[],
            risk_level=RiskLevel.MEDIUM,
        )

    def dry_run_dev_config_transform(self, *, project_id: ProjectId, options: DevTransformOptions | None = None) -> DryRunResult:
        preview = self.preview_dev_config_transform(project_id=project_id, options=options)
        return DryRunResult(preview.command_type, True, preview.preview, preview.warnings)

    def execute_apply_dev_config_transform(
        self,
        *,
        project_id: ProjectId,
        options: DevTransformOptions | None = None,
        idempotency_key: str | None = None,
    ) -> CommandExecutionResult:
        preview = self.preview_dev_config_transform(project_id=project_id, options=options)
        resolved = options or self._default_transform_options(project_id)
        overlay_path, prior_overlay = self._load_overlay(project_id)
        proposed, meta = plan_dev_config_transform(prior_overlay, resolved)
        self.filesystem.write_text(overlay_path, proposed)

        settings_patch = {
            Pathway2SettingKeys.DEV_TRANSFORMED: True,
            Pathway2SettingKeys.TRANSFORM_OPTIONS: meta,
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
                entity_type="Pathway2DevTransform",
                entity_id=str(project_id),
                summary=f"Applied dev config transform to {OVERLAY_FILENAME}",
                result={
                    "project_id": str(project_id),
                    "transform": meta,
                    "pathway2_state": _pathway2_state({**self._pathway2_settings(project_id), **settings_patch}),
                    "diff": preview.preview["diff"],
                    "plus_set_overrides": preview.preview["plus_set_overrides"],
                },
                events=[],
                undo_plan=UndoPlan(
                    "RevertDevConfigTransform",
                    f"Restore prior {OVERLAY_FILENAME} before dev transform",
                    compensation,
                    undo_payload,
                ),
                idempotency_key=idempotency_key,
            )
            uow.commit()
            return result

    def get_return_path_status(self, *, project_id: ProjectId, git_repository_id: str | None = None) -> dict[str, Any]:
        self._require_pathway2_origin(project_id)
        project_root = self._require_project_root(project_id)
        topology = discover_project_repo_topology(project_root)
        registered = self._container.create_git_service().list_git_repositories(project_id)
        if not registered and not topology.repos:
            raise Pathway2ApplicationError(ErrorCode.NOT_FOUND, "No git repository discovered for project")

        # Ensure nested/assembly repos are registered so per-repo status/commit can resolve IDs.
        self._ensure_topology_repos_registered(project_id=project_id, topology=topology, registered=registered)
        registered = self._container.create_git_service().list_git_repositories(project_id)

        server_cfg_rel = self._pathway2_settings(project_id).get(Pathway2SettingKeys.SERVER_CFG_PATH)
        git_service = self._container.create_git_service()
        repo_slices = []
        for discovered in topology.repos:
            matched = match_registered_repo(discovered=discovered, registered_repos=registered)
            if matched is None:
                continue
            if git_repository_id and matched["git_repository_id"] != git_repository_id:
                continue
            worktree = git_service.get_worktree_status(project_id, matched["git_repository_id"])
            file_changes = _file_changes_from_worktree(worktree)
            repo_root = Path(discovered.real_target).resolve()
            slice_ = build_repo_return_slice(
                project_root=project_root,
                discovered=discovered,
                registered=matched,
                file_changes=file_changes,
                branch_name=worktree.get("branch_name"),
                is_dirty=bool(worktree.get("is_dirty")),
                server_cfg_rel=server_cfg_rel,
                read_text=self.filesystem.read_text,
                scanner=self.secret_scanner,
                overlay_gitignored=self._overlay_gitignored(repo_root) or self._overlay_gitignored(project_root),
                has_git_baseline=bool(worktree.get("head_commit_sha")),
            )
            repo_slices.append(slice_)

        if git_repository_id and not repo_slices:
            # Fallback: registered repo not in topology scan (legacy single-repo path).
            repo = self._resolve_git_repository(project_id, git_repository_id)
            worktree = git_service.get_worktree_status(project_id, repo["git_repository_id"])
            from backend.domain.project.topology import DiscoveredRepo, RepoKind

            discovered = DiscoveredRepo(
                path=repo["local_path"],
                real_target=repo["local_path"],
                kind=RepoKind.ROOT,
                branch=worktree.get("branch_name"),
                remote_redacted=repo.get("remote_url"),
                is_junction=False,
            )
            repo_slices.append(
                build_repo_return_slice(
                    project_root=project_root,
                    discovered=discovered,
                    registered=repo,
                    file_changes=_file_changes_from_worktree(worktree),
                    branch_name=worktree.get("branch_name"),
                    is_dirty=bool(worktree.get("is_dirty")),
                    server_cfg_rel=server_cfg_rel,
                    read_text=self.filesystem.read_text,
                    scanner=self.secret_scanner,
                    overlay_gitignored=self._overlay_gitignored(Path(repo["local_path"]).resolve()),
                    has_git_baseline=bool(worktree.get("head_commit_sha")),
                )
            )

        changed_slices = [item for item in repo_slices if item.has_changes]
        aggregate = aggregate_return_gate(repo_slices)
        unowned_local = build_unowned_local_entries(project_root=project_root, topology=topology)

        # Backward-compatible primary fields: first changed repo, else first repo, else empty.
        # Single-repo keeps the per-repo report; multi-repo surfaces the aggregate gate.
        primary = changed_slices[0] if changed_slices else (repo_slices[0] if repo_slices else None)
        primary_paths = list(primary.default_commit_paths) if primary else []
        primary_scope = primary.commit_scope if primary else {
            "normalization_paths": [],
            "dev_change_paths": [],
            "normalization_only": True,
            "total_paths": 0,
        }
        primary_report = primary.contamination_report if primary and len(repo_slices) <= 1 else aggregate

        return {
            "project_id": str(project_id),
            "structure_kind": topology.structure_kind.value,
            "git_repository_id": primary.git_repository_id if primary else None,
            "branch_name": primary.branch_name if primary else None,
            "is_dirty": any(item.is_dirty for item in repo_slices),
            "default_commit_paths": primary_paths,
            "commit_scope": primary_scope,
            "contamination_report": primary_report,
            "gitignore_contains_overlay": any(item.gitignore_contains_overlay for item in repo_slices)
            or self._overlay_gitignored(project_root),
            "manual_push_message": aggregate["manual_push_message"],
            "repos": [item.to_dict() for item in repo_slices],
            "unowned_local_paths": unowned_local,
            "has_any_changes": len(changed_slices) > 0,
            "nothing_to_return": len(changed_slices) == 0,
        }

    def preview_safe_return_commit(
        self,
        *,
        project_id: ProjectId,
        git_repository_id: str,
        message: str,
        paths: list[str] | None = None,
        include_server_cfg: bool = False,
    ) -> CommandPreview:
        self._require_pathway2_origin(project_id)
        repo = self._resolve_git_repository(project_id, git_repository_id)
        resolved_paths, safety = self._evaluate_return_commit_paths(
            project_id=project_id,
            repo=repo,
            paths=paths,
            include_server_cfg=include_server_cfg,
        )
        return CommandPreview(
            "PlanSafeReturnCommit",
            "Preview fail-closed return-path commit",
            {
                "project_id": str(project_id),
                "git_repository_id": repo["git_repository_id"],
                "message": message,
                "paths": resolved_paths,
                "explicit_path_commit": True,
                "contamination_report": safety.to_report(),
            },
            warnings=[] if safety.allowed else ["Commit blocked by return-path secret gate"],
            risk_level=RiskLevel.HIGH,
        )

    def dry_run_safe_return_commit(
        self,
        *,
        project_id: ProjectId,
        git_repository_id: str,
        message: str,
        paths: list[str] | None = None,
        include_server_cfg: bool = False,
    ) -> DryRunResult:
        preview = self.preview_safe_return_commit(
            project_id=project_id,
            git_repository_id=git_repository_id,
            message=message,
            paths=paths,
            include_server_cfg=include_server_cfg,
        )
        allowed = bool(preview.preview["contamination_report"]["allowed"])
        return DryRunResult(preview.command_type, allowed, preview.preview, preview.warnings)

    def execute_safe_return_commit(
        self,
        *,
        project_id: ProjectId,
        git_repository_id: str,
        message: str,
        paths: list[str] | None = None,
        include_server_cfg: bool = False,
        idempotency_key: str | None = None,
    ) -> CommandExecutionResult:
        preview = self.preview_safe_return_commit(
            project_id=project_id,
            git_repository_id=git_repository_id,
            message=message,
            paths=paths,
            include_server_cfg=include_server_cfg,
        )
        dry_run = self.dry_run_safe_return_commit(
            project_id=project_id,
            git_repository_id=git_repository_id,
            message=message,
            paths=paths,
            include_server_cfg=include_server_cfg,
        )
        if not dry_run.valid:
            raise Pathway2ApplicationError(
                ErrorCode.VALIDATION_FAILED,
                "Return-path commit blocked by secret gate — fix or unstage flagged files",
            )
        resolved_paths = list(preview.preview["paths"])
        return self._container.create_git_service().execute_create_commit(
            project_id=project_id,
            git_repository_id=git_repository_id,
            message=message,
            paths=resolved_paths,
            idempotency_key=idempotency_key,
        )

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

    def _structural_validation_block(self, root: Path, *, for_response: bool = False) -> tuple[dict[str, Any], list[str]]:
        result = run_structural_validation(root=root, filesystem=self.filesystem, secret_scanner=self.secret_scanner)
        payload = enrich_validation_payload(result, root_path=str(root), for_response=for_response)
        return payload, result.warning_summary()

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
            raise Pathway2ApplicationError(ErrorCode.PRECONDITION_FAILED, "Apply P2-2 secret substitution first")

    def _default_transform_options(self, project_id: ProjectId) -> DevTransformOptions:
        settings = self._pathway2_settings(project_id)
        stored = settings.get(Pathway2SettingKeys.TRANSFORM_OPTIONS)
        if isinstance(stored, dict) and stored:
            return DevTransformOptions(
                hostname=str(stored.get("hostname", DevTransformOptions.hostname)),
                max_clients=int(stored.get("max_clients", DevTransformOptions.max_clients)),
                udp_port=int(stored.get("udp_port", DevTransformOptions.udp_port)),
                tcp_port=int(stored.get("tcp_port", DevTransformOptions.tcp_port)),
                dev_convars=dict(stored.get("dev_convars", DevTransformOptions().dev_convars)),
            )
        with self._container.session_factory() as session:
            repository = ProjectRepository(RepositoryContext(session=session, project_id=project_id))
            project = repository.get_project(project_id)
            display_name = project.display_name if project else None
        return default_transform_options(project_display_name=display_name)

    def _base_server_cfg_content(self, project_id: ProjectId) -> str | None:
        try:
            _, _, content = self._load_server_cfg(project_id)
        except Pathway2ApplicationError:
            return None
        return content

    def _require_pathway2_origin(self, project_id: ProjectId) -> None:
        settings = self._pathway2_settings(project_id)
        if not settings.get(Pathway2SettingKeys.ORIGIN):
            raise Pathway2ApplicationError(ErrorCode.PRECONDITION_FAILED, "Return-path commit requires an adopted Pathway 2 project")

    def _resolve_git_repository(self, project_id: ProjectId, git_repository_id: str | None) -> dict[str, Any]:
        repos = self._container.create_git_service().list_git_repositories(project_id)
        if not repos:
            raise Pathway2ApplicationError(ErrorCode.NOT_FOUND, "No git repository discovered for project")
        if git_repository_id:
            for repo in repos:
                if repo["git_repository_id"] == git_repository_id:
                    return repo
            raise Pathway2ApplicationError(ErrorCode.NOT_FOUND, f"Git repository not found: {git_repository_id}")
        return repos[0]

    def _evaluate_return_commit_paths(
        self,
        *,
        project_id: ProjectId,
        repo: dict[str, Any],
        paths: list[str] | None,
        include_server_cfg: bool,
    ):
        project_root = self._require_project_root(project_id)
        topology = discover_project_repo_topology(project_root)
        worktree = self._container.create_git_service().get_worktree_status(project_id, repo["git_repository_id"])
        repo_root = Path(repo["local_path"]).resolve()
        file_changes = _file_changes_from_worktree(worktree)
        server_cfg_rel = self._pathway2_settings(project_id).get(Pathway2SettingKeys.SERVER_CFG_PATH)

        from backend.domain.project.topology import DiscoveredRepo, RepoKind, resolve_path_owning_repo

        discovered = next(
            (
                item
                for item in topology.repos
                if Path(item.real_target).resolve() == repo_root or Path(item.path).resolve() == repo_root
            ),
            None,
        )
        if discovered is None:
            discovered = DiscoveredRepo(
                path=str(repo_root),
                real_target=str(repo_root),
                kind=RepoKind.ROOT,
                branch=worktree.get("branch_name"),
                remote_redacted=repo.get("remote_url"),
                is_junction=False,
            )

        if paths:
            for path in paths:
                absolute = (repo_root / path).resolve()
                if not _path_inside(absolute, repo_root):
                    raise Pathway2ApplicationError(
                        ErrorCode.VALIDATION_FAILED,
                        f"{path} is outside this repository and cannot be committed here",
                    )
                owner = resolve_path_owning_repo(project_root, absolute, topology)
                if owner is None and not any(_path_inside(absolute, Path(item.real_target)) for item in topology.repos):
                    raise Pathway2ApplicationError(
                        ErrorCode.VALIDATION_FAILED,
                        f"{path} stays local (not tracked by any repo) and cannot be committed",
                    )

        slice_ = build_repo_return_slice(
            project_root=project_root,
            discovered=discovered,
            registered=repo,
            file_changes=file_changes,
            branch_name=worktree.get("branch_name"),
            is_dirty=bool(worktree.get("is_dirty")),
            server_cfg_rel=server_cfg_rel,
            read_text=self.filesystem.read_text,
            scanner=self.secret_scanner,
            overlay_gitignored=self._overlay_gitignored(repo_root) or self._overlay_gitignored(project_root),
            include_server_cfg=include_server_cfg if paths is not None else None,
            paths=paths,
            has_git_baseline=bool(worktree.get("head_commit_sha")),
        )
        resolved_paths = list(slice_.default_commit_paths)
        if any(is_overlay_path(path) for path in resolved_paths):
            raise Pathway2ApplicationError(ErrorCode.VALIDATION_FAILED, f"{OVERLAY_FILENAME} cannot be included in a return-path commit")
        staged_files = load_staged_files(repo_root=repo_root, paths=resolved_paths, read_text=self.filesystem.read_text)
        safety = evaluate_commit_safety(staged_files=staged_files, scanner=self.secret_scanner)
        return resolved_paths, safety

    def _ensure_topology_repos_registered(
        self,
        *,
        project_id: ProjectId,
        topology,
        registered: list[dict[str, Any]],
    ) -> None:
        """Register any topology-discovered repos missing from the git registry."""
        for discovered in topology.repos:
            if match_registered_repo(discovered=discovered, registered_repos=registered) is None:
                self._container.create_git_service().execute_discover_git_repositories(project_id=project_id)
                return

    def _overlay_gitignored(self, project_root: Path) -> bool:
        gitignore_path = project_root / ".gitignore"
        content = self.filesystem.read_text(gitignore_path) or ""
        return GITIGNORE_OVERLAY_ENTRY in content


def _path_inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _file_changes_from_worktree(worktree: dict[str, Any]) -> list[Any]:
    from types import SimpleNamespace

    from backend.domain.git import ChangeStatus

    changes: list[Any] = []
    for item in worktree.get("file_changes", []):
        status = item["change_status"]
        if isinstance(status, str):
            status = ChangeStatus(status)
        changes.append(SimpleNamespace(path=item["path"], change_status=status))
    return changes


def _undo_settings_patch(command_type: str, *, overlay_content: str | None) -> dict[str, Any] | None:
    if command_type == "RevertRepoNormalization":
        return {
            Pathway2SettingKeys.NORMALIZED: False,
            Pathway2SettingKeys.SECRETS_SUBSTITUTED: False,
            Pathway2SettingKeys.RUN_READY: False,
            Pathway2SettingKeys.SUBSTITUTION_SLOTS: [],
            Pathway2SettingKeys.UNSET_DEV_SLOTS: [],
            Pathway2SettingKeys.DEV_TRANSFORMED: False,
            Pathway2SettingKeys.TRANSFORM_OPTIONS: {},
        }
    if command_type == "RevertSecretSubstitution":
        return {
            Pathway2SettingKeys.SECRETS_SUBSTITUTED: False,
            Pathway2SettingKeys.RUN_READY: False,
            Pathway2SettingKeys.SUBSTITUTION_SLOTS: [],
            Pathway2SettingKeys.UNSET_DEV_SLOTS: [],
            Pathway2SettingKeys.DEV_TRANSFORMED: False,
            Pathway2SettingKeys.TRANSFORM_OPTIONS: {},
        }
    if command_type == "RevertDevSecretApply":
        run_ready, unset = compute_run_gate(overlay_content or "")
        return {
            Pathway2SettingKeys.RUN_READY: run_ready,
            Pathway2SettingKeys.UNSET_DEV_SLOTS: unset,
        }
    if command_type == "RevertDevConfigTransform":
        return {
            Pathway2SettingKeys.DEV_TRANSFORMED: False,
            Pathway2SettingKeys.TRANSFORM_OPTIONS: {},
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
        "dev_transformed": bool(settings.get(Pathway2SettingKeys.DEV_TRANSFORMED)),
        "server_started": bool(settings.get(Pathway2SettingKeys.SERVER_STARTED)),
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
