from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import func, select

from backend.adapters.persistence import BackupRepository, SetupRepository
from backend.adapters.persistence.models import BackupRunRecord, TelemetryQueueRecord, TelemetryRejectionRecord
from backend.domain.automation.types import ActionType, RecipeKey
from backend.domain.shared_kernel import ProjectId, StableIdentifier
from backend.infrastructure.di import create_application_container
from backend.infrastructure.unit_of_work import RepositoryContext


def test_backup_captures_files_config_and_db_with_checksum(tmp_path: Path) -> None:
    container, project_id, root = _fixture(tmp_path)
    backup = container.create_backup_service()
    try:
        (root / "server-data" / "server.cfg").write_text("endpoint_add_tcp 30120", encoding="utf-8")
        (root / "resources" / "alpha" / "fxmanifest.lua").parent.mkdir(parents=True, exist_ok=True)
        (root / "resources" / "alpha" / "fxmanifest.lua").write_text("fx_version 'cerulean'", encoding="utf-8")
        _create_project_sqlite(root / "data" / "project.db", table="players", value="seed")
        result = backup.execute_run_backup(project_id, idempotency_key="backup:manual:1")
        assert result["status"] == "succeeded"
        assert result["content_hash"]
        assert Path(result["archive_path"]).exists()
        assert Path(result["archive_path"]).stat().st_size > 0
        detail = backup.get_run(project_id, result["backup_run_id"])
        item_types = {item["item_type"] for item in detail["items"]}
        assert "config" in item_types
        assert "resource" in item_types
        assert "database" in item_types
    finally:
        container.close()


def test_hot_backup_warns_when_server_running(tmp_path: Path) -> None:
    container, project_id, root = _fixture(tmp_path)
    backup = container.create_backup_service()
    now = datetime.now(UTC)
    try:
        with container.create_unit_of_work(project_id) as uow:
            uow.begin()
            uow.repository(SetupRepository).add_process_run(
                process_run_id=StableIdentifier.new(),
                project_id=project_id,
                pid=4242,
                state="running",
                launch={"fxserver_path": str(root / "FXServer.exe")},
                started_at=now,
            )
            uow.commit()
        result = backup.execute_run_backup(project_id, idempotency_key="backup:hot:1")
        assert result["warnings"]
        assert "running" in result["warnings"][0].lower()
        manifest = result["manifest_json"]
        assert manifest["consistency"]["guarantee"] == "best_effort"
        assert manifest["consistency"]["server_running"] is True
    finally:
        container.close()


def test_restore_preview_lists_overwrite_paths(tmp_path: Path) -> None:
    container, project_id, root = _fixture(tmp_path)
    backup = container.create_backup_service()
    try:
        marker = root / "server-data" / "server.cfg"
        marker.write_text("original", encoding="utf-8")
        run = backup.execute_run_backup(project_id, idempotency_key="backup:preview:1")
        marker.write_text("mutated", encoding="utf-8")
        preview = backup.preview_restore(project_id, run["backup_run_id"])
        assert any("server.cfg" in path for path in preview["overwrite_paths"])
        assert preview["requires_pre_restore_snapshot"] is True
    finally:
        container.close()


def test_reversible_restore_undo_returns_exact_pre_restore_bytes(tmp_path: Path) -> None:
    container, project_id, root = _fixture(tmp_path)
    backup = container.create_backup_service()
    try:
        cfg = root / "server-data" / "server.cfg"
        resource = root / "resources" / "alpha" / "fxmanifest.lua"
        resource.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text("version-one\n", encoding="utf-8")
        resource.write_text("resource-version-one\n", encoding="utf-8")
        run = backup.execute_run_backup(project_id, idempotency_key="backup:restore:1")

        pre_restore_cfg = b"post-backup-cfg\n"
        pre_restore_resource = b"post-backup-resource\n"
        cfg.write_bytes(pre_restore_cfg)
        resource.write_bytes(pre_restore_resource)
        pre_restore_tree = _tree_digest(root)

        restore = backup.execute_restore(project_id, run["backup_run_id"], idempotency_key="restore:1")
        assert restore["undo_available"] is True
        assert cfg.read_bytes() != pre_restore_cfg

        undo = backup.undo_restore(project_id, restore["restore_run_id"])
        assert undo["undo_result"]["steps"][0]["restored"] is True
        assert cfg.read_bytes() == pre_restore_cfg
        assert resource.read_bytes() == pre_restore_resource
        assert _tree_digest(root) == pre_restore_tree
    finally:
        container.close()


def test_restore_without_snapshot_requires_confirm(tmp_path: Path) -> None:
    container, project_id, _root = _fixture(tmp_path)
    backup = container.create_backup_service()
    try:
        run = backup.execute_run_backup(project_id, idempotency_key="backup:nosnap:1")
        with patch.object(backup._archive, "snapshot_tree", side_effect=OSError("snapshot denied")):
            try:
                backup.execute_restore(project_id, run["backup_run_id"])
            except Exception as error:  # noqa: BLE001
                assert "confirm_destructive" in str(error).lower() or "snapshot" in str(error).lower()
            else:
                raise AssertionError("restore should require confirmation when snapshot fails")
    finally:
        container.close()


def test_retention_prunes_idempotently_and_protects_last_backup(tmp_path: Path) -> None:
    container, project_id, _root = _fixture(tmp_path)
    backup = container.create_backup_service()
    clock = _AdvancingClock(datetime(2026, 1, 1, tzinfo=UTC))
    backup._clock = clock.advance
    try:
        plan = backup.create_plan(
            project_id,
            name="retention",
            retention_policy={"keep_count": 2, "keep_days": 30},
        )
        for index in range(4):
            clock.advance(timedelta(days=1))
            backup.execute_run_backup(
                project_id,
                plan_id=plan["backup_plan_id"],
                idempotency_key=f"backup:retention:{index}",
            )
        first = backup.evaluate_retention(project_id, plan_id=plan["backup_plan_id"])
        assert len(first["pruned"]) >= 1
        second = backup.evaluate_retention(project_id, plan_id=plan["backup_plan_id"])
        assert second["pruned"] == []
        remaining = [item for item in backup.list_runs(project_id) if item["status"] == "succeeded"]
        assert len(remaining) >= 1
    finally:
        container.close()


def test_scheduled_backup_via_m8a_scheduler(tmp_path: Path) -> None:
    container, project_id, _root = _fixture(tmp_path)
    backup = container.create_backup_service()
    scheduler = container.create_backup_scheduler_service()
    now = datetime(2026, 6, 1, tzinfo=UTC)
    scheduler._clock = lambda: now
    backup._clock = lambda: now
    try:
        plan = backup.create_plan(
            project_id,
            name="nightly",
            schedule_interval_seconds=3600,
        )
        with container.create_unit_of_work(project_id) as uow:
            uow.begin()
            record = uow.repository(BackupRepository).get_plan(project_id, plan["backup_plan_id"])
            assert record is not None
            record.next_run_at = (now - timedelta(seconds=10)).isoformat()
            uow.commit()
        results = scheduler.run_due_plans(before=now)
        assert len(results) == 1
        assert results[0]["status"] == "succeeded"
        again = scheduler.run_due_plans(before=now)
        assert again == []
    finally:
        container.close()


def test_scheduler_respects_kill_switch(tmp_path: Path) -> None:
    container, project_id, _root = _fixture(tmp_path)
    backup = container.create_backup_service()
    scheduler = container.create_backup_scheduler_service()
    now = datetime(2026, 6, 2, tzinfo=UTC)
    scheduler._clock = lambda: now
    backup._clock = lambda: now
    try:
        plan = backup.create_plan(project_id, name="blocked", schedule_interval_seconds=60)
        with container.create_unit_of_work(project_id) as uow:
            uow.begin()
            record = uow.repository(BackupRepository).get_plan(project_id, plan["backup_plan_id"])
            assert record is not None
            record.next_run_at = (now - timedelta(seconds=1)).isoformat()
            uow.commit()
        container.create_automation_service().set_global_enabled(enabled=False)
        assert scheduler.run_due_plans(before=now) == []
    finally:
        container.close()


def test_nightly_recipe_backup_step_executes(tmp_path: Path) -> None:
    container, project_id, root = _fixture(tmp_path)
    automation = container.create_automation_service()
    backup = container.create_backup_service()
    try:
        recipes = automation.list_recipes()
        nightly = next(item for item in recipes if item["recipe_key"] == RecipeKey.NIGHTLY_MAINTENANCE.value)
        assert nightly["deferred_capabilities"] == []
        instance = automation.instantiate_recipe(
            project_id,
            RecipeKey.NIGHTLY_MAINTENANCE.value,
            params={**_recipe_params(root), "git_repository_id": str(StableIdentifier.new())},
        )
        assert instance["resolved_action_count"] == 3
        executed: list[str] = []

        def track_execute(**kwargs):
            executed.append(kwargs["action_type"])
            if kwargs["action_type"] == ActionType.RUN_CONFIG_VALIDATION.value:
                return {"validation": {"status": "pass"}}
            if kwargs["action_type"] == ActionType.GIT_CAPTURE_STATUS.value:
                return {"git_status": {"clean": True}}
            if kwargs["action_type"] == ActionType.CREATE_BACKUP.value:
                return {"backup": backup.execute_run_backup(project_id, idempotency_key=kwargs["idempotency_key"])}
            return {}

        workflow_id = instance["automation_workflow_id"]
        with patch.object(automation.engine._executor, "execute", side_effect=track_execute):
            automation.run_now(project_id, workflow_id, idempotency_key="nightly:manual")
        assert ActionType.CREATE_BACKUP.value in executed
    finally:
        container.close()


def test_backup_restore_not_sent_to_telemetry(tmp_path: Path) -> None:
    container, project_id, root = _fixture(tmp_path)
    backup = container.create_backup_service()
    try:
        (root / "server-data" / "server.cfg").write_text("cfg", encoding="utf-8")
        run = backup.execute_run_backup(project_id, idempotency_key="backup:telemetry:1")
        (root / "server-data" / "server.cfg").write_text("changed", encoding="utf-8")
        restore = backup.execute_restore(project_id, run["backup_run_id"], idempotency_key="restore:telemetry:1")
        backup.undo_restore(project_id, restore["restore_run_id"])
        with container.session_factory() as session:
            assert int(session.scalar(select(func.count()).select_from(TelemetryQueueRecord)) or 0) == 0
            assert int(session.scalar(select(func.count()).select_from(TelemetryRejectionRecord)) or 0) == 0
    finally:
        container.close()


def test_project_db_backup_does_not_corrupt_atlas_db(tmp_path: Path) -> None:
    container, project_id, root = _fixture(tmp_path)
    backup = container.create_backup_service()
    atlas_db = tmp_path / "app-data" / "atlas.sqlite3"
    try:
        _create_project_sqlite(root / "data" / "project.db", table="items", value="one")
        backup.execute_run_backup(project_id, idempotency_key="backup:atlasdb:1")
        connection = sqlite3.connect(atlas_db)
        try:
            count = connection.execute("select count(*) from projects").fetchone()[0]
            assert int(count) >= 1
        finally:
            connection.close()
    finally:
        container.close()


def test_project_id_isolation(tmp_path: Path) -> None:
    container = create_application_container(tmp_path / "app-data")
    backup = container.create_backup_service()
    root_a = _project_root(tmp_path, "project-a")
    root_b = _project_root(tmp_path, "project-b")
    try:
        project_a = ProjectId(container.create_project_service().execute_import_project(root_path=root_a).result["project_id"])
        project_b = ProjectId(container.create_project_service().execute_import_project(root_path=root_b).result["project_id"])
        (root_a / "server-data" / "server.cfg").write_text("project-a", encoding="utf-8")
        (root_b / "server-data" / "server.cfg").write_text("project-b", encoding="utf-8")
        run_a = backup.execute_run_backup(project_a, idempotency_key="backup:a")
        backup.execute_run_backup(project_b, idempotency_key="backup:b")
        runs_a = backup.list_runs(project_a)
        runs_b = backup.list_runs(project_b)
        assert all(run["project_id"] == str(project_a) for run in runs_a)
        assert all(run["project_id"] == str(project_b) for run in runs_b)
        assert runs_a[0]["backup_run_id"] == run_a["backup_run_id"]
        with container.session_factory() as session:
            foreign = BackupRepository(RepositoryContext(session=session, project_id=project_a)).get_run(
                project_a,
                runs_b[0]["backup_run_id"],
            )
            assert foreign is None
    finally:
        container.close()


def test_op_progress_published_for_backup(tmp_path: Path) -> None:
    container, project_id, root = _fixture(tmp_path)
    backup = container.create_backup_service()
    try:
        (root / "server-data" / "server.cfg").write_text("cfg", encoding="utf-8")
        published: list[str] = []
        original = container.stream_publisher.publish_operation_progress

        def capture(**kwargs):
            published.append(kwargs["message"])
            return original(**kwargs)

        with patch.object(container.stream_publisher, "publish_operation_progress", side_effect=capture):
            backup.execute_run_backup(project_id, idempotency_key="backup:progress:1")
        assert any("compress" in message.lower() for message in published)
    finally:
        container.close()


class _AdvancingClock:
    def __init__(self, start: datetime) -> None:
        self._current = start

    def advance(self, delta: timedelta | None = None) -> datetime:
        if delta is not None:
            self._current = self._current + delta
        return self._current


def _fixture(tmp_path: Path, name: str = "backup-project"):
    container = create_application_container(tmp_path / "app-data")
    root = _project_root(tmp_path, name)
    project_id = ProjectId(container.create_project_service().execute_import_project(root_path=root).result["project_id"])
    return container, project_id, root


def _project_root(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    (root / "resources").mkdir(parents=True)
    (root / "server-data").mkdir(parents=True)
    return root


def _recipe_params(root: Path) -> dict[str, str]:
    return {
        "fxserver_path": str(root / "FXServer.exe"),
        "server_data_path": str(root / "server-data"),
    }


def _create_project_sqlite(path: Path, *, table: str, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute(f"create table {table} (value text)")
        connection.execute(f"insert into {table} (value) values (?)", (value,))
        connection.commit()
    finally:
        connection.close()


def _tree_digest(root: Path) -> dict[str, bytes]:
    digest: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and ".atlas-snapshots" not in path.parts:
            digest[str(path.relative_to(root))] = path.read_bytes()
    return digest
