from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete, select

from backend.adapters.persistence.models import (
    ConfigChangeSetRecord,
    ConfigFileRecord,
    ConfigSnapshotRecord,
    ConfigValidationFindingRecord,
    ConfigValidationRunRecord,
    SecretScanFindingRecord,
)
from backend.domain.shared_kernel import ProjectId, StableIdentifier
from backend.infrastructure.unit_of_work import ProjectScopeRequired, RepositoryContext


class ConfigRepository:
    def __init__(self, context: RepositoryContext) -> None:
        self._session = context.session
        self._project_id = context.project_id

    def upsert_config_file(
        self,
        *,
        config_file_id: StableIdentifier,
        project_id: ProjectId,
        environment_id: str | None,
        path: str,
        config_type: str,
        parser_kind: str | None,
        content_hash: str | None,
        scanned_at: datetime,
    ) -> ConfigFileRecord:
        self._ensure_project_scope(project_id)
        existing = self._session.execute(
            select(ConfigFileRecord).where(
                ConfigFileRecord.project_id == str(project_id),
                ConfigFileRecord.environment_id == environment_id,
                ConfigFileRecord.path == path,
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = ConfigFileRecord(
                config_file_id=str(config_file_id),
                project_id=str(project_id),
                environment_id=environment_id,
                path=path,
                config_type=config_type,
                parser_kind=parser_kind,
                content_hash=content_hash,
                last_scanned_at=scanned_at.isoformat(),
            )
            self._session.add(existing)
            return existing
        existing.config_type = config_type
        existing.parser_kind = parser_kind
        existing.content_hash = content_hash
        existing.last_scanned_at = scanned_at.isoformat()
        return existing

    def list_config_files(self, project_id: ProjectId) -> list[ConfigFileRecord]:
        self._ensure_project_scope(project_id)
        return list(
            self._session.execute(
                select(ConfigFileRecord).where(ConfigFileRecord.project_id == str(project_id)).order_by(ConfigFileRecord.path)
            ).scalars()
        )

    def get_config_file(self, project_id: ProjectId, config_file_id: StableIdentifier) -> ConfigFileRecord | None:
        self._ensure_project_scope(project_id)
        record = self._session.get(ConfigFileRecord, str(config_file_id))
        if record is None or record.project_id != str(project_id):
            return None
        return record

    def add_snapshot(
        self,
        *,
        config_snapshot_id: StableIdentifier,
        config_file_id: str,
        snapshot_kind: str,
        content_hash: str,
        captured_at: datetime,
        metadata: dict[str, Any],
    ) -> ConfigSnapshotRecord:
        record = ConfigSnapshotRecord(
            config_snapshot_id=str(config_snapshot_id),
            config_file_id=config_file_id,
            snapshot_kind=snapshot_kind,
            content_hash=content_hash,
            local_file_id=None,
            captured_at=captured_at.isoformat(),
            metadata_json=metadata,
        )
        self._session.add(record)
        return record

    def get_snapshot(self, config_snapshot_id: StableIdentifier) -> ConfigSnapshotRecord | None:
        return self._session.get(ConfigSnapshotRecord, str(config_snapshot_id))

    def list_snapshots(self, config_file_id: str) -> list[ConfigSnapshotRecord]:
        return list(
            self._session.execute(
                select(ConfigSnapshotRecord)
                .where(ConfigSnapshotRecord.config_file_id == config_file_id)
                .order_by(ConfigSnapshotRecord.captured_at.desc())
            ).scalars()
        )

    def create_change_set(
        self,
        *,
        config_change_set_id: StableIdentifier,
        project_id: ProjectId,
        status: str,
        summary: str | None,
        before_snapshot_id: str | None,
        after_snapshot_id: str | None,
        created_at: datetime,
        command_execution_id: str | None = None,
        applied_at: datetime | None = None,
    ) -> ConfigChangeSetRecord:
        self._ensure_project_scope(project_id)
        record = ConfigChangeSetRecord(
            config_change_set_id=str(config_change_set_id),
            project_id=str(project_id),
            command_execution_id=command_execution_id,
            status=status,
            summary=summary,
            before_snapshot_id=before_snapshot_id,
            after_snapshot_id=after_snapshot_id,
            created_at=created_at.isoformat(),
            applied_at=applied_at.isoformat() if applied_at else None,
        )
        self._session.add(record)
        return record

    def update_change_set_status(self, change_set_id: StableIdentifier, status: str, applied_at: datetime | None = None) -> None:
        record = self._session.get(ConfigChangeSetRecord, str(change_set_id))
        if record is None:
            return
        record.status = status
        if applied_at is not None:
            record.applied_at = applied_at.isoformat()

    def get_change_set(self, project_id: ProjectId, change_set_id: StableIdentifier) -> ConfigChangeSetRecord | None:
        self._ensure_project_scope(project_id)
        record = self._session.get(ConfigChangeSetRecord, str(change_set_id))
        if record is None or record.project_id != str(project_id):
            return None
        return record

    def add_validation_run(
        self,
        *,
        run_id: StableIdentifier,
        project_id: ProjectId,
        config_file_id: str | None,
        validator_id: str,
        status: str,
        started_at: datetime,
        finished_at: datetime,
        summary: dict[str, Any],
    ) -> ConfigValidationRunRecord:
        self._ensure_project_scope(project_id)
        record = ConfigValidationRunRecord(
            config_validation_run_id=str(run_id),
            project_id=str(project_id),
            config_file_id=config_file_id,
            validator_id=validator_id,
            status=status,
            started_at=started_at.isoformat(),
            finished_at=finished_at.isoformat(),
            summary_json=summary,
        )
        self._session.add(record)
        return record

    def add_validation_finding(
        self,
        *,
        finding_id: StableIdentifier,
        run_id: str,
        severity: str,
        rule_id: str,
        path: str | None,
        line: int | None,
        column: int | None,
        message: str,
        details: dict[str, Any] | None,
    ) -> None:
        self._session.add(
            ConfigValidationFindingRecord(
                finding_id=str(finding_id),
                config_validation_run_id=run_id,
                severity=severity,
                rule_id=rule_id,
                path=path,
                line=line,
                column=column,
                message=message,
                details_json=details or {},
            )
        )

    def list_validation_findings(self, project_id: ProjectId) -> list[ConfigValidationFindingRecord]:
        self._ensure_project_scope(project_id)
        return list(
            self._session.execute(
                select(ConfigValidationFindingRecord)
                .join(ConfigValidationRunRecord, ConfigValidationFindingRecord.config_validation_run_id == ConfigValidationRunRecord.config_validation_run_id)
                .where(ConfigValidationRunRecord.project_id == str(project_id))
                .order_by(ConfigValidationFindingRecord.finding_id.desc())
            ).scalars()
        )

    def replace_secret_findings(
        self,
        *,
        project_id: ProjectId,
        config_file_id: str | None,
        findings: list[dict[str, Any]],
        detected_at: datetime,
    ) -> list[SecretScanFindingRecord]:
        self._ensure_project_scope(project_id)
        query = delete(SecretScanFindingRecord).where(
            SecretScanFindingRecord.project_id == str(project_id),
            SecretScanFindingRecord.status == "open",
        )
        if config_file_id is not None:
            query = query.where(SecretScanFindingRecord.config_file_id == config_file_id)
        self._session.execute(query)
        records: list[SecretScanFindingRecord] = []
        for item in findings:
            record = SecretScanFindingRecord(
                secret_finding_id=str(StableIdentifier.new()),
                project_id=str(project_id),
                config_file_id=config_file_id,
                detector_id=item["detector_id"],
                severity=item["severity"],
                path=item.get("path"),
                line=item.get("line"),
                redacted_preview=item.get("redacted_preview"),
                status="open",
                detected_at=detected_at.isoformat(),
                metadata_json={"secret_type": item.get("secret_type")},
            )
            self._session.add(record)
            records.append(record)
        return records

    def list_secret_findings(self, project_id: ProjectId, status: str | None = None) -> list[SecretScanFindingRecord]:
        self._ensure_project_scope(project_id)
        query = select(SecretScanFindingRecord).where(SecretScanFindingRecord.project_id == str(project_id))
        if status is not None:
            query = query.where(SecretScanFindingRecord.status == status)
        return list(self._session.execute(query.order_by(SecretScanFindingRecord.detected_at.desc())).scalars())

    def _ensure_project_scope(self, project_id: ProjectId) -> None:
        if self._project_id is not None and self._project_id != project_id:
            raise ProjectScopeRequired("Repository project_id does not match requested project_id")
