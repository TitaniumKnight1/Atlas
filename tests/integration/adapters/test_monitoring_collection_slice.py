from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import httpx
from sqlalchemy import func, select

from backend.adapters.persistence.models import MetricSampleRecord, TelemetryQueueRecord, TelemetryRejectionRecord
from backend.domain.shared_kernel import ProjectId
from backend.infrastructure.di import create_application_container
from backend.infrastructure.streams import StreamTopic


def test_collect_once_emits_obtainable_metrics_without_command_audit(tmp_path: Path) -> None:
    container, project_id = _container_with_project(tmp_path)
    try:
        service = container.create_monitoring_service()
        samples = service.collect_once(project_id)
        names = {item["metric_name"] for item in samples}
        assert "memory_used_percent" in names
        assert "disk_used_percent" in names or "disk_free_gb" in names
        assert "process_state" in names
        assert "resource_count" in names
        deferred = [item for item in samples if item.get("deferred_reason")]
        assert any(item["metric_name"] == "server_fps" for item in deferred)
        assert all(item["quality"] == "missing" for item in deferred)
        assert all(item.get("value_real") is None for item in deferred)
    finally:
        container.close()


def test_metric_samples_stream_project_scoped_on_metrics_topic(tmp_path: Path) -> None:
    container, project_a = _container_with_project(tmp_path, "project-a")
    project_b = ProjectId(
        container.create_project_service().execute_import_project(root_path=_project_root(tmp_path, "project-b")).result["project_id"]
    )
    try:
        hub = container.stream_hub
        subscriber = hub.subscribe(str(project_a), {StreamTopic.METRICS})
        service = container.create_monitoring_service()
        service.collect_once(project_a)
        service.collect_once(project_b)
        received: list = []
        while True:
            event = subscriber.wait_next(timeout=0.5)
            if event is None:
                break
            received.append(event)
        assert received
        assert all(event.project_id == str(project_a) for event in received)
        assert all(event.topic == StreamTopic.METRICS for event in received)
        assert all(event.event_type == "MetricSample" for event in received)
        hub.unsubscribe(subscriber)
    finally:
        container.close()


def test_metrics_topic_coalesce_policy_via_bus_bridge(tmp_path: Path) -> None:
    container, project_id = _container_with_project(tmp_path)
    try:
        hub = container.stream_hub
        subscriber = hub.subscribe(str(project_id), {StreamTopic.METRICS})
        service = container.create_monitoring_service()
        with patch("backend.infrastructure.streams.hub.COALESCE_BUFFER_LIMIT", 2):
            for _ in range(4):
                service.collect_once(project_id)
        first = subscriber.wait_next(timeout=2.0)
        second = subscriber.wait_next(timeout=2.0)
        assert first is not None and second is not None
        assert first.sequence < second.sequence
        hub.unsubscribe(subscriber)
    finally:
        container.close()


def test_raw_samples_persist_in_single_writer_batches(tmp_path: Path) -> None:
    container, project_id = _container_with_project(tmp_path)
    try:
        service = container.create_monitoring_service()
        with patch("backend.application.monitoring.service.PERSIST_BATCH_MAX_SAMPLES", 1):
            service.start_collection(project_id, interval_seconds=0.05)
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline and _sample_count(container) == 0:
                time.sleep(0.05)
            service.stop_collection(project_id)
        assert _sample_count(container) > 0
    finally:
        container.close()


def test_collector_lifecycle_stops_without_leaked_sessions(tmp_path: Path) -> None:
    container, project_id = _container_with_project(tmp_path)
    try:
        service = container.create_monitoring_service()
        before = threading.active_count()
        service.start_collection(project_id, interval_seconds=0.05)
        time.sleep(0.15)
        assert service.active_collection_count() == 1
        service.stop_collection(project_id)
        assert service.active_collection_count() == 0
        time.sleep(0.1)
        assert threading.active_count() <= before + 1
        container.close()
        assert service.active_collection_count() == 0
    finally:
        container.close()


def test_supervised_process_metrics_reuse_m3b_status(tmp_path: Path) -> None:
    container, project_id = _container_with_project(tmp_path)
    setup = container.create_setup_service()
    script = "import time\nwhile True: time.sleep(0.2)\n"
    try:
        start = setup.execute_start_server(
            project_id=project_id,
            fxserver_path=sys.executable,
            server_data_path=str(tmp_path),
            extra_args=["-c", script],
        )
        process_run_id = start.result["process_run_id"]
        service = container.create_monitoring_service()
        samples = service.collect_once(project_id)
        by_name = {item["metric_name"]: item for item in samples}
        assert by_name["process_state"]["value_text"] == "running"
        assert by_name["process_up"]["value_real"] == 1.0
        assert by_name["process_pid"]["value_real"] == float(start.result["pid"])
        setup.execute_stop_server(project_id=project_id, process_run_id=process_run_id)
    finally:
        container.close()


def test_resource_health_source_consumes_m5a_not_rebuilt(tmp_path: Path) -> None:
    container, project_id = _container_with_project(tmp_path)
    resources = container.create_resource_service()
    try:
        resources.execute_rescan_resources(project_id=project_id, path_filters=None)
        service = container.create_monitoring_service()
        samples = service.collect_once(project_id)
        health_samples = [item for item in samples if item["metric_name"].startswith("resource_health_")]
        assert health_samples
        assert any(item["metric_name"] == "resource_count" for item in samples)
    finally:
        container.close()


def test_metrics_never_enter_telemetry_queue(tmp_path: Path) -> None:
    container, project_id = _container_with_project(tmp_path)
    try:
        service = container.create_monitoring_service()
        service.collect_once(project_id)
        service.start_collection(project_id, interval_seconds=0.05)
        time.sleep(0.2)
        service.stop_collection(project_id)
        assert _count(container, TelemetryQueueRecord) == 0
        assert _count(container, TelemetryRejectionRecord) == 0
    finally:
        container.close()


def test_project_isolation_on_metric_queries(tmp_path: Path) -> None:
    container, project_a = _container_with_project(tmp_path, "project-a")
    project_b = ProjectId(
        container.create_project_service().execute_import_project(root_path=_project_root(tmp_path, "project-b")).result["project_id"]
    )
    try:
        service = container.create_monitoring_service()
        with patch("backend.application.monitoring.service.PERSIST_BATCH_MAX_SAMPLES", 1):
            service.start_collection(project_a, interval_seconds=0.05)
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline and _sample_count(container) == 0:
                time.sleep(0.05)
            service.stop_collection(project_a)
        recent_a = service.recent_samples(project_a, limit=10)
        recent_b = service.recent_samples(project_b, limit=10)
        assert recent_a
        assert recent_b == []
    finally:
        container.close()


def test_fivem_player_count_collector(tmp_path: Path) -> None:
    container, project_id = _container_with_project(tmp_path)
    
    mock_response = MagicMock()
    mock_response.json.return_value = {"clients": 42}
    mock_response.raise_for_status.return_value = None
    
    mock_client = MagicMock()
    mock_client.get.return_value = mock_response
    
    setup = container.create_setup_service()
    script = "import time\nwhile True: time.sleep(0.2)\n"
    
    try:
        from backend.adapters.monitoring.collectors.fivem import FivemPlayerCountCollector
        collector = FivemPlayerCountCollector(port=30120, http_client=mock_client)
        # Register manually for the test
        container.create_monitoring_service()._registry.register(collector)
        
        start = setup.execute_start_server(
            project_id=project_id,
            fxserver_path=sys.executable,
            server_data_path=str(tmp_path),
            extra_args=["-c", script],
        )
        process_run_id = start.result["process_run_id"]
        
        service = container.create_monitoring_service()
        samples = service.collect_once(project_id)
        
        by_name = {item["metric_name"]: item for item in samples if item["source_type"] == "fivem"}
        
        assert "player_count" in by_name
        assert by_name["player_count"]["value_real"] == 42.0
        assert by_name["player_count"]["quality"] == "ok"
        assert by_name["player_count"]["source_ref"] == process_run_id
        
        setup.execute_stop_server(project_id=project_id, process_run_id=process_run_id)
    finally:
        container.close()


def _container_with_project(tmp_path: Path, name: str = "monitoring-project"):
    container = create_application_container(tmp_path / "app-data")
    project_id = ProjectId(
        container.create_project_service().execute_import_project(root_path=_project_root(tmp_path, name)).result["project_id"]
    )
    return container, project_id


def _project_root(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    (root / "resources").mkdir(parents=True)
    return root


def _count(container, model) -> int:
    with container.session_factory() as session:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _sample_count(container) -> int:
    return _count(container, MetricSampleRecord)
