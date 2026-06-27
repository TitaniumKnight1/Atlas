from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from backend.adapters.monitoring import MetricCollectorRegistry
from backend.adapters.monitoring.collectors import (
    DeferredServerMetricCollector,
    ResourceHealthMetricCollector,
    SupervisedProcessMetricCollector,
    SystemMetricCollector,
)
from backend.adapters.monitoring.collectors.fivem import FivemPlayerCountCollector
from backend.adapters.persistence import MonitoringRepository, ProjectRepository, SetupRepository
from backend.adapters.persistence.models import ProjectPathRecord
from backend.domain.monitoring import CollectorContext, CollectedMetricSample, RetentionClass
from backend.domain.shared_kernel import ErrorCode, ProjectId, StableIdentifier
from backend.infrastructure.unit_of_work import RepositoryContext


SAMPLE_INTERVAL_SECONDS = 2.0
PERSIST_BATCH_INTERVAL_SECONDS = 10.0
PERSIST_BATCH_MAX_SAMPLES = 30


class MonitoringApplicationError(RuntimeError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(slots=True)
class _CollectionSession:
    project_id: ProjectId
    stop_event: threading.Event
    thread: threading.Thread
    pending_samples: list[dict[str, Any]] = field(default_factory=list)
    last_flush_at: float = field(default_factory=time.monotonic)
    series_cache: dict[tuple[str, str | None, str], str] = field(default_factory=dict)


class MonitoringApplicationService:
    """M6a read-only metric collection, query, and live streaming — not a command/undo module."""

    def __init__(self, *, container: Any, process_port: Any, stream_publisher: Any | None = None) -> None:
        self._container = container
        self._process_port = process_port
        self._stream_publisher = stream_publisher
        self._registry = MetricCollectorRegistry()
        self._registry.register(SystemMetricCollector())
        self._registry.register(SupervisedProcessMetricCollector(process_port))
        self._registry.register(ResourceHealthMetricCollector(container.create_resource_service()))
        self._registry.register(DeferredServerMetricCollector())
        self._registry.register(FivemPlayerCountCollector())
        self._lock = threading.RLock()
        self._sessions: dict[str, _CollectionSession] = {}

    def start_collection(self, project_id: ProjectId, *, interval_seconds: float = SAMPLE_INTERVAL_SECONDS) -> dict[str, Any]:
        with self._lock:
            if str(project_id) in self._sessions:
                return {"project_id": str(project_id), "status": "already_running"}
            self._ensure_default_sources(project_id)
            stop_event = threading.Event()
            session = _CollectionSession(
                project_id=project_id,
                stop_event=stop_event,
                thread=threading.Thread(
                    target=self._collection_loop,
                    args=(project_id, stop_event, interval_seconds),
                    name=f"metric-collector-{project_id}",
                    daemon=True,
                ),
            )
            self._sessions[str(project_id)] = session
            session.thread.start()
        return {"project_id": str(project_id), "status": "running", "interval_seconds": interval_seconds}

    def stop_collection(self, project_id: ProjectId) -> dict[str, Any]:
        session = self._pop_session(project_id)
        if session is None:
            return {"project_id": str(project_id), "status": "not_running"}
        session.stop_event.set()
        session.thread.join(timeout=5.0)
        if session.pending_samples:
            self._flush_samples(project_id, session.pending_samples)
        return {"project_id": str(project_id), "status": "stopped"}

    def stop_all_collections(self) -> None:
        with self._lock:
            project_ids = list(self._sessions.keys())
        for project_id in project_ids:
            self.stop_collection(ProjectId(project_id))

    def active_collection_count(self) -> int:
        with self._lock:
            return len(self._sessions)

    def collection_status(self, project_id: ProjectId) -> dict[str, Any]:
        """Return the collection status for a project (running/stopped, thread alive, pending sample count)."""
        with self._lock:
            session = self._sessions.get(str(project_id))
        if session is None:
            return {"project_id": str(project_id), "status": "stopped", "thread_alive": False, "pending_samples": 0}
        return {
            "project_id": str(project_id),
            "status": "running",
            "thread_alive": session.thread.is_alive(),
            "pending_samples": len(session.pending_samples),
        }

    def list_sources(self, project_id: ProjectId) -> list[dict[str, Any]]:
        with self._container.session_factory() as session:
            records = MonitoringRepository(RepositoryContext(session=session, project_id=project_id)).list_sources(project_id)
        return [_source_data(record) for record in records]

    def latest_metrics(self, project_id: ProjectId) -> list[dict[str, Any]]:
        with self._container.session_factory() as session:
            return MonitoringRepository(RepositoryContext(session=session, project_id=project_id)).latest_samples_per_series(project_id)

    def recent_samples(self, project_id: ProjectId, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._container.session_factory() as session:
            return MonitoringRepository(RepositoryContext(session=session, project_id=project_id)).list_recent_samples(
                project_id, limit=limit
            )

    def collect_once(self, project_id: ProjectId) -> list[dict[str, Any]]:
        """Synchronous single collection tick for tests and on-demand sampling."""
        session = self._sessions.get(str(project_id))
        series_cache = session.series_cache if session is not None else {}
        context = self._build_context(project_id)
        raw_samples: list[CollectedMetricSample] = []
        for collector in self._registry.list_collectors():
            raw_samples.extend(collector.collect(context))
        series_ids = self._resolve_series_ids(project_id, raw_samples, context.sampled_at, series_cache)
        if session is not None:
            session.series_cache = series_ids
        emitted: list[dict[str, Any]] = []
        for sample in raw_samples:
            payload = self._emit_sample(project_id, sample, context.sampled_at, series_ids)
            if payload is not None:
                emitted.append(payload)
        return emitted

    def _collection_loop(self, project_id: ProjectId, stop_event: threading.Event, interval_seconds: float) -> None:
        session = self._sessions.get(str(project_id))
        while not stop_event.wait(interval_seconds):
            try:
                payloads = self.collect_once(project_id)
                if session is None:
                    continue
                session.pending_samples.extend(payloads)
                if self._should_flush(session):
                    batch = list(session.pending_samples)
                    session.pending_samples.clear()
                    session.last_flush_at = time.monotonic()
                    self._flush_samples(project_id, batch)
            except Exception:
                continue

    def _should_flush(self, session: _CollectionSession) -> bool:
        if len(session.pending_samples) >= PERSIST_BATCH_MAX_SAMPLES:
            return True
        return (time.monotonic() - session.last_flush_at) >= PERSIST_BATCH_INTERVAL_SECONDS

    def _flush_samples(self, project_id: ProjectId, payloads: list[dict[str, Any]]) -> None:
        persistable = [item for item in payloads if item.get("persist")]
        if not persistable:
            return
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(MonitoringRepository)
            rows = [
                {
                    "sample_id": str(StableIdentifier.new()),
                    "metric_series_id": item["metric_series_id"],
                    "sampled_at": item["sampled_at"],
                    "value_real": item.get("value_real"),
                    "value_text": item.get("value_text"),
                    "quality": item["quality"],
                }
                for item in persistable
            ]
            repository.add_samples(rows)
            uow.commit()

    def _emit_sample(
        self,
        project_id: ProjectId,
        sample: CollectedMetricSample,
        sampled_at: datetime,
        series_ids: dict[tuple[str, str | None, str], str],
    ) -> dict[str, Any] | None:
        series_key = (sample.source_type, sample.source_ref, sample.metric_name)
        series_id = series_ids.get(series_key)
        if series_id is None:
            return None
        persist = sample.quality != "missing" or sample.value_real is not None or sample.value_text is not None
        payload = {
            "metric_series_id": series_id,
            "metric_name": sample.metric_name,
            "source_type": sample.source_type,
            "source_ref": sample.source_ref,
            "unit": sample.unit,
            "value_type": sample.value_type,
            "value_real": sample.value_real,
            "value_text": sample.value_text,
            "quality": sample.quality,
            "sampled_at": sampled_at.isoformat(),
            "deferred_reason": sample.deferred_reason,
            "persist": persist,
        }
        if self._stream_publisher is not None:
            self._stream_publisher.publish_metric_sample(project_id=project_id, sample=payload)
        return payload

    def _resolve_series_ids(
        self,
        project_id: ProjectId,
        samples: list[CollectedMetricSample],
        sampled_at: datetime,
        cache: dict[tuple[str, str | None, str], str],
    ) -> dict[tuple[str, str | None, str], str]:
        unresolved = {
            (sample.source_type, sample.source_ref, sample.metric_name)
            for sample in samples
            if (sample.source_type, sample.source_ref, sample.metric_name) not in cache
        }
        if not unresolved:
            return cache
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(MonitoringRepository)
            updated = dict(cache)
            for source_type, source_ref, metric_name in unresolved:
                sample = next(
                    item
                    for item in samples
                    if item.source_type == source_type and item.source_ref == source_ref and item.metric_name == metric_name
                )
                source = repository.upsert_source(
                    metric_source_id=StableIdentifier.new(),
                    project_id=project_id,
                    source_type=source_type,
                    source_ref=source_ref,
                    display_name=f"{source_type}:{source_ref or metric_name}",
                    is_enabled=True,
                )
                uow.session.flush()
                series = repository.upsert_series(
                    metric_series_id=StableIdentifier.new(),
                    metric_source_id=source.metric_source_id,
                    metric_name=metric_name,
                    unit=sample.unit,
                    value_type=sample.value_type,
                    retention_class=RetentionClass.HIGH.value,
                    created_at=sampled_at,
                )
                updated[(source_type, source_ref, metric_name)] = series.metric_series_id
            uow.commit()
            return updated

    def _ensure_default_sources(self, project_id: ProjectId) -> None:
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            self._require_project(uow.repository(ProjectRepository), project_id)
            repository = uow.repository(MonitoringRepository)
            for collector in self._registry.list_collectors():
                repository.upsert_source(
                    metric_source_id=StableIdentifier.new(),
                    project_id=project_id,
                    source_type=collector.source_type,
                    source_ref=None,
                    display_name=collector.collector_id,
                    is_enabled=True,
                    metadata={"collector_id": collector.collector_id},
                )
            uow.commit()

    def _build_context(self, project_id: ProjectId) -> CollectorContext:
        now = datetime.now(UTC)
        process_run_id = None
        project_root = None
        with self._container.session_factory() as session:
            current = SetupRepository(RepositoryContext(session=session, project_id=project_id)).current_process_run(project_id)
            if current is not None:
                process_run_id = current.process_run_id
            paths = session.execute(
                select(ProjectPathRecord).where(
                    ProjectPathRecord.project_id == str(project_id),
                    ProjectPathRecord.path_role == "root",
                )
            ).scalars()
            for record in paths:
                project_root = Path(record.absolute_path)
                break
        return CollectorContext(project_id=project_id, sampled_at=now, process_run_id=process_run_id, project_root=project_root)

    def _pop_session(self, project_id: ProjectId) -> _CollectionSession | None:
        with self._lock:
            return self._sessions.pop(str(project_id), None)

    def _require_project(self, repository: ProjectRepository, project_id: ProjectId) -> None:
        if repository.get_project(project_id) is None:
            raise MonitoringApplicationError(ErrorCode.NOT_FOUND, f"Project not found: {project_id}")


def _source_data(record: Any) -> dict[str, Any]:
    return {
        "metric_source_id": record.metric_source_id,
        "project_id": record.project_id,
        "source_type": record.source_type,
        "source_ref": record.source_ref,
        "display_name": record.display_name,
        "is_enabled": bool(record.is_enabled),
        "metadata": record.metadata_json or {},
    }
