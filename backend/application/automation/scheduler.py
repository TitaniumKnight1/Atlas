from __future__ import annotations

import threading
import time
from datetime import UTC, datetime
from typing import Any, Callable

from backend.adapters.persistence import AutomationRepository
from backend.application.automation.engine import AutomationEngine
from backend.infrastructure.unit_of_work import RepositoryContext


SCHEDULER_POLL_SECONDS = 0.25


class AutomationSchedulerService:
    """DB-backed in-process scheduler — single-writer-safe, no APScheduler second writer."""

    def __init__(self, *, container: Any, engine: AutomationEngine, clock: Callable[[], datetime] | None = None) -> None:
        self._container = container
        self._engine = engine
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, *, poll_seconds: float = SCHEDULER_POLL_SECONDS) -> dict[str, Any]:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return {"status": "already_running", "poll_seconds": poll_seconds}
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._poll_loop,
                args=(poll_seconds,),
                name="automation-scheduler",
                daemon=True,
            )
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

    def active(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def run_due_schedules(self, *, before: datetime | None = None) -> list[dict[str, Any]]:
        now = before or self._clock()
        with self._container.session_factory() as session:
            due = AutomationRepository(RepositoryContext(session=session)).list_due_schedules(before=now)
        results: list[dict[str, Any]] = []
        for schedule in due:
            result = self._engine.trigger_schedule(schedule.automation_schedule_id)
            if result is not None:
                results.append(result)
        return results

    def _poll_loop(self, poll_seconds: float) -> None:
        while not self._stop_event.wait(poll_seconds):
            try:
                self.run_due_schedules()
            except Exception:
                continue
