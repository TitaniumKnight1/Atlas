from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

from backend.adapters.persistence import BackupRepository
from backend.application.backup.service import BackupApplicationService
from backend.domain.backup.types import BackupTriggerType
from backend.domain.shared_kernel import ProjectId
from backend.infrastructure.unit_of_work import RepositoryContext


SCHEDULER_POLL_SECONDS = 0.5


class BackupSchedulerService:
    """Scheduled backups via in-process poll — single-writer-safe, idempotent."""

    def __init__(self, *, container: Any, backup_service: BackupApplicationService, clock: Callable[[], datetime] | None = None) -> None:
        self._container = container
        self._backup = backup_service
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, *, poll_seconds: float = SCHEDULER_POLL_SECONDS) -> dict[str, Any]:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return {"status": "already_running"}
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._poll_loop, args=(poll_seconds,), name="backup-scheduler", daemon=True)
            self._thread.start()
        return {"status": "running", "poll_seconds": poll_seconds}

    def stop(self) -> dict[str, Any]:
        with self._lock:
            if self._thread is None:
                return {"status": "not_running"}
            self._stop_event.set()
            thread = self._thread
        thread.join(timeout=5.0)
        with self._lock:
            self._thread = None
        return {"status": "stopped"}

    def run_due_plans(self, *, before: datetime | None = None) -> list[dict[str, Any]]:
        if not self._automation_globally_enabled():
            return []
        now = before or self._clock()
        with self._container.session_factory() as session:
            due = BackupRepository(RepositoryContext(session=session)).list_due_plans(before=now)
        results: list[dict[str, Any]] = []
        for plan in due:
            key = f"schedule:{plan.backup_plan_id}:{plan.next_run_at}"
            result = self._backup.execute_run_backup(
                ProjectId(plan.project_id),
                plan_id=plan.backup_plan_id,
                trigger_type=BackupTriggerType.SCHEDULED.value,
                idempotency_key=key,
            )
            self._advance_plan(plan.backup_plan_id, ProjectId(plan.project_id), now)
            results.append(result)
        return results

    def _advance_plan(self, plan_id: str, project_id: ProjectId, now: datetime) -> None:
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(BackupRepository)
            plan = repository.get_plan(project_id, plan_id)
            if plan is None or not plan.schedule_interval_seconds or not plan.next_run_at:
                uow.rollback()
                return
            due_at = datetime.fromisoformat(plan.next_run_at)
            interval = timedelta(seconds=int(plan.schedule_interval_seconds))
            next_run = due_at
            while next_run <= now:
                next_run = next_run + interval
            repository.advance_plan_schedule(plan, next_run_at=next_run, last_run_at=now)
            uow.commit()

    def _poll_loop(self, poll_seconds: float) -> None:
        while not self._stop_event.wait(poll_seconds):
            try:
                self.run_due_plans()
            except Exception:
                continue

    def _automation_globally_enabled(self) -> bool:
        from backend.adapters.persistence import AutomationRepository

        with self._container.session_factory() as session:
            return AutomationRepository(RepositoryContext(session=session)).get_global_enabled()
