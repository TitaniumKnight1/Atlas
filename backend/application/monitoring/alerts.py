from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

from backend.adapters.persistence import MonitoringRepository, ProjectRepository
from backend.domain.monitoring.alert_state import (
    AlertCondition,
    AlertEvaluationInput,
    AlertEventKind,
    AlertRuntimeState,
    Comparator,
    compute_duration_satisfied,
    evaluate_alert_state,
    is_breaching,
)
from backend.domain.shared_kernel import ErrorCode, ProjectId, StableIdentifier


EVALUATION_INTERVAL_SECONDS = 30.0


class MonitoringAlertError(RuntimeError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


class MonitoringAlertService:
    """M6c alert detection and eventing only — no action execution (M8 owns actions)."""

    def __init__(self, *, container: Any, stream_publisher: Any | None = None, clock: Callable[[], datetime] | None = None) -> None:
        self._container = container
        self._stream_publisher = stream_publisher
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def create_alert(
        self,
        project_id: ProjectId,
        *,
        name: str,
        severity: str,
        metric_series_id: str,
        comparator: Comparator,
        threshold: float,
        duration_seconds: int = 0,
        is_enabled: bool = True,
    ) -> dict[str, Any]:
        now = self._clock()
        condition_json = {
            "metric_series_id": metric_series_id,
            "comparator": comparator,
            "threshold": threshold,
            "duration_seconds": duration_seconds,
        }
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            self._require_project(uow.repository(ProjectRepository), project_id)
            alert_id = StableIdentifier.new()
            record = uow.repository(MonitoringRepository).create_alert(
                monitoring_alert_id=alert_id,
                project_id=project_id,
                name=name,
                severity=severity,
                condition_json=condition_json,
                metric_series_id=metric_series_id,
                is_enabled=is_enabled,
                created_at=now,
            )
            uow.commit()
        return _alert_data(record)

    def update_alert(
        self,
        project_id: ProjectId,
        monitoring_alert_id: str,
        *,
        name: str | None = None,
        severity: str | None = None,
        metric_series_id: str | None = None,
        comparator: Comparator | None = None,
        threshold: float | None = None,
        duration_seconds: int | None = None,
        is_enabled: bool | None = None,
    ) -> dict[str, Any]:
        now = self._clock()
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(MonitoringRepository)
            existing = repository.get_alert(project_id, monitoring_alert_id)
            if existing is None:
                raise MonitoringAlertError(ErrorCode.NOT_FOUND, f"Alert not found: {monitoring_alert_id}")
            condition_json = dict(existing.condition_json)
            if metric_series_id is not None:
                condition_json["metric_series_id"] = metric_series_id
            if comparator is not None:
                condition_json["comparator"] = comparator
            if threshold is not None:
                condition_json["threshold"] = threshold
            if duration_seconds is not None:
                condition_json["duration_seconds"] = duration_seconds
            record = repository.update_alert(
                project_id=project_id,
                monitoring_alert_id=monitoring_alert_id,
                name=name,
                severity=severity,
                condition_json=condition_json,
                metric_series_id=metric_series_id,
                is_enabled=is_enabled,
                updated_at=now,
            )
            uow.commit()
        assert record is not None
        return _alert_data(record)

    def delete_alert(self, project_id: ProjectId, monitoring_alert_id: str) -> dict[str, Any]:
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            deleted = uow.repository(MonitoringRepository).delete_alert(project_id, monitoring_alert_id)
            if not deleted:
                raise MonitoringAlertError(ErrorCode.NOT_FOUND, f"Alert not found: {monitoring_alert_id}")
            uow.commit()
        return {"monitoring_alert_id": monitoring_alert_id, "deleted": True}

    def list_alerts(self, project_id: ProjectId) -> list[dict[str, Any]]:
        with self._container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext

            records = MonitoringRepository(RepositoryContext(session=session, project_id=project_id)).list_alerts(project_id)
        return [_alert_data(record) for record in records]

    def list_alert_events(self, project_id: ProjectId, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext

            return MonitoringRepository(RepositoryContext(session=session, project_id=project_id)).list_alert_events(
                project_id, limit=limit
            )

    def start_evaluation(self, *, interval_seconds: float = EVALUATION_INTERVAL_SECONDS) -> dict[str, Any]:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return {"status": "already_running", "interval_seconds": interval_seconds}
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._evaluation_loop,
                args=(interval_seconds,),
                name="monitoring-alert-evaluation",
                daemon=True,
            )
            self._thread.start()
        return {"status": "running", "interval_seconds": interval_seconds}

    def stop_evaluation(self) -> dict[str, Any]:
        with self._lock:
            if self._thread is None:
                return {"status": "not_running"}
            self._stop_event.set()
            thread = self._thread
        thread.join(timeout=5.0)
        with self._lock:
            self._thread = None
        return {"status": "stopped"}

    def active_evaluation(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def evaluate_project(self, project_id: ProjectId) -> dict[str, int]:
        now = self._clock()
        fired = 0
        resolved = 0
        stream_events: list[tuple[ProjectId, str, dict[str, Any]]] = []
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(MonitoringRepository)
            for alert in repository.list_enabled_alerts(project_id):
                transition, event_payload = self._evaluate_alert(repository, alert, now)
                if transition is None:
                    continue
                repository.update_alert_runtime(
                    monitoring_alert_id=alert.monitoring_alert_id,
                    runtime_state=transition.next_state.value,
                    pending_since=transition.pending_since,
                    updated_at=now,
                )
                if transition.event_kind is None:
                    continue
                if transition.event_kind == AlertEventKind.FIRED:
                    fired += 1
                    status = "triggered"
                else:
                    resolved += 1
                    status = "resolved"
                event_id = StableIdentifier.new()
                repository.add_alert_event(
                    alert_event_id=event_id,
                    monitoring_alert_id=alert.monitoring_alert_id,
                    project_id=ProjectId(alert.project_id),
                    status=status,
                    triggered_at=now,
                    resolved_at=now if status == "resolved" else None,
                    details_json=event_payload,
                )
                stream_events.append(
                    (
                        ProjectId(alert.project_id),
                        transition.event_kind.value,
                        {
                            "alert_event_id": str(event_id),
                            "monitoring_alert_id": alert.monitoring_alert_id,
                            "alert_name": alert.name,
                            "severity": alert.severity,
                            "status": status,
                            **event_payload,
                        },
                    )
                )
            uow.commit()
        if self._stream_publisher is not None:
            for event_project_id, event_type, payload in stream_events:
                self._stream_publisher.publish_alert_event(
                    project_id=event_project_id,
                    event_type=event_type,
                    payload=payload,
                )
        return {"fired": fired, "resolved": resolved}

    def evaluate_all_projects(self) -> dict[str, int]:
        totals = {"fired": 0, "resolved": 0}
        with self._container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext

            project_ids = {
                ProjectId(alert.project_id)
                for alert in MonitoringRepository(RepositoryContext(session=session)).list_enabled_alerts()
            }
        for project_id in project_ids:
            result = self.evaluate_project(project_id)
            totals["fired"] += result["fired"]
            totals["resolved"] += result["resolved"]
        return totals

    def _evaluation_loop(self, interval_seconds: float) -> None:
        while not self._stop_event.wait(interval_seconds):
            try:
                self.evaluate_all_projects()
            except Exception:
                continue

    def _evaluate_alert(self, repository: MonitoringRepository, alert: Any, now: datetime):
        condition_data = alert.condition_json
        series_id = alert.metric_series_id or condition_data.get("metric_series_id")
        if not series_id:
            return None, None
        condition = AlertCondition(
            metric_series_id=series_id,
            comparator=condition_data["comparator"],
            threshold=float(condition_data["threshold"]),
            duration_seconds=int(condition_data.get("duration_seconds", 0)),
        )
        observed = repository.latest_sample_value(series_id)
        pending_since = datetime.fromisoformat(alert.pending_since) if alert.pending_since else None
        window_start = now - timedelta(seconds=max(condition.duration_seconds, 1))
        recent = repository.recent_numeric_samples(series_id, start_at=window_start, end_at=now)
        breaching = observed is not None and is_breaching(observed, condition.comparator, condition.threshold)
        duration_satisfied = compute_duration_satisfied(
            condition=condition,
            breaching=breaching,
            pending_since=pending_since,
            evaluated_at=now,
            recent_samples=recent,
        )
        transition = evaluate_alert_state(
            AlertEvaluationInput(
                condition=condition,
                runtime_state=AlertRuntimeState(alert.runtime_state),
                pending_since=pending_since,
                observed_value=observed,
                evaluated_at=now,
                duration_satisfied=duration_satisfied,
            )
        )
        payload = {
            "metric_series_id": series_id,
            "observed_value": observed,
            "threshold": condition.threshold,
            "comparator": condition.comparator,
        }
        return transition, payload

    def _require_project(self, repository: ProjectRepository, project_id: ProjectId) -> None:
        if repository.get_project(project_id) is None:
            raise MonitoringAlertError(ErrorCode.NOT_FOUND, f"Project not found: {project_id}")


def _alert_data(record: Any) -> dict[str, Any]:
    return {
        "monitoring_alert_id": record.monitoring_alert_id,
        "project_id": record.project_id,
        "name": record.name,
        "severity": record.severity,
        "metric_series_id": record.metric_series_id,
        "condition": record.condition_json,
        "is_enabled": bool(record.is_enabled),
        "runtime_state": record.runtime_state,
        "pending_since": record.pending_since,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }
