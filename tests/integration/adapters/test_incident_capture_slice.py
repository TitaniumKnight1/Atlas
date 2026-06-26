from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from git import Repo
from sqlalchemy import func, select

from backend.adapters.persistence.models import (
    CommandExecutionRecord,
    DomainEventRecord,
    GitRepositoryRecord,
    IncidentGroupRecord,
    IncidentOccurrenceRecord,
    TelemetryQueueRecord,
    TelemetryRejectionRecord,
)
from backend.domain.incident import ContextSnapshotType
from backend.domain.shared_kernel import ProjectId
from backend.infrastructure.di import create_application_container


def test_crash_triggers_incident_capture_with_full_snapshot(tmp_path: Path) -> None:
    container, project_id, resources_root, config_file_id = _fixture(tmp_path)
    setup = container.create_setup_service()
    script = "import time, sys\nprint('CRASHING', flush=True)\ntime.sleep(0.2)\nsys.exit(7)\n"
    try:
        _seed_resources(container, project_id, resources_root)
        _seed_config_secrets(container, project_id, config_file_id)
        _seed_git(container, project_id, tmp_path)
        container.create_monitoring_service().collect_once(project_id)

        start = setup.execute_start_server(
            project_id=project_id,
            fxserver_path=sys.executable,
            server_data_path=str(resources_root.parent / "server-data"),
            extra_args=["-c", script],
        )
        process_run_id = start.result["process_run_id"]
        _wait_for_crash(setup, project_id, process_run_id)

        incident = _wait_for_incident(container, project_id)
        timeline = container.create_incident_service().get_occurrence_timeline(project_id, incident["occurrences"][0]["occurrence_id"])
        snapshots = {item["context_type"]: item["snapshot_json"] for item in timeline["context_snapshots"]}

        assert incident["severity"] == "fatal"
        assert incident["category"] == "crash"
        assert ContextSnapshotType.RUNTIME.value in snapshots
        assert snapshots[ContextSnapshotType.RUNTIME.value]["state"] == "crashed"
        assert snapshots[ContextSnapshotType.RUNTIME.value]["exit_code"] == 7
        assert ContextSnapshotType.RESOURCES.value in snapshots
        assert snapshots[ContextSnapshotType.RESOURCES.value]["resources"]
        assert ContextSnapshotType.STARTUP_ORDER.value in snapshots
        assert ContextSnapshotType.CONFIG_EXCERPT.value in snapshots
        assert snapshots[ContextSnapshotType.CONFIG_EXCERPT.value]["secret_findings"]
        assert ContextSnapshotType.ENVIRONMENT.value in snapshots
        assert snapshots[ContextSnapshotType.ENVIRONMENT.value]["repositories"]
        assert ContextSnapshotType.SYSTEM.value in snapshots
        assert ContextSnapshotType.LOGS.value in snapshots
        logs = snapshots[ContextSnapshotType.LOGS.value]
        assert logs["availability"] == "bounded_tail_only"
        assert logs["durable_history_available"] is False
        assert logs["max_lines_per_stream"] == 200
        assert any("CRASHING" in line for line in logs["stdout_tail"])
        assert timeline["stack_trace"] is not None
        assert "unexpected" in (timeline["stack_trace"].get("exception_value") or "").lower()
        assert timeline["breadcrumbs"]
        assert "IncidentCaptured" in _domain_event_types(container)
        assert _count(container, IncidentGroupRecord) == 1
        assert _count(container, IncidentOccurrenceRecord) == 1
        assert _count(container, TelemetryQueueRecord) == 0
        assert _count(container, TelemetryRejectionRecord) == 0
    finally:
        container.close()


def test_git_remote_redacted_in_snapshot(tmp_path: Path) -> None:
    container, project_id, resources_root, config_file_id = _fixture(tmp_path)
    setup = container.create_setup_service()
    secret_url = "https://user:supersecret@example.com/org/repo.git"
    script = "import sys\nsys.exit(3)\n"
    try:
        repo_id = _seed_git(container, project_id, tmp_path)
        with container.session_factory() as session:
            record = session.get(GitRepositoryRecord, repo_id)
            assert record is not None
            record.remote_url = secret_url
            session.commit()

        start = setup.execute_start_server(
            project_id=project_id,
            fxserver_path=sys.executable,
            server_data_path=str(resources_root.parent / "server-data"),
            extra_args=["-c", script],
        )
        _wait_for_crash(setup, project_id, start.result["process_run_id"])
        incident = _wait_for_incident(container, project_id)
        timeline = container.create_incident_service().get_occurrence_timeline(
            project_id, incident["occurrences"][0]["occurrence_id"]
        )
        env = next(item for item in timeline["context_snapshots"] if item["context_type"] == ContextSnapshotType.ENVIRONMENT.value)
        payload = json.dumps(env["snapshot_json"])
        assert "supersecret" not in payload
        assert "[REDACTED]" in payload
    finally:
        container.close()


def test_config_secrets_not_widened_in_snapshot(tmp_path: Path) -> None:
    container, project_id, resources_root, config_file_id = _fixture(tmp_path, content=_config_with_secret())
    setup = container.create_setup_service()
    script = "import sys\nsys.exit(5)\n"
    try:
        _seed_config_secrets(container, project_id, config_file_id)
        start = setup.execute_start_server(
            project_id=project_id,
            fxserver_path=sys.executable,
            server_data_path=str(resources_root.parent / "server-data"),
            extra_args=["-c", script],
        )
        _wait_for_crash(setup, project_id, start.result["process_run_id"])
        incident = _wait_for_incident(container, project_id)
        timeline = container.create_incident_service().get_occurrence_timeline(
            project_id, incident["occurrences"][0]["occurrence_id"]
        )
        config_snapshot = next(
            item for item in timeline["context_snapshots"] if item["context_type"] == ContextSnapshotType.CONFIG_EXCERPT.value
        )
        payload = json.dumps(config_snapshot["snapshot_json"])
        assert "supersecret" not in payload
        assert "discord_token" not in payload.lower() or "secret_finding_id" in payload
        findings = config_snapshot["snapshot_json"]["secret_findings"]
        assert findings
        assert all("Secret values are not included" in item.get("note", "") for item in findings)
    finally:
        container.close()


def test_project_isolation_for_incidents(tmp_path: Path) -> None:
    container, first_project_id, resources_root, _ = _fixture(tmp_path, name="alpha")
    second_project_id = ProjectId(
        container.create_project_service().execute_import_project(root_path=_project_root(tmp_path, "beta")).result["project_id"]
    )
    setup = container.create_setup_service()
    script = "import sys\nsys.exit(9)\n"
    try:
        start = setup.execute_start_server(
            project_id=first_project_id,
            fxserver_path=sys.executable,
            server_data_path=str(resources_root.parent / "server-data"),
            extra_args=["-c", script],
        )
        _wait_for_crash(setup, first_project_id, start.result["process_run_id"])
        assert _wait_for_incident(container, first_project_id)
        assert container.create_incident_service().list_incidents(second_project_id) == []
    finally:
        container.close()


def test_capture_is_not_undo_ceremony(tmp_path: Path) -> None:
    container, project_id, resources_root, _ = _fixture(tmp_path)
    setup = container.create_setup_service()
    script = "import sys\nsys.exit(2)\n"
    try:
        before = _count(container, CommandExecutionRecord)
        start = setup.execute_start_server(
            project_id=project_id,
            fxserver_path=sys.executable,
            server_data_path=str(resources_root.parent / "server-data"),
            extra_args=["-c", script],
        )
        _wait_for_crash(setup, project_id, start.result["process_run_id"])
        _wait_for_incident(container, project_id)
        after = _count(container, CommandExecutionRecord)
        assert after - before == 1
        with container.session_factory() as session:
            records = session.execute(select(CommandExecutionRecord)).scalars().all()
            assert all((record.result_json or {}).get("command_type") != "CaptureIncident" for record in records)
    finally:
        container.close()


def _fixture(tmp_path: Path, name: str = "incident-project", content: str | None = None):
    container = create_application_container(tmp_path / "app-data")
    root = _project_root(tmp_path, name)
    server_data = root / "server-data"
    server_data.mkdir(parents=True, exist_ok=True)
    resources_root = root / "resources"
    resources_root.mkdir(parents=True, exist_ok=True)
    config_path = server_data / "server.cfg"
    config_path.write_text(content or _valid_config(), encoding="utf-8")
    project_id = ProjectId(container.create_project_service().execute_import_project(root_path=root).result["project_id"])
    scan = container.create_config_service().execute_rescan_config_files(project_id=project_id, scan_roots=[str(server_data)])
    config_file_id = scan["files"][0]["config_file_id"] or container.create_config_service().list_config_files(project_id)[0]["config_file_id"]
    return container, project_id, resources_root, config_file_id


def _project_root(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    (root / "resources").mkdir(parents=True)
    (root / "server-data").mkdir(parents=True)
    return root


def _valid_config() -> str:
    return 'endpoint_add_tcp "0.0.0.0:30120"\nendpoint_add_udp "0.0.0.0:30120"\nsv_licenseKey "cfxk_test_placeholder_key_value"\n'


def _config_with_secret() -> str:
    token_part_a = "MTIzNDU2Nzg5MDEyMzQ1Njc4OTAx"
    token_part_b = "Ghpcy5pcy5hLnRlc3QudG9rZW4"
    token_part_c = "c2VjcmV0X3ZhbHVlX2hlcmU"
    return (
        _valid_config()
        + f'set mysql_connection_string "mysql://user:supersecret@{token_part_a}.local/db"\n'
        + f'set discord_token "{token_part_a}.{token_part_b}.{token_part_c}"\n'
    )


def _seed_resources(container, project_id: ProjectId, resources_root: Path) -> None:
    (resources_root / "alpha").mkdir(parents=True)
    (resources_root / "alpha" / "fxmanifest.lua").write_text('fx_version "cerulean"\nname "alpha"\n', encoding="utf-8")
    container.create_resource_service().execute_rescan_resources(project_id=project_id, path_filters=[str(resources_root)])


def _seed_config_secrets(container, project_id: ProjectId, config_file_id: str) -> None:
    container.create_config_service().execute_run_secret_scan(project_id=project_id, config_file_id=config_file_id)


def _seed_git(container, project_id: ProjectId, tmp_path: Path) -> str:
    bare_path = _init_bare_repo_with_commit(tmp_path / "bare-origin")
    clone_dest = tmp_path / "incident-clone"
    result = container.create_git_service().execute_clone_repository(
        project_id=project_id,
        remote_url=str(bare_path),
        destination_path=str(clone_dest),
    )
    return result.result["git_repository_id"]


def _init_bare_repo_with_commit(bare_path: Path) -> Path:
    bare_path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--bare", str(bare_path)], check=True, capture_output=True)
    work = bare_path.parent / "seed-work"
    work.mkdir(exist_ok=True)
    repo = Repo.init(str(work))
    readme = work / "README.md"
    readme.write_text("seed\n", encoding="utf-8")
    repo.index.add([str(readme)])
    repo.index.commit("seed commit")
    branch = repo.active_branch.name
    repo.create_remote("origin", str(bare_path))
    repo.remotes.origin.push(refspec=f"{branch}:{branch}")
    return bare_path


def _wait_for_crash(setup, project_id: ProjectId, process_run_id: str) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        status = setup.get_process_status(project_id, process_run_id)
        if status["state"] == "crashed":
            return
        time.sleep(0.05)
    raise AssertionError("process did not crash in time")


def _wait_for_incident(container, project_id: ProjectId) -> dict:
    service = container.create_incident_service()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        incidents = service.list_incidents(project_id)
        if incidents:
            detail = service.get_incident(project_id, incidents[0]["incident_group_id"])
            return detail
        time.sleep(0.05)
    raise AssertionError("incident was not captured")


def _count(container, model) -> int:
    with container.session_factory() as session:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _domain_event_types(container) -> list[str]:
    with container.session_factory() as session:
        return list(session.execute(select(DomainEventRecord.event_type).order_by(DomainEventRecord.occurred_at)).scalars())
