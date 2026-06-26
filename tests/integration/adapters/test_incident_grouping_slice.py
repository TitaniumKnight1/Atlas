from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select

from backend.adapters.persistence.models import (
    IncidentFingerprintRecord,
    IncidentGroupRecord,
    IncidentOccurrenceRecord,
    TelemetryQueueRecord,
    TelemetryRejectionRecord,
)
from backend.domain.incident.fingerprint import compute_fingerprint, is_placeholder_fingerprint
from backend.domain.incident.signals import FingerprintSignals
from backend.domain.shared_kernel import ProjectId, StableIdentifier
from backend.infrastructure.di import create_application_container
from backend.adapters.persistence import IncidentRepository


def test_identical_crashes_deduplicate_into_one_group(tmp_path: Path) -> None:
    container, project_id, resources_root, _ = _fixture(tmp_path)
    setup = container.create_setup_service()
    script = "import time, sys\nprint('CRASHING', flush=True)\ntime.sleep(0.1)\nsys.exit(7)\n"
    try:
        for _ in range(3):
            start = setup.execute_start_server(
                project_id=project_id,
                fxserver_path=sys.executable,
                server_data_path=str(resources_root.parent / "server-data"),
                extra_args=["-c", script],
            )
            _wait_for_crash(setup, project_id, start.result["process_run_id"])
            _wait_for_incident_count(container, project_id, min_groups=1)

        service = container.create_incident_service()
        groups = service.list_incidents(project_id)
        assert len(groups) == 1
        group = service.get_incident(project_id, groups[0]["incident_group_id"])
        assert group["occurrence_count"] == 3
        assert len(group["occurrences"]) == 3
        assert not is_placeholder_fingerprint(group["fingerprint"])
        assert group["first_seen_at"] <= group["last_seen_at"]
    finally:
        container.close()


def test_distinct_exit_codes_create_distinct_groups(tmp_path: Path) -> None:
    container, project_id, resources_root, _ = _fixture(tmp_path)
    setup = container.create_setup_service()
    try:
        for code in (7, 9):
            script = f"import sys\nprint('FAIL-{code}', flush=True)\nsys.exit({code})\n"
            start = setup.execute_start_server(
                project_id=project_id,
                fxserver_path=sys.executable,
                server_data_path=str(resources_root.parent / "server-data"),
                extra_args=["-c", script],
            )
            _wait_for_crash(setup, project_id, start.result["process_run_id"])
            time.sleep(0.2)
        groups = container.create_incident_service().list_incidents(project_id)
        assert len(groups) == 2
        fingerprints = {item["fingerprint"] for item in groups}
        assert len(fingerprints) == 2
    finally:
        container.close()


def test_safe_transition_merges_m7a_placeholder_groups(tmp_path: Path) -> None:
    container, project_id = _container_with_project(tmp_path)
    service = container.create_incident_service()
    try:
        placeholder_ids = _seed_m7a_placeholder_groups(container, project_id, copies=3, exit_code=7)
        assert len(placeholder_ids) == 3
        assert _count(container, IncidentGroupRecord) == 3
        assert _count(container, IncidentOccurrenceRecord) == 3

        first = service.migrate_placeholder_incidents(project_id)
        second = service.migrate_placeholder_incidents(project_id)
        assert first["occurrences_moved"] >= 0
        assert second == {"groups_merged": 0, "occurrences_moved": 0, "groups_deleted": 0}

        groups = service.list_incidents(project_id)
        assert len(groups) == 1
        assert groups[0]["occurrence_count"] == 3
        assert not is_placeholder_fingerprint(groups[0]["fingerprint"])
        assert _count(container, IncidentOccurrenceRecord) == 3
        assert _count(container, IncidentFingerprintRecord) >= 1
    finally:
        container.close()


def test_fingerprint_key_contains_no_planted_secret(tmp_path: Path) -> None:
    secret = "supersecret-token-value-12345"
    signals = FingerprintSignals(
        category="crash",
        severity="fatal",
        source_type="process",
        exit_code=7,
        exception_type=None,
        normalized_message="Server process exited unexpectedly with code 7",
        log_lines=(f"discord_token={secret}",),
    )
    result = compute_fingerprint(signals)
    assert secret not in result.fingerprint
    assert secret not in json.dumps(result.components)

    container, project_id, resources_root, _ = _fixture(tmp_path)
    setup = container.create_setup_service()
    script = f"import sys\nprint('discord_token={secret}', flush=True)\nsys.exit(7)\n"
    try:
        start = setup.execute_start_server(
            project_id=project_id,
            fxserver_path=sys.executable,
            server_data_path=str(resources_root.parent / "server-data"),
            extra_args=["-c", script],
        )
        _wait_for_crash(setup, project_id, start.result["process_run_id"])
        group = container.create_incident_service().list_incidents(project_id)[0]
        assert secret not in group["fingerprint"]
        with container.session_factory() as session:
            fp = session.execute(select(IncidentFingerprintRecord)).scalar_one()
            assert secret not in fp.fingerprint
            assert secret not in json.dumps(fp.components_json or {})
        assert _count(container, TelemetryQueueRecord) == 0
        assert _count(container, TelemetryRejectionRecord) == 0
    finally:
        container.close()


def test_project_isolation_for_grouped_incidents(tmp_path: Path) -> None:
    container, first_project_id, resources_root, _ = _fixture(tmp_path, name="alpha")
    second_project_id = ProjectId(
        container.create_project_service().execute_import_project(root_path=_project_root(tmp_path, "beta")).result["project_id"]
    )
    setup = container.create_setup_service()
    script = "import sys\nsys.exit(7)\n"
    try:
        start = setup.execute_start_server(
            project_id=first_project_id,
            fxserver_path=sys.executable,
            server_data_path=str(resources_root.parent / "server-data"),
            extra_args=["-c", script],
        )
        _wait_for_crash(setup, first_project_id, start.result["process_run_id"])
        assert container.create_incident_service().list_incidents(first_project_id)
        assert container.create_incident_service().list_incidents(second_project_id) == []
    finally:
        container.close()


def test_compare_incidents_reports_differences(tmp_path: Path) -> None:
    container, project_id, resources_root, _ = _fixture(tmp_path)
    setup = container.create_setup_service()
    try:
        for code in (7, 9):
            script = f"import sys\nprint('FAIL-{code}')\nsys.exit({code})\n"
            start = setup.execute_start_server(
                project_id=project_id,
                fxserver_path=sys.executable,
                server_data_path=str(resources_root.parent / "server-data"),
                extra_args=["-c", script],
            )
            _wait_for_crash(setup, project_id, start.result["process_run_id"])
            time.sleep(0.2)
        groups = container.create_incident_service().list_incidents(project_id)
        report = container.create_incident_service().compare_incidents(
            project_id, incident_group_ids=[groups[0]["incident_group_id"], groups[1]["incident_group_id"]]
        )
        assert report["shared"]["fingerprint"] is False
        assert any(item["field"] == "exit_code" for item in report["differences"])
    finally:
        container.close()


def _seed_m7a_placeholder_groups(container, project_id: ProjectId, *, copies: int, exit_code: int) -> list[str]:
    from backend.adapters.incident.snapshot_assembler import IncidentSnapshotAssembler
    from backend.domain.incident import IncidentCategory, IncidentGroupStatus, IncidentSeverity, IncidentSourceType

    assembler = IncidentSnapshotAssembler(container)
    group_ids: list[str] = []
    for _ in range(copies):
        process_run_id = "synthetic-run"
        assembled = assembler.assemble(project_id, process_run_id=process_run_id, exit_code=exit_code)
        group_id = str(StableIdentifier.new())
        occurrence_id = StableIdentifier.new()
        now = datetime.now(UTC)
        with container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(IncidentRepository)
            repository.create_group(
                incident_group_id=StableIdentifier(group_id),
                project_id=project_id,
                fingerprint=f"capture:{occurrence_id}",
                title=assembled.message,
                severity=IncidentSeverity.FATAL.value,
                category=IncidentCategory.CRASH.value,
                status=IncidentGroupStatus.UNRESOLVED.value,
                first_seen_at=now,
                last_seen_at=now,
            )
            repository.create_occurrence(
                occurrence_id=occurrence_id,
                incident_group_id=group_id,
                project_id=project_id,
                occurred_at=now,
                source_type=IncidentSourceType.PROCESS.value,
                message=assembled.message,
            )
            uow.session.flush()
            repository.add_breadcrumbs(str(occurrence_id), assembled.breadcrumbs)
            repository.add_context_snapshots(str(occurrence_id), assembled.context_snapshots)
            if assembled.stack_trace is not None:
                repository.add_stack_trace(str(occurrence_id), assembled.stack_trace)
            uow.commit()
        group_ids.append(group_id)
    return group_ids


def _fixture(tmp_path: Path, name: str = "grouping-project"):
    container = create_application_container(tmp_path / "app-data")
    root = _project_root(tmp_path, name)
    server_data = root / "server-data"
    server_data.mkdir(parents=True, exist_ok=True)
    resources_root = root / "resources"
    resources_root.mkdir(parents=True, exist_ok=True)
    (server_data / "server.cfg").write_text('sv_licenseKey "cfxk_test"\n', encoding="utf-8")
    project_id = ProjectId(container.create_project_service().execute_import_project(root_path=root).result["project_id"])
    return container, project_id, resources_root, None


def _container_with_project(tmp_path: Path, name: str = "transition-project"):
    container = create_application_container(tmp_path / "app-data")
    root = _project_root(tmp_path, name)
    (root / "server-data").mkdir(parents=True, exist_ok=True)
    project_id = ProjectId(container.create_project_service().execute_import_project(root_path=root).result["project_id"])
    return container, project_id


def _project_root(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    (root / "resources").mkdir(parents=True, exist_ok=True)
    (root / "server-data").mkdir(parents=True, exist_ok=True)
    return root


def _wait_for_crash(setup, project_id: ProjectId, process_run_id: str) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if setup.get_process_status(project_id, process_run_id)["state"] == "crashed":
            return
        time.sleep(0.05)
    raise AssertionError("process did not crash")


def _wait_for_incident_count(container, project_id: ProjectId, *, min_groups: int) -> None:
    service = container.create_incident_service()
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if len(service.list_incidents(project_id)) >= min_groups:
            return
        time.sleep(0.05)
    raise AssertionError("incident groups missing")


def _count(container, model) -> int:
    with container.session_factory() as session:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)
