from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select

from backend.adapters.persistence.models import (
    BackupItemRecord,
    BackupPlanRecord,
    BackupRestoreRunRecord,
    BackupRetentionEventRecord,
    BackupRunRecord,
)
from backend.domain.shared_kernel import ProjectId, StableIdentifier
from backend.infrastructure.unit_of_work import ProjectScopeRequired, RepositoryContext


class BackupRepository:
    def __init__(self, context: RepositoryContext) -> None:
        self._session = context.session
        self._project_id = context.project_id

    def create_plan(
        self,
        *,
        plan_id: StableIdentifier,
        project_id: ProjectId,
        name: str,
        backup_scope: str,
        retention_policy_json: dict[str, Any],
        schedule_interval_seconds: int | None,
        next_run_at: datetime | None,
        is_enabled: bool,
        created_at: datetime,
    ) -> BackupPlanRecord:
        self._ensure_project_scope(project_id)
        record = BackupPlanRecord(
            backup_plan_id=str(plan_id),
            project_id=str(project_id),
            name=name,
            backup_scope=backup_scope,
            retention_policy_json=retention_policy_json,
            schedule_interval_seconds=schedule_interval_seconds,
            next_run_at=next_run_at.isoformat() if next_run_at else None,
            is_enabled=1 if is_enabled else 0,
            created_at=created_at.isoformat(),
            updated_at=created_at.isoformat(),
        )
        self._session.add(record)
        return record

    def get_plan(self, project_id: ProjectId, plan_id: str) -> BackupPlanRecord | None:
        self._ensure_project_scope(project_id)
        return self._session.execute(
            select(BackupPlanRecord).where(
                BackupPlanRecord.project_id == str(project_id),
                BackupPlanRecord.backup_plan_id == plan_id,
            )
        ).scalar_one_or_none()

    def list_plans(self, project_id: ProjectId) -> list[BackupPlanRecord]:
        self._ensure_project_scope(project_id)
        return list(
            self._session.execute(
                select(BackupPlanRecord).where(BackupPlanRecord.project_id == str(project_id)).order_by(BackupPlanRecord.name)
            ).scalars()
        )

    def list_due_plans(self, *, before: datetime) -> list[BackupPlanRecord]:
        return list(
            self._session.execute(
                select(BackupPlanRecord).where(
                    BackupPlanRecord.is_enabled == 1,
                    BackupPlanRecord.next_run_at.is_not(None),
                    BackupPlanRecord.next_run_at <= before.isoformat(),
                )
            ).scalars()
        )

    def advance_plan_schedule(self, plan: BackupPlanRecord, *, next_run_at: datetime, last_run_at: datetime) -> None:
        plan.next_run_at = next_run_at.isoformat()
        plan.last_run_at = last_run_at.isoformat()
        plan.updated_at = last_run_at.isoformat()

    def get_run_by_idempotency(self, idempotency_key: str) -> BackupRunRecord | None:
        if not idempotency_key:
            return None
        return self._session.execute(
            select(BackupRunRecord).where(BackupRunRecord.idempotency_key == idempotency_key)
        ).scalar_one_or_none()

    def create_run(
        self,
        *,
        run_id: StableIdentifier,
        project_id: ProjectId,
        backup_plan_id: str | None,
        status: str,
        trigger_type: str,
        idempotency_key: str | None,
        started_at: datetime,
    ) -> BackupRunRecord:
        self._ensure_project_scope(project_id)
        record = BackupRunRecord(
            backup_run_id=str(run_id),
            backup_plan_id=backup_plan_id,
            project_id=str(project_id),
            status=status,
            trigger_type=trigger_type,
            idempotency_key=idempotency_key,
            started_at=started_at.isoformat(),
        )
        self._session.add(record)
        return record

    def finish_run(
        self,
        run: BackupRunRecord,
        *,
        status: str,
        finished_at: datetime,
        total_bytes: int | None = None,
        archive_path: str | None = None,
        content_hash: str | None = None,
        manifest_json: dict[str, Any] | None = None,
    ) -> None:
        run.status = status
        run.finished_at = finished_at.isoformat()
        if total_bytes is not None:
            run.total_bytes = total_bytes
        if archive_path is not None:
            run.archive_path = archive_path
        if content_hash is not None:
            run.content_hash = content_hash
        if manifest_json is not None:
            run.manifest_json = manifest_json

    def list_runs(self, project_id: ProjectId, *, limit: int = 50) -> list[BackupRunRecord]:
        self._ensure_project_scope(project_id)
        return list(
            self._session.execute(
                select(BackupRunRecord)
                .where(BackupRunRecord.project_id == str(project_id))
                .order_by(BackupRunRecord.started_at.desc())
                .limit(limit)
            ).scalars()
        )

    def list_succeeded_runs(self, project_id: ProjectId) -> list[BackupRunRecord]:
        self._ensure_project_scope(project_id)
        return list(
            self._session.execute(
                select(BackupRunRecord)
                .where(BackupRunRecord.project_id == str(project_id), BackupRunRecord.status == "succeeded")
                .order_by(BackupRunRecord.started_at.desc())
            ).scalars()
        )

    def get_run(self, project_id: ProjectId, run_id: str) -> BackupRunRecord | None:
        self._ensure_project_scope(project_id)
        return self._session.execute(
            select(BackupRunRecord).where(
                BackupRunRecord.project_id == str(project_id),
                BackupRunRecord.backup_run_id == run_id,
            )
        ).scalar_one_or_none()

    def add_item(
        self,
        *,
        item_id: StableIdentifier,
        run_id: str,
        item_type: str,
        source_path: str | None,
        content_hash: str | None,
        size_bytes: int | None,
        metadata_json: dict[str, Any] | None = None,
    ) -> BackupItemRecord:
        record = BackupItemRecord(
            backup_item_id=str(item_id),
            backup_run_id=run_id,
            item_type=item_type,
            source_path=source_path,
            content_hash=content_hash,
            size_bytes=size_bytes,
            metadata_json=metadata_json or {},
        )
        self._session.add(record)
        return record

    def list_items(self, run_id: str) -> list[BackupItemRecord]:
        return list(
            self._session.execute(select(BackupItemRecord).where(BackupItemRecord.backup_run_id == run_id)).scalars()
        )

    def create_restore_run(
        self,
        *,
        restore_id: StableIdentifier,
        backup_run_id: str,
        project_id: ProjectId,
        status: str,
        dry_run: bool,
        restore_plan_json: dict[str, Any],
        started_at: datetime,
    ) -> BackupRestoreRunRecord:
        self._ensure_project_scope(project_id)
        record = BackupRestoreRunRecord(
            restore_run_id=str(restore_id),
            backup_run_id=backup_run_id,
            project_id=str(project_id),
            status=status,
            dry_run=1 if dry_run else 0,
            restore_plan_json=restore_plan_json,
            started_at=started_at.isoformat(),
        )
        self._session.add(record)
        return record

    def finish_restore_run(
        self,
        restore: BackupRestoreRunRecord,
        *,
        status: str,
        finished_at: datetime,
        command_execution_id: str | None = None,
        pre_restore_snapshot_path: str | None = None,
        undo_plan_json: dict[str, Any] | None = None,
    ) -> None:
        restore.status = status
        restore.finished_at = finished_at.isoformat()
        if command_execution_id is not None:
            restore.command_execution_id = command_execution_id
        if pre_restore_snapshot_path is not None:
            restore.pre_restore_snapshot_path = pre_restore_snapshot_path
        if undo_plan_json is not None:
            restore.undo_plan_json = undo_plan_json

    def get_restore_run(self, project_id: ProjectId, restore_id: str) -> BackupRestoreRunRecord | None:
        self._ensure_project_scope(project_id)
        return self._session.execute(
            select(BackupRestoreRunRecord).where(
                BackupRestoreRunRecord.project_id == str(project_id),
                BackupRestoreRunRecord.restore_run_id == restore_id,
            )
        ).scalar_one_or_none()

    def list_restore_runs(self, project_id: ProjectId) -> list[BackupRestoreRunRecord]:
        self._ensure_project_scope(project_id)
        return list(
            self._session.execute(
                select(BackupRestoreRunRecord)
                .where(BackupRestoreRunRecord.project_id == str(project_id))
                .order_by(BackupRestoreRunRecord.started_at.desc())
            ).scalars()
        )

    def add_retention_event(
        self,
        *,
        event_id: StableIdentifier,
        project_id: ProjectId,
        event_type: str,
        occurred_at: datetime,
        backup_plan_id: str | None = None,
        backup_run_id: str | None = None,
        reason: str | None = None,
        details_json: dict[str, Any] | None = None,
    ) -> BackupRetentionEventRecord:
        self._ensure_project_scope(project_id)
        record = BackupRetentionEventRecord(
            retention_event_id=str(event_id),
            backup_plan_id=backup_plan_id,
            backup_run_id=backup_run_id,
            project_id=str(project_id),
            event_type=event_type,
            reason=reason,
            occurred_at=occurred_at.isoformat(),
            details_json=details_json or {},
        )
        self._session.add(record)
        return record

    def _ensure_project_scope(self, project_id: ProjectId) -> None:
        if self._project_id is not None and self._project_id != project_id:
            raise ProjectScopeRequired("Repository project scope does not match requested project_id")
