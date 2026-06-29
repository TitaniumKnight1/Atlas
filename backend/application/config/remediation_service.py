from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.adapters.config import unified_diff
from backend.application.commands import CommandContext, CommandExecutionResult, CommandPreview, DryRunResult, RiskLevel, UndoPlan
from backend.application.commands.recorder import CommandAuditRecorder
from backend.application.commands.serialization import compensation_from_storage
from backend.application.config.service import RestoreConfigFileCompensation
from backend.application.config.structural_validation import enrich_validation_payload, run_structural_validation
from backend.application.pathway2.compensation import pathway2_audit_undo_payload, pathway2_undo_root, snapshot_config_compensation
from backend.domain.config.structural import ConfigFindingType
from backend.domain.pathway2.normalization import find_server_cfg
from backend.domain.shared_kernel import ErrorCode, ProjectId


class ConfigRemediationError(RuntimeError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


ATLAS_DANGLING_COMMENT = "commented by Atlas: resource not found"
ENSURE_LINE = re.compile(r"^(\s*)(ensure|start)(\s+)([^\s#;]+)(.*)$", re.IGNORECASE)
ABSOLUTE_IN_QUOTES = re.compile(
    r'^(\s*(?:set|setr|sets)\s+\S+\s+)(["\'])([^"\']*(?:[A-Za-z]:[\\/]|/home/|/Users/)[^"\']*)\2(.*)$'
)


@dataclass(frozen=True, slots=True)
class ResolvedFinding:
    finding: dict[str, Any]
    absolute_path: Path
    rel_path: str


class ConfigRemediationService:
    def __init__(self, *, container: Any, filesystem: Any, secret_scanner: Any) -> None:
        self._container = container
        self._filesystem = filesystem
        self._secret_scanner = secret_scanner
        self._recorder = CommandAuditRecorder()

    def preview_comment_out_dangling_ensure(self, *, project_id: ProjectId, finding_id: str) -> CommandPreview:
        resolved = self._resolve_finding(project_id, finding_id, ConfigFindingType.DANGLING_RESOURCE_REFERENCE)
        current = self._filesystem.read_text(resolved.absolute_path) or ""
        proposed = _comment_out_line(current, resolved.finding.get("line"), resolved.finding.get("context", {}).get("resource_name"))
        diff = unified_diff(current, proposed, resolved.rel_path)
        return CommandPreview(
            "CommentOutConfigEnsure",
            f"Comment out dangling ensure in {resolved.rel_path}",
            {
                "project_id": str(project_id),
                "finding_id": finding_id,
                "path": resolved.rel_path,
                "line": resolved.finding.get("line"),
                "diff": diff,
                "proposed_line_preview": _line_preview(proposed, resolved.finding.get("line")),
            },
            risk_level=RiskLevel.MEDIUM,
        )

    def dry_run_comment_out_dangling_ensure(self, *, project_id: ProjectId, finding_id: str) -> DryRunResult:
        preview = self.preview_comment_out_dangling_ensure(project_id=project_id, finding_id=finding_id)
        resolved = self._resolve_finding(project_id, finding_id, ConfigFindingType.DANGLING_RESOURCE_REFERENCE)
        valid = resolved.absolute_path.is_file()
        warnings: list[str] = []
        if not valid:
            warnings.append("Target config file is missing.")
        return DryRunResult(preview.command_type, valid, preview.preview, warnings)

    def execute_comment_out_dangling_ensure(self, *, project_id: ProjectId, finding_id: str) -> CommandExecutionResult:
        preview = self.preview_comment_out_dangling_ensure(project_id=project_id, finding_id=finding_id)
        resolved = self._resolve_finding(project_id, finding_id, ConfigFindingType.DANGLING_RESOURCE_REFERENCE)
        prior = self._filesystem.read_text(resolved.absolute_path) or ""
        proposed = _comment_out_line(prior, resolved.finding.get("line"), resolved.finding.get("context", {}).get("resource_name"))
        compensation = snapshot_config_compensation(
            undo_root=pathway2_undo_root(self._container.app_data_dir, project_id),
            absolute_path=resolved.absolute_path,
            prior_content=prior,
            filesystem=self._filesystem,
        )
        self._filesystem.write_text(resolved.absolute_path, proposed)
        undo_payload = pathway2_audit_undo_payload(compensation, project_id)
        return self._record_execution(
            project_id,
            preview,
            compensation,
            undo_payload,
            "UndoCommentOutConfigEnsure",
            f"Restore {resolved.rel_path} before dangling-ensure comment-out",
            {"path": resolved.rel_path, "finding_id": finding_id},
        )

    def preview_rewrite_absolute_path(self, *, project_id: ProjectId, finding_id: str) -> CommandPreview:
        resolved = self._resolve_finding(project_id, finding_id, ConfigFindingType.ABSOLUTE_PATH)
        project_root = self._project_root(project_id)
        current = self._filesystem.read_text(resolved.absolute_path) or ""
        proposed, portable = _rewrite_absolute_line(current, resolved.finding.get("line"), project_root)
        if portable is None:
            raise ConfigRemediationError(ErrorCode.PRECONDITION_FAILED, "Absolute path rewrite is ambiguous; use prompt export instead.")
        diff = unified_diff(current, proposed, resolved.rel_path)
        return CommandPreview(
            "RewriteConfigAbsolutePath",
            f"Rewrite absolute path in {resolved.rel_path}",
            {
                "project_id": str(project_id),
                "finding_id": finding_id,
                "path": resolved.rel_path,
                "line": resolved.finding.get("line"),
                "diff": diff,
                "portable_path": portable,
                "requires_confirmation": True,
            },
            warnings=["Confirm the portable path resolves on your machine before applying."],
            risk_level=RiskLevel.HIGH,
        )

    def dry_run_rewrite_absolute_path(self, *, project_id: ProjectId, finding_id: str) -> DryRunResult:
        preview = self.preview_rewrite_absolute_path(project_id=project_id, finding_id=finding_id)
        return DryRunResult(preview.command_type, True, preview.preview, preview.warnings)

    def execute_rewrite_absolute_path(self, *, project_id: ProjectId, finding_id: str) -> CommandExecutionResult:
        preview = self.preview_rewrite_absolute_path(project_id=project_id, finding_id=finding_id)
        resolved = self._resolve_finding(project_id, finding_id, ConfigFindingType.ABSOLUTE_PATH)
        project_root = self._project_root(project_id)
        prior = self._filesystem.read_text(resolved.absolute_path) or ""
        proposed, _ = _rewrite_absolute_line(prior, resolved.finding.get("line"), project_root)
        if proposed == prior:
            raise ConfigRemediationError(ErrorCode.PRECONDITION_FAILED, "No portable rewrite available.")
        compensation = snapshot_config_compensation(
            undo_root=pathway2_undo_root(self._container.app_data_dir, project_id),
            absolute_path=resolved.absolute_path,
            prior_content=prior,
            filesystem=self._filesystem,
        )
        self._filesystem.write_text(resolved.absolute_path, proposed)
        undo_payload = pathway2_audit_undo_payload(compensation, project_id)
        return self._record_execution(
            project_id,
            preview,
            compensation,
            undo_payload,
            "UndoRewriteConfigAbsolutePath",
            f"Restore {resolved.rel_path} before absolute-path rewrite",
            {"path": resolved.rel_path, "finding_id": finding_id},
        )

    def undo(self, undo_plan: UndoPlan) -> CommandExecutionResult:
        project_id_value = undo_plan.payload.get("project_id")
        project_id = ProjectId(str(project_id_value)) if project_id_value else None
        preview = CommandPreview(undo_plan.command_type, undo_plan.summary, {"undo": undo_plan.payload}, risk_level=RiskLevel.HIGH)
        action = (
            compensation_from_storage(undo_plan.payload, filesystem=self._filesystem)
            if undo_plan.payload.get("action_type") in {"restore_config_file", "restore_path_from_snapshot", "composite_compensation"}
            else undo_plan.action
        )
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            action_result = action.apply(CommandContext(uow=uow))
            result = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="ConfigRemediationUndo",
                entity_id=str(project_id) if project_id else None,
                summary=undo_plan.summary,
                result=action_result,
                events=[],
                undo_plan=None,
            )
            uow.commit()
            return result

    def _resolve_finding(self, project_id: ProjectId, finding_id: str, expected_type: ConfigFindingType) -> ResolvedFinding:
        project_root = self._project_root(project_id)
        validation = run_structural_validation(root=project_root, filesystem=self._filesystem, secret_scanner=self._secret_scanner)
        payload = enrich_validation_payload(validation, root_path=str(project_root))
        match = next((item for item in payload.get("findings", []) if item.get("finding_id") == finding_id), None)
        if match is None:
            raise ConfigRemediationError(ErrorCode.NOT_FOUND, f"Finding not found: {finding_id}")
        if match.get("type") != expected_type.value:
            raise ConfigRemediationError(ErrorCode.VALIDATION_FAILED, "Finding type does not support this remediation.")
        remediation = match.get("remediation") or {}
        if not remediation.get("auto_fix_available"):
            raise ConfigRemediationError(ErrorCode.PRECONDITION_FAILED, "No safe auto-fix available for this finding.")
        rel_path = match.get("path") or ""
        absolute = (project_root / rel_path).resolve()
        if not absolute.is_file():
            server_cfg = find_server_cfg(project_root)
            if server_cfg is None:
                raise ConfigRemediationError(ErrorCode.NOT_FOUND, "Config file not found.")
            absolute = server_cfg.resolve()
            rel_path = str(server_cfg.relative_to(project_root)).replace("\\", "/")
        return ResolvedFinding(finding=match, absolute_path=absolute, rel_path=rel_path)

    def _project_root(self, project_id: ProjectId) -> Path:
        project = self._container.create_project_service().get_project(project_id)
        for item in project.get("paths", []):
            if item.get("path_role") == "root":
                return Path(str(item.get("absolute_path"))).resolve()
        raise ConfigRemediationError(ErrorCode.NOT_FOUND, f"Project root not found: {project_id}")

    def _record_execution(
        self,
        project_id: ProjectId,
        preview: CommandPreview,
        compensation: Any,
        undo_payload: dict[str, Any],
        undo_command_type: str,
        undo_summary: str,
        result_extra: dict[str, Any],
    ) -> CommandExecutionResult:
        undo_plan = UndoPlan(undo_command_type, undo_summary, compensation, undo_payload)
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            result = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="ConfigRemediation",
                entity_id=str(project_id),
                summary=preview.summary,
                result={**result_extra, "command_type": preview.command_type},
                events=[],
                undo_plan=undo_plan,
            )
            uow.commit()
            return result


def _comment_out_line(content: str, line_number: int | None, resource_name: str | None) -> str:
    if line_number is None:
        raise ConfigRemediationError(ErrorCode.VALIDATION_FAILED, "Finding is missing line number.")
    lines = content.splitlines(keepends=True)
    index = line_number - 1
    if index < 0 or index >= len(lines):
        raise ConfigRemediationError(ErrorCode.VALIDATION_FAILED, "Line number out of range.")
    raw = lines[index]
    stripped = raw.lstrip()
    if stripped.lstrip("#").strip().startswith(("ensure", "start")):
        comment = raw.rstrip("\r\n")
        lines[index] = f"# {comment.strip()}  # {ATLAS_DANGLING_COMMENT}\n"
        return "".join(lines)
    match = ENSURE_LINE.match(raw.rstrip("\r\n"))
    if match is None:
        raise ConfigRemediationError(ErrorCode.VALIDATION_FAILED, "Line is not an ensure/start directive.")
    token = match.group(4).strip().strip('"').strip("'")
    if resource_name and token != resource_name:
        raise ConfigRemediationError(ErrorCode.VALIDATION_FAILED, "Line no longer matches the finding resource name.")
    lines[index] = f"{match.group(1)}# {match.group(2)}{match.group(3)}{match.group(4)}{match.group(5)}  # {ATLAS_DANGLING_COMMENT}\n"
    return "".join(lines)


def _rewrite_absolute_line(content: str, line_number: int | None, project_root: Path) -> tuple[str, str | None]:
    if line_number is None:
        return content, None
    lines = content.splitlines(keepends=True)
    index = line_number - 1
    if index < 0 or index >= len(lines):
        return content, None
    raw = lines[index]
    match = ABSOLUTE_IN_QUOTES.match(raw.rstrip("\r\n"))
    if match is None:
        return content, None
    absolute_value = match.group(3)
    try:
        absolute_path = Path(absolute_value).resolve()
        portable = absolute_path.relative_to(project_root.resolve())
        portable_text = str(portable).replace("\\", "/")
    except (OSError, ValueError):
        return content, None
    quote = match.group(2)
    lines[index] = f"{match.group(1)}{quote}{portable_text}{quote}{match.group(4)}\n"
    return "".join(lines), portable_text


def _line_preview(content: str, line_number: int | None) -> str | None:
    if line_number is None:
        return None
    lines = content.splitlines()
    index = line_number - 1
    if 0 <= index < len(lines):
        return lines[index]
    return None
