from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from backend.adapters.persistence.models import (
    AuditEventRecord,
    CommandExecutionRecord,
    PluginCapabilityCallRecord,
    TelemetryQueueRecord,
    TelemetryRejectionRecord,
)
from backend.domain.plugin import HONEST_TRUST_WARNING, ConsentModel
from backend.domain.shared_kernel import ProjectId
from backend.infrastructure.di import create_application_container


REPO_ROOT = Path(__file__).resolve().parents[3]
TEST_PLUGIN_DIR = REPO_ROOT / "plugin-sdk" / "examples" / "test_echo_plugin"


def test_registers_only_contributions_with_granted_capability(tmp_path: Path) -> None:
    container, project_id, plugin_id, _root = _fixture(tmp_path, grants=["read-config"])
    contributions = container.create_plugin_contribution_service()
    try:
        result = contributions.register_manifest_contributions(plugin_id, project_id)
        registered_points = {item["contribution_point"] for item in result["registered"]}
        assert registered_points == {"config-validators"}
        assert any(item["reason"] == "missing_capability" for item in result["skipped"])
    finally:
        container.close()


def test_read_contribution_receives_gated_data_and_no_bypass(tmp_path: Path) -> None:
    container, project_id, plugin_id, _root = _fixture(tmp_path, grants=["read-config"])
    contributions = container.create_plugin_contribution_service()
    host = container.create_plugin_host_service()
    try:
        registered = contributions.register_manifest_contributions(plugin_id, project_id)["registered"][0]
        result = contributions.invoke_contribution(registered["contribution_id"], project_id)
        assert result["result"]["findings"][0]["severity"] == "info"
        calls = host.list_capability_calls(plugin_id, project_id)
        assert any(call["capability"] == "read-config" and call["decision"] == "granted" for call in calls)
        assert any(call["capability"] == "read-incidents" and call["decision"] == "denied" for call in calls)
    finally:
        container.close()


def test_mutating_contribution_uses_command_contract_with_undo_payload(tmp_path: Path) -> None:
    container, project_id, plugin_id, root = _fixture(tmp_path, grants=["invoke-resource-lifecycle"])
    contributions = container.create_plugin_contribution_service()
    try:
        registered = contributions.register_manifest_contributions(plugin_id, project_id)["registered"]
        action = next(item for item in registered if item["contribution_point"] == "automation-actions")
        result = contributions.invoke_contribution(action["contribution_id"], project_id)
        marker = root / "plugin-contribution-marker.txt"
        assert marker.read_text(encoding="utf-8") == "plugin contribution mutation\n"
        assert result["result"]["mutation"]["granted"] is True
        with container.session_factory() as session:
            assert int(session.scalar(select(func.count()).select_from(CommandExecutionRecord)) or 0) >= 1
            undo_events = list(session.execute(select(AuditEventRecord)).scalars())
            assert any((event.details_json or {}).get("undo") for event in undo_events)
    finally:
        container.close()


def test_producing_command_contribution_returns_output(tmp_path: Path) -> None:
    container, project_id, plugin_id, _root = _fixture(tmp_path, grants=["read-project-metadata"])
    contributions = container.create_plugin_contribution_service()
    try:
        registered = contributions.register_manifest_contributions(plugin_id, project_id)["registered"]
        command = next(item for item in registered if item["identifier"] == "atlas.test_echo.status")
        result = contributions.invoke_contribution(command["contribution_id"], project_id)
        assert "plugin command for" in result["result"]["output"]
    finally:
        container.close()


def test_contribution_failure_is_contained_and_recorded(tmp_path: Path) -> None:
    container, project_id, plugin_id, _root = _fixture(tmp_path, grants=["read-project-metadata"])
    contributions = container.create_plugin_contribution_service()
    try:
        registered = contributions.register_manifest_contributions(plugin_id, project_id)["registered"]
        command = next(item for item in registered if item["identifier"] == "atlas.test_echo.crash")
        result = contributions.invoke_contribution(command["contribution_id"], project_id)
        assert result["runtime"]["status"] == "crashed"
        assert container.create_plugin_service().get_global_settings()["global_enabled"] is True
    finally:
        container.close()


def test_disable_kill_switch_and_revoke_remove_contributions_live(tmp_path: Path) -> None:
    container, project_id, plugin_id, _root = _fixture(tmp_path, grants=["read-config"])
    contributions = container.create_plugin_contribution_service()
    plugins = container.create_plugin_service()
    try:
        registered = contributions.register_manifest_contributions(plugin_id, project_id)["registered"][0]
        plugins.revoke_capability(plugin_id, project_id, capability="read-config", idempotency_key="contrib:revoke")
        live = contributions.list_contributions(project_id, plugin_id=plugin_id)
        assert live[0]["live_enabled"] is False
        with pytest.raises(Exception):
            contributions.invoke_contribution(registered["contribution_id"], project_id)
        plugins.grant_capabilities(plugin_id, project_id, capabilities=["read-config"], trust_acknowledgment=_trust_ack())
        plugins.set_plugin_enabled(plugin_id, enabled=True)
        plugins.set_global_enabled(enabled=False)
        assert contributions.list_contributions(project_id, plugin_id=plugin_id)[0]["live_enabled"] is False
    finally:
        container.close()


def test_contribution_scoping_and_no_telemetry(tmp_path: Path) -> None:
    container = create_application_container(tmp_path / "app-data")
    contributions = container.create_plugin_contribution_service()
    root_a = _project_root(tmp_path, "project-a")
    root_b = _project_root(tmp_path, "project-b")
    try:
        project_a = ProjectId(container.create_project_service().execute_import_project(root_path=root_a).result["project_id"])
        project_b = ProjectId(container.create_project_service().execute_import_project(root_path=root_b).result["project_id"])
        plugin_id = _register_plugin(container, project_a, grants=["read-config"])
        contributions.register_manifest_contributions(plugin_id, project_a)
        assert contributions.list_contributions(project_a, plugin_id=plugin_id)
        assert contributions.list_contributions(project_b, plugin_id=plugin_id) == []
        with container.session_factory() as session:
            assert int(session.scalar(select(func.count()).select_from(TelemetryQueueRecord)) or 0) == 0
            assert int(session.scalar(select(func.count()).select_from(TelemetryRejectionRecord)) or 0) == 0
            assert int(session.scalar(select(func.count()).select_from(PluginCapabilityCallRecord)) or 0) == 0
    finally:
        container.close()


def _fixture(tmp_path: Path, *, grants: list[str]):
    container = create_application_container(tmp_path / "app-data")
    root = _project_root(tmp_path, "plugin-project")
    project_id = ProjectId(container.create_project_service().execute_import_project(root_path=root).result["project_id"])
    plugin_id = _register_plugin(container, project_id, grants=grants)
    return container, project_id, plugin_id, root


def _project_root(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    (root / "resources").mkdir(parents=True)
    (root / "server-data").mkdir(parents=True)
    (root / "server-data" / "server.cfg").write_text("endpoint_add_tcp 30120", encoding="utf-8")
    return root


def _register_plugin(container, project_id: ProjectId, *, grants: list[str]) -> str:
    plugins = container.create_plugin_service()
    manifest = json.loads((TEST_PLUGIN_DIR / "manifest.json").read_text(encoding="utf-8"))
    registered = plugins.register_plugin(manifest, source_ref=str(TEST_PLUGIN_DIR), idempotency_key=f"contrib:register:{project_id}")
    plugins.grant_capabilities(
        registered["plugin_id"],
        project_id,
        capabilities=grants,
        trust_acknowledgment=_trust_ack(),
        idempotency_key=f"contrib:grant:{project_id}:{','.join(grants)}",
    )
    plugins.set_plugin_enabled(registered["plugin_id"], enabled=True)
    return registered["plugin_id"]


def _trust_ack() -> dict:
    return {
        "consent_model": ConsentModel.INTEGRITY_NOT_SANDBOX.value,
        "acknowledged_warning": HONEST_TRUST_WARNING,
        "user_confirmed": True,
    }
