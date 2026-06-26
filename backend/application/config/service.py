from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from backend.adapters.config import FiveMConfigValidator, LocalConfigSecretScanner, content_hash, unified_diff
from backend.adapters.persistence import ConfigRepository, ProjectRepository
from backend.adapters.persistence.models import ProjectPathRecord
from backend.application.commands import CommandContext, CommandExecutionResult, CommandPreview, DryRunResult, RiskLevel, UndoPlan
from backend.application.commands.recorder import CommandAuditRecorder
from backend.domain.config import (
    ConfigFilesystemPort,
    ConfigValidationPort,
    FindingSeverity,
    SecretScannerPort,
    SnapshotKind,
    config_changed,
    config_change_planned,
    config_inventory_changed,
    config_validation_failed,
    secret_scan_finding_detected,
)
from backend.domain.shared_kernel import ErrorCode, ProjectId, StableIdentifier
from backend.infrastructure.unit_of_work import RepositoryContext


class ConfigApplicationError(RuntimeError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class RestoreConfigFileCompensation:
    """Snapshot restore compensation — same mechanism as M3a setup server.cfg undo."""

    absolute_path: str
    prior_content: str | None
    filesystem: ConfigFilesystemPort
    action_type: str = "restore_config_file"

    def describe(self) -> dict[str, Any]:
        return {"action_type": self.action_type, "absolute_path": self.absolute_path, "had_prior_content": self.prior_content is not None}

    def apply(self, context: CommandContext) -> dict[str, Any]:
        path = Path(self.absolute_path)
        if self.prior_content is None:
            if path.exists():
                path.unlink()
            return {"absolute_path": str(path), "restored": "deleted_new_file"}
        self.filesystem.write_text(path, self.prior_content)
        return {"absolute_path": str(path), "restored": "prior_content"}


class ConfigApplicationService:
    def __init__(
        self,
        *,
        container: Any,
        filesystem: ConfigFilesystemPort,
        validator: ConfigValidationPort,
        secret_scanner: SecretScannerPort,
    ) -> None:
        self._container = container
        self._filesystem = filesystem
        self._validator = validator
        self._secret_scanner = secret_scanner
        self._recorder = CommandAuditRecorder()

    def execute_rescan_config_files(self, *, project_id: ProjectId, scan_roots: list[str] | None = None) -> dict[str, Any]:
        now = datetime.now(UTC)
        discovered = self._discover_config_files(project_id, scan_roots)
        changed = 0
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            self._require_project(uow.repository(ProjectRepository), project_id)
            repository = uow.repository(ConfigRepository)
            for item in discovered:
                repository.upsert_config_file(
                    config_file_id=StableIdentifier.new() if item.get("config_file_id") is None else StableIdentifier(item["config_file_id"]),
                    project_id=project_id,
                    environment_id=None,
                    path=item["path"],
                    config_type=item["config_type"],
                    parser_kind="fivem_server_cfg" if item["config_type"] == "server_cfg" else None,
                    content_hash=item.get("content_hash"),
                    scanned_at=now,
                )
                changed += 1
            uow.collect_event(config_inventory_changed(project_id, changed))
            uow.commit()
        return {"project_id": str(project_id), "changed_count": changed, "files": discovered}

    def list_config_files(self, project_id: ProjectId) -> list[dict[str, Any]]:
        with self._container.session_factory() as session:
            return [_config_file_data(record) for record in ConfigRepository(RepositoryContext(session=session, project_id=project_id)).list_config_files(project_id)]

    def get_config_file_view(self, project_id: ProjectId, config_file_id: str) -> dict[str, Any]:
        record = self._get_config_record(project_id, config_file_id)
        absolute = self._absolute_path(project_id, record.path)
        content = self._filesystem.read_text(absolute)
        return {**_config_file_data(record), "absolute_path": str(absolute), "content": content}

    def preview_plan_config_change(self, *, project_id: ProjectId, config_file_id: str, proposed_content: str) -> CommandPreview:
        record = self._get_config_record(project_id, config_file_id)
        absolute = self._absolute_path(project_id, record.path)
        current = self._filesystem.read_text(absolute) or ""
        diff = unified_diff(current, proposed_content, record.path)
        findings = self._validator.validate(path=record.path, content=proposed_content, config_type=record.config_type)
        secret_hits = self._secret_scanner.scan(path=record.path, content=proposed_content)
        return CommandPreview(
            "PlanConfigChangeSet",
            f"Preview config change for {record.path}",
            {
                "project_id": str(project_id),
                "config_file_id": config_file_id,
                "path": record.path,
                "diff": diff,
                "validation_findings": [_finding_data(item) for item in findings],
                "secret_findings": [_secret_data(item) for item in secret_hits],
            },
            warnings=[item.message for item in findings if item.severity in {FindingSeverity.WARNING, FindingSeverity.ERROR}],
            risk_level=RiskLevel.HIGH,
        )

    def dry_run_plan_config_change(self, *, project_id: ProjectId, config_file_id: str, proposed_content: str) -> DryRunResult:
        preview = self.preview_plan_config_change(project_id=project_id, config_file_id=config_file_id, proposed_content=proposed_content)
        findings = preview.preview["validation_findings"]
        valid = not any(item["severity"] == "error" for item in findings)
        return DryRunResult(preview.command_type, valid, preview.preview, preview.warnings)

    def execute_apply_config_change(
        self,
        *,
        project_id: ProjectId,
        config_file_id: str,
        proposed_content: str,
        idempotency_key: str | None = None,
    ) -> CommandExecutionResult:
        preview = self.preview_plan_config_change(project_id=project_id, config_file_id=config_file_id, proposed_content=proposed_content)
        dry_run = self.dry_run_plan_config_change(project_id=project_id, config_file_id=config_file_id, proposed_content=proposed_content)
        if not dry_run.valid:
            raise ConfigApplicationError(ErrorCode.VALIDATION_FAILED, "Config change failed validation")
        record = self._get_config_record(project_id, config_file_id)
        absolute = self._absolute_path(project_id, record.path)
        prior_content = self._filesystem.read_text(absolute)
        now = datetime.now(UTC)
        change_set_id = StableIdentifier.new()
        before_snapshot_id = StableIdentifier.new()
        after_snapshot_id = StableIdentifier.new()
        compensation = RestoreConfigFileCompensation(str(absolute), prior_content, self._filesystem)
        self._filesystem.write_text(absolute, proposed_content)
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(ConfigRepository)
            repository.add_snapshot(
                config_snapshot_id=before_snapshot_id,
                config_file_id=config_file_id,
                snapshot_kind=SnapshotKind.BEFORE.value,
                content_hash=content_hash(prior_content or ""),
                captured_at=now,
                metadata={"content": prior_content},
            )
            repository.add_snapshot(
                config_snapshot_id=after_snapshot_id,
                config_file_id=config_file_id,
                snapshot_kind=SnapshotKind.AFTER.value,
                content_hash=content_hash(proposed_content),
                captured_at=now,
                metadata={"content": proposed_content},
            )
            uow.session.flush()
            repository.create_change_set(
                config_change_set_id=change_set_id,
                project_id=project_id,
                status="applied",
                summary=f"Applied config change to {record.path}",
                before_snapshot_id=str(before_snapshot_id),
                after_snapshot_id=str(after_snapshot_id),
                created_at=now,
                applied_at=now,
            )
            record_row = repository.get_config_file(project_id, StableIdentifier(config_file_id))
            if record_row is not None:
                record_row.content_hash = content_hash(proposed_content)
            result = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="ConfigChangeSet",
                entity_id=str(change_set_id),
                summary=f"Applied config change to {record.path}",
                result={
                    "project_id": str(project_id),
                    "config_file_id": config_file_id,
                    "config_change_set_id": str(change_set_id),
                    "before_snapshot_id": str(before_snapshot_id),
                    "after_snapshot_id": str(after_snapshot_id),
                    "diff": preview.preview["diff"],
                },
                events=[config_change_planned(project_id, config_file_id, RiskLevel.HIGH.value), config_changed(project_id, str(change_set_id), config_file_id)],
                undo_plan=UndoPlan(
                    "RevertConfigChangeSet",
                    f"Restore prior content for {record.path}",
                    compensation,
                    {**compensation.describe(), "project_id": str(project_id), "config_file_id": config_file_id},
                ),
                idempotency_key=idempotency_key,
            )
            uow.commit()
            return result

    def undo(self, undo_plan: UndoPlan) -> CommandExecutionResult:
        project_id_value = undo_plan.payload.get("project_id")
        project_id = ProjectId(str(project_id_value)) if project_id_value else None
        preview = CommandPreview(undo_plan.command_type, undo_plan.summary, {"undo": undo_plan.payload}, risk_level=RiskLevel.HIGH)
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            action_result = undo_plan.action.apply(CommandContext(uow=uow))
            result = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="ConfigUndo",
                entity_id=str(project_id) if project_id else "global",
                summary=undo_plan.summary,
                result=action_result,
                events=[],
                undo_plan=None,
            )
            uow.commit()
            return result

    def execute_run_validation(self, *, project_id: ProjectId, config_file_id: str | None = None) -> dict[str, Any]:
        now = datetime.now(UTC)
        run_id = StableIdentifier.new()
        findings: list[dict[str, Any]] = []
        status = "pass"
        if config_file_id:
            record = self._get_config_record(project_id, config_file_id)
            absolute = self._absolute_path(project_id, record.path)
            content = self._filesystem.read_text(absolute) or ""
            for item in self._validator.validate(path=record.path, content=content, config_type=record.config_type):
                findings.append(_finding_data(item))
        else:
            for record in self._list_records(project_id):
                absolute = self._absolute_path(project_id, record.path)
                content = self._filesystem.read_text(absolute) or ""
                for item in self._validator.validate(path=record.path, content=content, config_type=record.config_type):
                    findings.append(_finding_data(item))
        if any(item["severity"] == "error" for item in findings):
            status = "fail"
        elif any(item["severity"] == "warning" for item in findings):
            status = "warning"
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(ConfigRepository)
            repository.add_validation_run(
                run_id=run_id,
                project_id=project_id,
                config_file_id=config_file_id,
                validator_id="fivem_server_cfg",
                status=status,
                started_at=now,
                finished_at=now,
                summary={"finding_count": len(findings)},
            )
            uow.session.flush()
            for item in findings:
                repository.add_validation_finding(
                    finding_id=StableIdentifier.new(),
                    run_id=str(run_id),
                    severity=item["severity"],
                    rule_id=item["rule_id"],
                    path=item.get("path"),
                    line=item.get("line"),
                    column=item.get("column"),
                    message=item["message"],
                    details=item.get("details"),
                )
            events = []
            if status in {"fail", "warning"}:
                events.append(config_validation_failed(project_id, "fivem_server_cfg", status))
            for event in events:
                uow.collect_event(event)
            uow.commit()
        return {"config_validation_run_id": str(run_id), "status": status, "findings": findings}

    def execute_run_secret_scan(self, *, project_id: ProjectId, config_file_id: str | None = None) -> dict[str, Any]:
        now = datetime.now(UTC)
        stored: list[dict[str, Any]] = []
        events = []
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(ConfigRepository)
            targets = [self._get_config_record(project_id, config_file_id)] if config_file_id else self._list_records(project_id)
            for record in targets:
                absolute = self._absolute_path(project_id, record.path)
                content = self._filesystem.read_text(absolute) or ""
                findings = self._secret_scanner.scan(path=record.path, content=content)
                payload = [_secret_data(item) for item in findings]
                rows = repository.replace_secret_findings(
                    project_id=project_id,
                    config_file_id=record.config_file_id,
                    findings=payload,
                    detected_at=now,
                )
                for row in rows:
                    stored.append(_secret_record_data(row))
                    events.append(
                        secret_scan_finding_detected(
                            project_id,
                            row.secret_finding_id,
                            row.severity,
                            (row.metadata_json or {}).get("secret_type", "unknown"),
                        )
                    )
            for event in events:
                uow.collect_event(event)
            uow.commit()
        return {"project_id": str(project_id), "finding_count": len(stored), "findings": stored}

    def get_config_diff(self, project_id: ProjectId, config_file_id: str, snapshot_id: str | None = None) -> dict[str, Any]:
        record = self._get_config_record(project_id, config_file_id)
        absolute = self._absolute_path(project_id, record.path)
        current = self._filesystem.read_text(absolute) or ""
        if snapshot_id is None:
            snapshots = self._list_snapshots(project_id, config_file_id)
            if not snapshots:
                return {"path": record.path, "diff": unified_diff("", current, record.path), "snapshot_id": None}
            snapshot_id = snapshots[0]["config_snapshot_id"]
        snapshot = self._get_snapshot(project_id, snapshot_id)
        prior = (snapshot.metadata_json or {}).get("content", "")
        return {"path": record.path, "snapshot_id": snapshot_id, "diff": unified_diff(prior or "", current, record.path)}

    def list_snapshots(self, project_id: ProjectId, config_file_id: str) -> list[dict[str, Any]]:
        self._get_config_record(project_id, config_file_id)
        return self._list_snapshots(project_id, config_file_id)

    def list_validation_findings(self, project_id: ProjectId) -> list[dict[str, Any]]:
        with self._container.session_factory() as session:
            return [_validation_finding_data(record) for record in ConfigRepository(RepositoryContext(session=session, project_id=project_id)).list_validation_findings(project_id)]

    def list_secret_findings(self, project_id: ProjectId, status: str | None = None) -> list[dict[str, Any]]:
        with self._container.session_factory() as session:
            return [_secret_record_data(record) for record in ConfigRepository(RepositoryContext(session=session, project_id=project_id)).list_secret_findings(project_id, status)]

    def _discover_config_files(self, project_id: ProjectId, scan_roots: list[str] | None) -> list[dict[str, Any]]:
        project_root = self._project_root(project_id)
        roots = scan_roots or self._default_scan_roots(project_id, project_root)
        existing = {record.path: record for record in self._list_records(project_id)}
        discovered: list[dict[str, Any]] = []
        seen: set[str] = set()
        for root in roots:
            base = Path(root).resolve()
            if not base.exists():
                continue
            candidates = [base / "server.cfg", *base.rglob("*.cfg")]
            for candidate in candidates:
                if not candidate.is_file():
                    continue
                rel = self._relative_config_path(project_root, candidate)
                if rel in seen:
                    continue
                seen.add(rel)
                content = self._filesystem.read_text(candidate) or ""
                prior = existing.get(rel)
                discovered.append(
                    {
                        "config_file_id": prior.config_file_id if prior else None,
                        "path": rel,
                        "config_type": "server_cfg" if rel.endswith("server.cfg") else "resource",
                        "content_hash": content_hash(content),
                        "absolute_path": str(candidate),
                    }
                )
        return discovered

    def _default_scan_roots(self, project_id: ProjectId, project_root: Path | None) -> list[str]:
        roots: list[str] = []
        if project_root is not None:
            roots.append(str(project_root))
            server_data = project_root / "server-data"
            if server_data.exists():
                roots.append(str(server_data))
        roots.extend(self._project_scan_roots(project_id))
        return list(dict.fromkeys(roots))

    def _project_root(self, project_id: ProjectId) -> Path | None:
        with self._container.session_factory() as session:
            paths = session.execute(select(ProjectPathRecord).where(ProjectPathRecord.project_id == str(project_id))).scalars()
            for record in paths:
                if record.path_role == "root":
                    return Path(record.absolute_path).resolve()
        return None

    def _relative_config_path(self, project_root: Path | None, absolute: Path) -> str:
        resolved = absolute.resolve()
        if project_root is not None:
            try:
                return str(resolved.relative_to(project_root.resolve())).replace("\\", "/")
            except ValueError:
                pass
        return resolved.name

    def _project_scan_roots(self, project_id: ProjectId) -> list[str]:
        with self._container.session_factory() as session:
            paths = session.execute(select(ProjectPathRecord).where(ProjectPathRecord.project_id == str(project_id))).scalars()
            return [record.absolute_path for record in paths if record.path_role in {"server_data", "root", "project_root"}]

    def _absolute_path(self, project_id: ProjectId, relative_path: str) -> Path:
        project_root = self._project_root(project_id)
        if project_root is None:
            raise ConfigApplicationError(ErrorCode.PRECONDITION_FAILED, "Project has no root path")
        return (project_root / relative_path).resolve()

    def _get_config_record(self, project_id: ProjectId, config_file_id: str):
        with self._container.session_factory() as session:
            record = ConfigRepository(RepositoryContext(session=session, project_id=project_id)).get_config_file(project_id, StableIdentifier(config_file_id))
            if record is None:
                raise ConfigApplicationError(ErrorCode.NOT_FOUND, f"Config file not found: {config_file_id}")
            return record

    def _list_records(self, project_id: ProjectId):
        with self._container.session_factory() as session:
            return ConfigRepository(RepositoryContext(session=session, project_id=project_id)).list_config_files(project_id)

    def _list_snapshots(self, project_id: ProjectId, config_file_id: str) -> list[dict[str, Any]]:
        with self._container.session_factory() as session:
            return [_snapshot_data(record) for record in ConfigRepository(RepositoryContext(session=session, project_id=project_id)).list_snapshots(config_file_id)]

    def _get_snapshot(self, project_id: ProjectId, snapshot_id: str):
        with self._container.session_factory() as session:
            snapshot = ConfigRepository(RepositoryContext(session=session, project_id=project_id)).get_snapshot(StableIdentifier(snapshot_id))
            if snapshot is None:
                raise ConfigApplicationError(ErrorCode.NOT_FOUND, f"Snapshot not found: {snapshot_id}")
            return snapshot

    def _require_project(self, repository: ProjectRepository, project_id: ProjectId) -> None:
        if repository.get_project(project_id) is None:
            raise ConfigApplicationError(ErrorCode.NOT_FOUND, f"Project not found: {project_id}")


def _config_file_data(record: Any) -> dict[str, Any]:
    return {
        "config_file_id": record.config_file_id,
        "project_id": record.project_id,
        "path": record.path,
        "config_type": record.config_type,
        "content_hash": record.content_hash,
        "last_scanned_at": record.last_scanned_at,
    }


def _snapshot_data(record: Any) -> dict[str, Any]:
    return {
        "config_snapshot_id": record.config_snapshot_id,
        "config_file_id": record.config_file_id,
        "snapshot_kind": record.snapshot_kind,
        "content_hash": record.content_hash,
        "captured_at": record.captured_at,
    }


def _finding_data(item: Any) -> dict[str, Any]:
    return {
        "rule_id": item.rule_id,
        "severity": item.severity.value if hasattr(item.severity, "value") else item.severity,
        "message": item.message,
        "path": item.path,
        "line": item.line,
        "column": item.column,
        "details": item.details,
    }


def _secret_data(item: Any) -> dict[str, Any]:
    return {
        "detector_id": item.detector_id,
        "severity": item.severity.value if hasattr(item.severity, "value") else item.severity,
        "path": item.path,
        "line": item.line,
        "redacted_preview": item.redacted_preview,
        "secret_type": item.secret_type,
    }


def _validation_finding_data(record: Any) -> dict[str, Any]:
    return {
        "finding_id": record.finding_id,
        "severity": record.severity,
        "rule_id": record.rule_id,
        "path": record.path,
        "line": record.line,
        "message": record.message,
        "details": record.details_json or {},
    }


def _secret_record_data(record: Any) -> dict[str, Any]:
    return {
        "secret_finding_id": record.secret_finding_id,
        "project_id": record.project_id,
        "config_file_id": record.config_file_id,
        "detector_id": record.detector_id,
        "severity": record.severity,
        "path": record.path,
        "line": record.line,
        "redacted_preview": record.redacted_preview,
        "status": record.status,
        "secret_type": (record.metadata_json or {}).get("secret_type"),
    }
