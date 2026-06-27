from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from backend.adapters.filesystem.backup_archive import BackupArchiveAdapter
from backend.adapters.persistence import BackupRepository, ProjectRepository, SetupRepository
from backend.application.commands import CommandContext, CommandPreview, RiskLevel, UndoPlan
from backend.application.commands.compensation import CompositeCompensation, RestorePathFromSnapshotCompensation
from backend.application.commands.recorder import CommandAuditRecorder
from backend.application.commands.serialization import compensation_from_storage, compensation_to_storage
from backend.domain.backup import (
    BackupItemType,
    BackupRunStatus,
    BackupScope,
    BackupTriggerType,
    RestoreRunStatus,
    RetentionEventType,
    assess_backup_consistency,
    backup_completed,
    backup_failed,
    backup_pruned,
    evaluate_retention,
    restore_completed,
)
from backend.domain.shared_kernel import ErrorCode, ProjectId, StableIdentifier
from backend.infrastructure.unit_of_work import RepositoryContext, sqlite_database_path


EXCLUDE_DIRS = {".atlas-snapshots", "backups", "__pycache__"}


class BackupApplicationError(RuntimeError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


class BackupApplicationService:
    def __init__(self, *, container: Any, clock: Callable[[], datetime] | None = None) -> None:
        self._container = container
        self._clock = clock or (lambda: datetime.now(UTC))
        self._archive = BackupArchiveAdapter()
        self._recorder = CommandAuditRecorder()

    def create_plan(
        self,
        project_id: ProjectId,
        *,
        name: str,
        backup_scope: str = BackupScope.FULL.value,
        retention_policy: dict[str, Any] | None = None,
        schedule_interval_seconds: int | None = None,
        is_enabled: bool = True,
    ) -> dict[str, Any]:
        now = self._clock()
        plan_id = StableIdentifier.new()
        policy = retention_policy or {"keep_count": 5, "keep_days": 30}
        next_run = now if schedule_interval_seconds else None
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(BackupRepository)
            uow.repository(ProjectRepository).get_project(project_id) or self._missing_project(project_id)
            record = repository.create_plan(
                plan_id=plan_id,
                project_id=project_id,
                name=name,
                backup_scope=backup_scope,
                retention_policy_json=policy,
                schedule_interval_seconds=schedule_interval_seconds,
                next_run_at=next_run,
                is_enabled=is_enabled,
                created_at=now,
            )
            uow.commit()
        return _plan_data(record)

    def list_plans(self, project_id: ProjectId) -> list[dict[str, Any]]:
        with self._container.session_factory() as session:
            records = BackupRepository(RepositoryContext(session=session, project_id=project_id)).list_plans(project_id)
        return [_plan_data(record) for record in records]

    def get_plan(self, project_id: ProjectId, plan_id: str) -> dict[str, Any]:
        with self._container.session_factory() as session:
            plan = BackupRepository(RepositoryContext(session=session, project_id=project_id)).get_plan(project_id, plan_id)
            if not plan:
                raise BackupApplicationError(ErrorCode.NOT_FOUND, f"Backup plan not found: {plan_id}")
            return _plan_data(plan)

    def update_plan(
        self,
        project_id: ProjectId,
        plan_id: str,
        *,
        retention_policy: dict[str, Any] | None = None,
        schedule_interval_seconds: int | None = None,
        is_enabled: bool | None = None,
    ) -> dict[str, Any]:
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(BackupRepository)
            plan = repository.get_plan(project_id, plan_id)
            if not plan:
                raise BackupApplicationError(ErrorCode.NOT_FOUND, f"Backup plan not found: {plan_id}")

            if retention_policy is not None:
                plan.retention_policy_json = retention_policy
            if schedule_interval_seconds is not None:
                plan.schedule_interval_seconds = schedule_interval_seconds
            if is_enabled is not None:
                plan.is_enabled = 1 if is_enabled else 0

            plan.updated_at = self._clock().isoformat()
            uow.commit()

        if retention_policy is not None:
            self.evaluate_retention(project_id, plan_id=plan_id)

        return self.get_plan(project_id, plan_id)

    def list_runs(self, project_id: ProjectId, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._container.session_factory() as session:
            repository = BackupRepository(RepositoryContext(session=session, project_id=project_id))
            return [_run_data(run) for run in repository.list_runs(project_id, limit=limit)]

    def get_run(self, project_id: ProjectId, backup_run_id: str) -> dict[str, Any]:
        with self._container.session_factory() as session:
            repository = BackupRepository(RepositoryContext(session=session, project_id=project_id))
            run = repository.get_run(project_id, backup_run_id)
            if run is None:
                raise BackupApplicationError(ErrorCode.NOT_FOUND, f"Backup run not found: {backup_run_id}")
            items = repository.list_items(backup_run_id)
        return {**_run_data(run), "items": [_item_data(item) for item in items]}

    def execute_run_backup(
        self,
        project_id: ProjectId,
        *,
        plan_id: str | None = None,
        trigger_type: str = BackupTriggerType.MANUAL.value,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        now = self._clock()
        key = idempotency_key or f"backup:{project_id}:{now.isoformat()}"
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(BackupRepository)
            existing = repository.get_run_by_idempotency(key)
            if existing is not None:
                uow.commit()
                return _run_data(existing)
            run_id = StableIdentifier.new()
            repository.create_run(
                run_id=run_id,
                project_id=project_id,
                backup_plan_id=plan_id,
                status=BackupRunStatus.RUNNING.value,
                trigger_type=trigger_type,
                idempotency_key=key,
                started_at=now,
            )
            uow.commit()
        try:
            result = self._capture_backup(project_id, str(run_id), plan_id=plan_id)
        except Exception as error:
            self._fail_run(project_id, str(run_id), str(error))
            raise BackupApplicationError(ErrorCode.EXTERNAL_ADAPTER_FAILED, str(error)) from error
        return result

    def preview_restore(self, project_id: ProjectId, backup_run_id: str) -> dict[str, Any]:
        run = self._require_succeeded_run(project_id, backup_run_id)
        project_root = self._project_root(project_id)
        manifest = run.manifest_json or {}
        paths = manifest.get("files", [])
        warnings: list[str] = []
        if manifest.get("consistency", {}).get("warning"):
            warnings.append(str(manifest["consistency"]["warning"]))
        warnings.append("Restore will overwrite current project files with backup contents.")
        return {
            "backup_run_id": backup_run_id,
            "project_root": str(project_root),
            "overwrite_paths": paths,
            "warnings": warnings,
            "requires_pre_restore_snapshot": True,
        }

    def execute_restore(
        self,
        project_id: ProjectId,
        backup_run_id: str,
        *,
        confirm_destructive: bool = False,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        preview = self.preview_restore(project_id, backup_run_id)
        run = self._require_succeeded_run(project_id, backup_run_id)
        project_root = self._project_root(project_id)
        archive_path = Path(run.archive_path or "")
        if not archive_path.exists():
            raise BackupApplicationError(ErrorCode.NOT_FOUND, f"Backup archive missing: {archive_path}")
        restore_id = StableIdentifier.new()
        snapshot_path = self._pre_restore_snapshot_path(project_id, str(restore_id))
        now = self._clock()
        try:
            self._archive.snapshot_tree(project_root, snapshot_path)
            snapshot_ok = snapshot_path.exists()
        except OSError as error:
            snapshot_ok = False
            if not confirm_destructive:
                raise BackupApplicationError(
                    ErrorCode.PRECONDITION_FAILED,
                    f"Cannot snapshot current state before restore: {error}. Set confirm_destructive=true to proceed.",
                ) from error
        if not snapshot_ok and not confirm_destructive:
            raise BackupApplicationError(
                ErrorCode.PRECONDITION_FAILED,
                "Pre-restore snapshot failed. Set confirm_destructive=true to proceed without undo guarantee.",
            )
        compensation = RestorePathFromSnapshotCompensation(str(snapshot_path), str(project_root))
        undo_plan = UndoPlan(
            command_type="backup.restore",
            summary="Restore project state from pre-restore snapshot",
            action=CompositeCompensation((compensation,)),
            payload=compensation.describe(),
        )
        preview_cmd = CommandPreview(
            command_type="backup.restore",
            summary=f"Restore backup {backup_run_id}",
            preview=preview,
            warnings=preview.get("warnings", []),
            risk_level=RiskLevel.DESTRUCTIVE,
        )
        self._archive.extract_zip_archive(archive_path, project_root)
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(BackupRepository)
            restore = repository.create_restore_run(
                restore_id=restore_id,
                backup_run_id=backup_run_id,
                project_id=project_id,
                status=RestoreRunStatus.RUNNING.value,
                dry_run=False,
                restore_plan_json=preview,
                started_at=now,
            )
            execution = self._recorder.record_success(
                uow=uow,
                preview=preview_cmd,
                project_id=project_id,
                entity_type="backup_restore",
                entity_id=str(restore_id),
                summary=preview_cmd.summary,
                result={"backup_run_id": backup_run_id, "restored_files": preview["overwrite_paths"]},
                events=[],
                undo_plan=undo_plan,
                idempotency_key=idempotency_key,
            )
            uow.session.flush()
            repository.finish_restore_run(
                restore,
                status=RestoreRunStatus.SUCCEEDED.value,
                finished_at=self._clock(),
                command_execution_id=str(execution.command_execution_id),
                pre_restore_snapshot_path=str(snapshot_path) if snapshot_ok else None,
                undo_plan_json=_serialize_undo(undo_plan),
            )
            uow.collect_event(restore_completed(project_id, str(restore_id), backup_run_id))
            uow.commit()
        return {
            "restore_run_id": str(restore_id),
            "status": RestoreRunStatus.SUCCEEDED.value,
            "command_execution_id": str(execution.command_execution_id),
            "pre_restore_snapshot_path": str(snapshot_path) if snapshot_ok else None,
            "undo_available": snapshot_ok,
        }

    def undo_restore(self, project_id: ProjectId, restore_run_id: str) -> dict[str, Any]:
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(BackupRepository)
            restore = repository.get_restore_run(project_id, restore_run_id)
            if restore is None or not restore.undo_plan_json:
                uow.rollback()
                raise BackupApplicationError(ErrorCode.NOT_FOUND, "Restore undo not available")
            action = compensation_from_storage(restore.undo_plan_json, filesystem=self._container.setup_filesystem)
            context = CommandContext(uow=uow)
            result = action.apply(context)
            uow.commit()
        return {"restore_run_id": restore_run_id, "undo_result": result}

    def evaluate_retention(self, project_id: ProjectId, *, plan_id: str | None = None) -> dict[str, Any]:
        now = self._clock()
        with self._container.session_factory() as session:
            repository = BackupRepository(RepositoryContext(session=session, project_id=project_id))
            plan = repository.get_plan(project_id, plan_id) if plan_id else None
            policy = (plan.retention_policy_json if plan else None) or {"keep_count": 5, "keep_days": 30}
            runs = [
                {"backup_run_id": run.backup_run_id, "status": run.status, "started_at": run.started_at}
                for run in repository.list_succeeded_runs(project_id)
            ]
        decisions = evaluate_retention(runs, policy=policy, now=now)
        pruned: list[str] = []
        skipped: list[str] = []
        for decision in decisions:
            if decision.action == "prune":
                self._prune_run(project_id, decision.backup_run_id, reason=decision.reason, plan_id=plan_id)
                pruned.append(decision.backup_run_id)
            else:
                skipped.append(decision.backup_run_id)
                self._record_retention_event(
                    project_id,
                    event_type=RetentionEventType.SKIPPED.value,
                    backup_run_id=decision.backup_run_id,
                    plan_id=plan_id,
                    reason=decision.reason,
                )
        return {"pruned": pruned, "skipped": skipped, "evaluated": len(decisions)}

    def _capture_backup(self, project_id: ProjectId, run_id: str, *, plan_id: str | None) -> dict[str, Any]:
        now = self._clock()
        project_root = self._project_root(project_id)
        server_running = self._server_running(project_id)
        consistency = assess_backup_consistency(server_running=server_running)
        staging = self._staging_dir(project_id, run_id)
        archive_path = self._archive_path(project_id, run_id)
        items: list[dict[str, Any]] = []
        if staging.exists():
            shutil_rmtree(staging)
        staging.mkdir(parents=True)
        copied = self._archive.copy_tree_into(project_root, staging / "project", exclude_names=EXCLUDE_DIRS)
        for entry in copied:
            relative = entry["relative_path"]
            item_type = BackupItemType.DATABASE.value if str(relative).endswith(".db") else (
                BackupItemType.CONFIG.value if "server-data" in str(relative) else BackupItemType.RESOURCE.value
            )
            items.append({"item_type": item_type, "source_path": relative, "size_bytes": entry["size_bytes"]})
        db_files = [path for path in project_root.rglob("*.db") if not any(part in EXCLUDE_DIRS for part in path.parts)]
        for db_path in db_files:
            if sqlite_database_path(self._container.app_data_dir).resolve() == db_path.resolve():
                continue
            rel = db_path.relative_to(project_root).as_posix()
            staged_db = staging / "project" / rel
            staged_db.parent.mkdir(parents=True, exist_ok=True)
            self._archive.sqlite_backup_file(db_path, staged_db)
            items.append({"item_type": BackupItemType.DATABASE.value, "source_path": rel, "size_bytes": staged_db.stat().st_size, "method": "sqlite_backup_api"})
        manifest = {
            "files": [item["source_path"] for item in items],
            "consistency": consistency,
            "captured_at": now.isoformat(),
        }
        self._publish_progress(project_id, run_id, "Compressing backup archive")
        self._archive.create_zip_archive(staging / "project", archive_path)
        checksum = self._archive.sha256_file(archive_path)
        self._publish_progress(project_id, run_id, "Backup capture complete")
        shutil_rmtree(staging)
        finished = self._clock()
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(BackupRepository)
            run = repository.get_run(project_id, run_id)
            assert run is not None
            for item in items:
                repository.add_item(
                    item_id=StableIdentifier.new(),
                    run_id=run_id,
                    item_type=item["item_type"],
                    source_path=item["source_path"],
                    content_hash=None,
                    size_bytes=int(item.get("size_bytes") or 0),
                    metadata_json={key: value for key, value in item.items() if key not in {"item_type", "source_path", "size_bytes"}},
                )
            repository.finish_run(
                run,
                status=BackupRunStatus.SUCCEEDED.value,
                finished_at=finished,
                total_bytes=archive_path.stat().st_size,
                archive_path=str(archive_path),
                content_hash=checksum,
                manifest_json=manifest,
            )
            uow.collect_event(backup_completed(project_id, run_id, total_bytes=archive_path.stat().st_size, checksum=checksum))
            uow.commit()
        warnings = [consistency["warning"]] if consistency.get("warning") else []
        return {
            "backup_run_id": run_id,
            "project_id": str(project_id),
            "status": BackupRunStatus.SUCCEEDED.value,
            "total_bytes": archive_path.stat().st_size,
            "content_hash": checksum,
            "archive_path": str(archive_path),
            "manifest_json": manifest,
            "warnings": warnings,
            "items": items,
        }

    def _fail_run(self, project_id: ProjectId, run_id: str, reason: str) -> None:
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(BackupRepository)
            run = repository.get_run(project_id, run_id)
            if run is not None:
                repository.finish_run(run, status=BackupRunStatus.FAILED.value, finished_at=self._clock())
                uow.collect_event(backup_failed(project_id, run_id, reason))
            uow.commit()

    def _prune_run(self, project_id: ProjectId, backup_run_id: str, *, reason: str, plan_id: str | None) -> None:
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(BackupRepository)
            run = repository.get_run(project_id, backup_run_id)
            if run is None:
                uow.rollback()
                return
            if run.archive_path:
                path = Path(run.archive_path)
                if path.exists():
                    path.unlink()
            repository.finish_run(run, status=BackupRunStatus.PRUNED.value, finished_at=self._clock())
            repository.add_retention_event(
                event_id=StableIdentifier.new(),
                project_id=project_id,
                event_type=RetentionEventType.PRUNED.value,
                backup_plan_id=plan_id,
                backup_run_id=backup_run_id,
                reason=reason,
                occurred_at=self._clock(),
            )
            uow.collect_event(backup_pruned(project_id, backup_run_id, reason))
            uow.commit()

    def _record_retention_event(
        self,
        project_id: ProjectId,
        *,
        event_type: str,
        backup_run_id: str,
        plan_id: str | None,
        reason: str,
    ) -> None:
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            uow.repository(BackupRepository).add_retention_event(
                event_id=StableIdentifier.new(),
                project_id=project_id,
                event_type=event_type,
                backup_plan_id=plan_id,
                backup_run_id=backup_run_id,
                reason=reason,
                occurred_at=self._clock(),
            )
            uow.commit()

    def _server_running(self, project_id: ProjectId) -> bool:
        with self._container.session_factory() as session:
            current = SetupRepository(RepositoryContext(session=session, project_id=project_id)).current_process_run(project_id)
        return current is not None

    def _project_root(self, project_id: ProjectId) -> Path:
        with self._container.session_factory() as session:
            paths = ProjectRepository(RepositoryContext(session=session, project_id=project_id)).list_paths(project_id, role="root")
        if not paths:
            raise BackupApplicationError(ErrorCode.NOT_FOUND, f"Project root not found: {project_id}")
        return Path(paths[0].absolute_path)

    def _backup_root(self) -> Path:
        return self._container.app_data_dir / "backups"

    def _archive_path(self, project_id: ProjectId, run_id: str) -> Path:
        return self._backup_root() / str(project_id) / f"{run_id}.zip"

    def _staging_dir(self, project_id: ProjectId, run_id: str) -> Path:
        return self._backup_root() / "staging" / str(project_id) / run_id

    def _pre_restore_snapshot_path(self, project_id: ProjectId, restore_id: str) -> Path:
        root = self._project_root(project_id)
        return root.parent / ".atlas-snapshots" / str(project_id) / f"pre-restore-{restore_id}"

    def _require_succeeded_run(self, project_id: ProjectId, backup_run_id: str):
        with self._container.session_factory() as session:
            run = BackupRepository(RepositoryContext(session=session, project_id=project_id)).get_run(project_id, backup_run_id)
        if run is None or run.status != BackupRunStatus.SUCCEEDED.value:
            raise BackupApplicationError(ErrorCode.NOT_FOUND, f"Backup run not available: {backup_run_id}")
        return run

    def _publish_progress(self, project_id: ProjectId, operation_id: str, message: str) -> None:
        publisher = getattr(self._container, "stream_publisher", None)
        if publisher is not None:
            publisher.publish_operation_progress(project_id=project_id, operation_id=operation_id, message=message)

    def _missing_project(self, project_id: ProjectId) -> None:
        raise BackupApplicationError(ErrorCode.NOT_FOUND, f"Project not found: {project_id}")


def shutil_rmtree(path: Path) -> None:
    import shutil

    if path.exists():
        shutil.rmtree(path)


def _serialize_undo(undo_plan: UndoPlan) -> dict[str, Any]:
    return compensation_to_storage(undo_plan.action)


def _plan_data(record: Any) -> dict[str, Any]:
    return {
        "backup_plan_id": record.backup_plan_id,
        "project_id": record.project_id,
        "name": record.name,
        "backup_scope": record.backup_scope,
        "retention_policy": record.retention_policy_json,
        "schedule_interval_seconds": record.schedule_interval_seconds,
        "next_run_at": record.next_run_at,
        "is_enabled": bool(record.is_enabled),
    }


def _run_data(record: Any) -> dict[str, Any]:
    return {
        "backup_run_id": record.backup_run_id,
        "backup_plan_id": record.backup_plan_id,
        "project_id": record.project_id,
        "status": record.status,
        "trigger_type": record.trigger_type,
        "started_at": record.started_at,
        "finished_at": record.finished_at,
        "total_bytes": record.total_bytes,
        "content_hash": record.content_hash,
        "archive_path": record.archive_path,
        "manifest_json": record.manifest_json,
        "idempotency_key": record.idempotency_key,
    }


def _item_data(record: Any) -> dict[str, Any]:
    return {
        "backup_item_id": record.backup_item_id,
        "item_type": record.item_type,
        "source_path": record.source_path,
        "size_bytes": record.size_bytes,
        "metadata_json": record.metadata_json,
    }
