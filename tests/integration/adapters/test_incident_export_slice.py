from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select

from backend.adapters.persistence import IncidentRepository
from backend.adapters.persistence.models import (
    IncidentExportRecord,
    TelemetryQueueRecord,
    TelemetryRejectionRecord,
)
from backend.domain.incident import ContextSnapshotType, IncidentCategory, IncidentGroupStatus, IncidentSeverity, IncidentSourceType
from backend.domain.shared_kernel import ProjectId, StableIdentifier
from backend.infrastructure.di import create_application_container

PLANTED_SECRETS: dict[str, str] = {
    "license_key": "cfxk_test123456789012345678901234",
    "discord_token": "MTIzNDU2Nzg5MDEyMzQ1Njc4OTAx.Ghpcy5pcy5hLnRlc3QudG9rZW4.c2VjcmV0X3ZhbHVlX2hlcmU",
    "webhook_url": "https://discord.com/api/webhooks/123456789012345678/abcdefghijklmnopqrstuvwxyz123456",
    "database_connection_string": "postgres://dbuser:supersecret@db.internal:5432/fivem",
    "api_key": "api_key=sk-live-supersecretvalue123456",
    "ipv4": "192.168.50.42",
    "ipv6": "2001:0db8:85a3:0000:0000:8a2e:0370:7334",
    "steam_id": "76561198000000000",
    "rockstar_id": "license:deadbeef0123456789abcdef01234567",
    "credential_url": "https://deploy:supersecret@github.com/org/private-repo.git",
    "player_identifier": 'player_id="steam:110000112345678"',
    "unknown_secret": "Zmx1ZmZ5X2Jhc2U2NF9zZWNyZXRfdG9rZW5fdmFsdWU",
}


def test_export_single_sanitized_path_redacts_all_planted_secrets(tmp_path: Path) -> None:
    container, project_id, group_id = _seed_incident_with_secrets(tmp_path)
    service = container.create_incident_service()
    try:
        result = service.export_incident_markdown(project_id, incident_group_id=group_id)
        markdown = result["markdown"]
        assert result["sanitized"] is True
        for category, planted in PLANTED_SECRETS.items():
            assert planted not in markdown, f"{category} leaked into export"
            assert "[REDACTED:" in markdown
        assert "resource alpha failed" in markdown
        assert result["redaction_summary"]["redaction_count"] >= len(PLANTED_SECRETS)
        assert _count(container, IncidentExportRecord) == 1
        with container.session_factory() as session:
            record = session.execute(select(IncidentExportRecord)).scalar_one()
            stored = Path(record.local_file_path).read_text(encoding="utf-8")
            for planted in PLANTED_SECRETS.values():
                assert planted not in stored
        assert _count(container, TelemetryQueueRecord) == 0
        assert _count(container, TelemetryRejectionRecord) == 0
    finally:
        container.close()


def test_no_raw_export_bypass_exists(tmp_path: Path) -> None:
    container, project_id, group_id = _seed_incident_with_secrets(tmp_path)
    service = container.create_incident_service()
    try:
        result = service.export_incident_markdown(project_id, incident_group_id=group_id)
        assert result["sanitized"] is True
        assert "redaction_summary" in result
        assert "[REDACTED:" in result["markdown"]
        # Service exposes only sanitized markdown key — no raw_markdown field.
        assert "raw_markdown" not in result
    finally:
        container.close()


def test_project_isolation_for_exports(tmp_path: Path) -> None:
    container, first_project_id, group_id = _seed_incident_with_secrets(tmp_path, name="alpha")
    second_project_id = ProjectId(
        container.create_project_service().execute_import_project(root_path=_project_root(tmp_path, "beta")).result["project_id"]
    )
    service = container.create_incident_service()
    try:
        service.export_incident_markdown(first_project_id, incident_group_id=group_id)
        try:
            service.list_incident_exports(second_project_id, group_id)
        except Exception as error:  # noqa: BLE001
            assert "not found" in str(error).lower()
        else:
            raise AssertionError("cross-project export list was allowed")
    finally:
        container.close()


def test_list_exports_returns_metadata_without_unsanitized_payload(tmp_path: Path) -> None:
    container, project_id, group_id = _seed_incident_with_secrets(tmp_path)
    service = container.create_incident_service()
    try:
        exported = service.export_incident_markdown(project_id, incident_group_id=group_id)
        rows = service.list_incident_exports(project_id, group_id)
        assert len(rows) == 1
        assert rows[0]["incident_export_id"] == exported["incident_export_id"]
        assert rows[0]["content_hash"] == exported["content_hash"]
        assert "markdown" not in rows[0]
        for planted in PLANTED_SECRETS.values():
            assert planted not in json.dumps(rows[0])
    finally:
        container.close()


def test_crash_capture_then_export_is_sanitized(tmp_path: Path) -> None:
    container, project_id, resources_root, _ = _fixture(tmp_path)
    setup = container.create_setup_service()
    script = (
        "import sys\n"
        f"print('license {PLANTED_SECRETS['license_key']}', flush=True)\n"
        f"print('ip {PLANTED_SECRETS['ipv4']}', flush=True)\n"
        "sys.exit(7)\n"
    )
    try:
        start = setup.execute_start_server(
            project_id=project_id,
            fxserver_path=sys.executable,
            server_data_path=str(resources_root.parent / "server-data"),
            extra_args=["-c", script],
        )
        _wait_for_crash(setup, project_id, start.result["process_run_id"])
        time.sleep(0.3)
        groups = container.create_incident_service().list_incidents(project_id)
        exported = container.create_incident_service().export_incident_markdown(
            project_id, incident_group_id=groups[0]["incident_group_id"]
        )
        for planted in (PLANTED_SECRETS["license_key"], PLANTED_SECRETS["ipv4"]):
            assert planted not in exported["markdown"]
        assert "exit code" in exported["markdown"].lower() or "exit_code" in exported["markdown"]
    finally:
        container.close()


def _seed_incident_with_secrets(tmp_path: Path, name: str = "export-project"):
    container = create_application_container(tmp_path / "app-data")
    root = _project_root(tmp_path, name)
    project_id = ProjectId(container.create_project_service().execute_import_project(root_path=root).result["project_id"])
    group_id = str(StableIdentifier.new())
    occurrence_id = StableIdentifier.new()
    now = datetime.now(UTC)
    secret_lines = "\n".join(f"{key}={value}" for key, value in PLANTED_SECRETS.items())
    logs = {
        "availability": "bounded_tail_only",
        "stdout_tail": [secret_lines, "Error: resource alpha failed to start"],
        "stderr_tail": [f"connecting from {PLANTED_SECRETS['ipv4']}"],
    }
    config_excerpt = {
        "config_files": [{"path": "server-data/server.cfg", "validation_status": "ok"}],
        "secret_findings": [{"secret_type": "cfx_license_key", "path": "server-data/server.cfg", "status": "open"}],
    }
    environment = {
        "repositories": [
            {
                "remote_url": PLANTED_SECRETS["credential_url"],
                "head_commit_sha": "abc123",
                "current_branch": "main",
            }
        ]
    }
    snapshots = [
        _snapshot(ContextSnapshotType.RUNTIME, {"state": "crashed", "exit_code": 7, "pid": 4242}),
        _snapshot(ContextSnapshotType.LOGS, logs),
        _snapshot(ContextSnapshotType.CONFIG_EXCERPT, config_excerpt),
        _snapshot(ContextSnapshotType.ENVIRONMENT, environment),
        _snapshot(ContextSnapshotType.RESOURCES, {"resources": [{"resource_name": "alpha"}]}),
        _snapshot(ContextSnapshotType.STARTUP_ORDER, {"ok": True, "order": ["alpha"]}),
    ]
    with container.create_unit_of_work(project_id) as uow:
        uow.begin()
        repository = uow.repository(IncidentRepository)
        repository.create_group(
            incident_group_id=StableIdentifier(group_id),
            project_id=project_id,
            fingerprint="test-fingerprint-export",
            title="Server process exited unexpectedly with code 7",
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
            message="Server process exited unexpectedly with code 7",
        )
        uow.session.flush()
        repository.add_context_snapshots(str(occurrence_id), snapshots)
        repository.record_fingerprint(
            incident_group_id=group_id,
            fingerprint="test-fingerprint-export",
            algorithm_version="atlas-crash-v1",
            components={"exit_code": 7, "log_signature": "abc"},
            created_at=now,
        )
        uow.commit()
    return container, project_id, group_id


def _snapshot(context_type: ContextSnapshotType, payload: dict) -> dict:
    return {
        "context_type": context_type.value,
        "snapshot_json": payload,
        "redaction_state": "raw_local",
        "captured_at": datetime.now(UTC).isoformat(),
    }


def _fixture(tmp_path: Path, name: str = "export-live-project"):
    container = create_application_container(tmp_path / "app-data")
    root = _project_root(tmp_path, name)
    (root / "server-data").mkdir(parents=True, exist_ok=True)
    (root / "server-data" / "server.cfg").write_text('sv_licenseKey "cfxk_test"\n', encoding="utf-8")
    project_id = ProjectId(container.create_project_service().execute_import_project(root_path=root).result["project_id"])
    return container, project_id, root / "resources", None


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


def _count(container, model) -> int:
    with container.session_factory() as session:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)
