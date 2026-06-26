from __future__ import annotations

import json
import os
from pathlib import Path

from sqlalchemy import func, select

from backend.adapters.persistence.models import CommandExecutionRecord, PluginCapabilityCallRecord, TelemetryQueueRecord, TelemetryRejectionRecord
from backend.domain.plugin import HONEST_TRUST_WARNING, ConsentModel
from backend.domain.plugin.runtime_types import PLUGIN_HANG_KILL_TIMEOUT_SECONDS, PluginRuntimeStatus
from backend.domain.shared_kernel import ProjectId
from backend.infrastructure.di import create_application_container


REPO_ROOT = Path(__file__).resolve().parents[3]
TEST_PLUGIN_DIR = REPO_ROOT / "plugin-sdk" / "examples" / "test_echo_plugin"


def test_plugin_runs_in_isolated_subprocess(tmp_path: Path) -> None:
    container, project_id, plugin_id, _root = _registered_plugin(tmp_path)
    host = container.create_plugin_host_service()
    try:
        result = host.run_plugin(plugin_id, project_id, mode="normal", call_timeout_seconds=PLUGIN_HANG_KILL_TIMEOUT_SECONDS)
        assert result["pid"] != result["atlas_pid"]
        assert result["pid"] != os.getpid()
        calls = host.list_capability_calls(plugin_id, project_id)
        assert any(call["capability"] == "read-config" and call["decision"] == "granted" for call in calls)
        assert any(call["capability"] == "read-incidents" and call["decision"] == "denied" for call in calls)
    finally:
        container.close()


def test_ungranted_capability_denied_and_audited(tmp_path: Path) -> None:
    container, project_id, plugin_id, _root = _registered_plugin(tmp_path)
    host = container.create_plugin_host_service()
    try:
        host.run_plugin(plugin_id, project_id, mode="normal", call_timeout_seconds=PLUGIN_HANG_KILL_TIMEOUT_SECONDS)
        denied = [call for call in host.list_capability_calls(plugin_id, project_id) if call["capability"] == "read-incidents"]
        assert len(denied) == 1
        assert denied[0]["decision"] == "denied"
        assert denied[0]["outcome"] == "denied"
        assert denied[0]["response"]["granted"] is False
    finally:
        container.close()


def test_plugin_mutation_via_command_contract(tmp_path: Path) -> None:
    container, project_id, plugin_id, root = _registered_plugin(tmp_path, grant_write=True)
    host = container.create_plugin_host_service()
    try:
        host.run_plugin(plugin_id, project_id, mode="mutate", call_timeout_seconds=PLUGIN_HANG_KILL_TIMEOUT_SECONDS)
        marker = root / "plugin-marker.txt"
        assert marker.exists()
        assert marker.read_text(encoding="utf-8") == "plugin-mediated-write\n"
        with container.session_factory() as session:
            assert int(session.scalar(select(func.count()).select_from(CommandExecutionRecord)) or 0) >= 1
        granted = [call for call in host.list_capability_calls(plugin_id, project_id) if call["capability"] == "filesystem-write"]
        assert granted and granted[0]["decision"] == "granted"
    finally:
        container.close()


def test_crashing_plugin_does_not_crash_atlas(tmp_path: Path) -> None:
    container, project_id, plugin_id, _root = _registered_plugin(tmp_path)
    host = container.create_plugin_host_service()
    try:
        result = host.run_plugin(plugin_id, project_id, mode="crash", call_timeout_seconds=PLUGIN_HANG_KILL_TIMEOUT_SECONDS)
        assert result["status"] == PluginRuntimeStatus.CRASHED.value
        assert container.create_plugin_service().get_global_settings()["global_enabled"] is True
    finally:
        container.close()


def test_hanging_plugin_is_killed_without_orphan(tmp_path: Path) -> None:
    import time

    container, project_id, plugin_id, _root = _registered_plugin(tmp_path)
    host = container.create_plugin_host_service()
    try:
        result = host.run_plugin(plugin_id, project_id, mode="hang", call_timeout_seconds=PLUGIN_HANG_KILL_TIMEOUT_SECONDS)
        assert result["status"] == PluginRuntimeStatus.TIMED_OUT.value
        child_pid = result["pid"]
        assert child_pid is not None
        for _ in range(30):
            if not _process_exists(child_pid):
                break
            time.sleep(0.1)
        assert not _process_exists(child_pid)
    finally:
        container.close()


def test_kill_switch_prevents_launch(tmp_path: Path) -> None:
    container, project_id, plugin_id, _root = _registered_plugin(tmp_path)
    plugins = container.create_plugin_service()
    host = container.create_plugin_host_service()
    try:
        plugins.set_global_enabled(enabled=False)
        try:
            host.run_plugin(plugin_id, project_id, mode="normal")
        except Exception as error:  # noqa: BLE001
            assert "kill switch" in str(error).lower()
        else:
            raise AssertionError("launch should fail when kill switch disabled")
    finally:
        container.close()


def test_capability_revocation_denies_subsequent_calls(tmp_path: Path) -> None:
    container, project_id, plugin_id, _root = _registered_plugin(tmp_path)
    plugins = container.create_plugin_service()
    host = container.create_plugin_host_service()
    try:
        host.run_plugin(plugin_id, project_id, mode="normal", call_timeout_seconds=PLUGIN_HANG_KILL_TIMEOUT_SECONDS)
        before = [call for call in host.list_capability_calls(plugin_id, project_id) if call["capability"] == "read-config"]
        assert before and before[0]["decision"] == "granted"
        plugins.revoke_capability(plugin_id, project_id, capability="read-config", idempotency_key="revoke:host:1")
        plugins.grant_capabilities(
            plugin_id,
            project_id,
            capabilities=["read-incidents"],
            trust_acknowledgment=_trust_ack(),
            idempotency_key="grant:incidents",
        )
        plugins.set_plugin_enabled(plugin_id, enabled=True)
        host.run_plugin(plugin_id, project_id, mode="normal", call_timeout_seconds=PLUGIN_HANG_KILL_TIMEOUT_SECONDS)
        config_calls = [call for call in host.list_capability_calls(plugin_id, project_id) if call["capability"] == "read-config"]
        assert len(config_calls) >= 2
        assert config_calls[0]["decision"] == "denied"
    finally:
        container.close()


def test_plugin_failure_data_local_not_telemetry(tmp_path: Path) -> None:
    container, project_id, plugin_id, _root = _registered_plugin(tmp_path)
    host = container.create_plugin_host_service()
    try:
        result = host.run_plugin(plugin_id, project_id, mode="crash", call_timeout_seconds=PLUGIN_HANG_KILL_TIMEOUT_SECONDS)
        with container.session_factory() as session:
            assert int(session.scalar(select(func.count()).select_from(TelemetryQueueRecord)) or 0) == 0
            assert int(session.scalar(select(func.count()).select_from(TelemetryRejectionRecord)) or 0) == 0
        runtime = host.get_runtime(result["runtime_id"], project_id)
        assert runtime.get("failure_summary", {}).get("local_only") is True
    finally:
        container.close()


def test_capability_call_project_scoping(tmp_path: Path) -> None:
    container = create_application_container(tmp_path / "app-data")
    root_a = tmp_path / "project-a"
    root_b = tmp_path / "project-b"
    root_a.mkdir(parents=True)
    (root_a / "server-data").mkdir()
    root_b.mkdir(parents=True)
    (root_b / "server-data").mkdir()
    try:
        project_a = ProjectId(container.create_project_service().execute_import_project(root_path=root_a).result["project_id"])
        project_b = ProjectId(container.create_project_service().execute_import_project(root_path=root_b).result["project_id"])
        plugin_id = _register_test_plugin(container, grant_project=project_a)
        container.create_plugin_service().set_plugin_enabled(plugin_id, enabled=True)
        host = container.create_plugin_host_service()
        host.run_plugin(plugin_id, project_a, mode="normal", call_timeout_seconds=PLUGIN_HANG_KILL_TIMEOUT_SECONDS)
        with container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext
            from backend.adapters.persistence import PluginRepository

            calls_b = PluginRepository(RepositoryContext(session=session, project_id=project_b)).list_capability_calls(plugin_id, project_b)
            assert calls_b == []
            count_a = int(
                session.scalar(
                    select(func.count()).select_from(PluginCapabilityCallRecord).where(PluginCapabilityCallRecord.project_id == str(project_a))
                )
                or 0
            )
            assert count_a >= 1
    finally:
        container.close()


def _registered_plugin(tmp_path: Path, *, grant_write: bool = False):
    container = create_application_container(tmp_path / "app-data")
    root = tmp_path / "plugin-project"
    root.mkdir(parents=True)
    (root / "server-data").mkdir()
    (root / "server-data" / "server.cfg").write_text("endpoint_add_tcp 30120", encoding="utf-8")
    project_id = ProjectId(container.create_project_service().execute_import_project(root_path=root).result["project_id"])
    plugin_id = _register_test_plugin(container, grant_project=project_id, grant_write=grant_write)
    container.create_plugin_service().set_plugin_enabled(plugin_id, enabled=True)
    return container, project_id, plugin_id, root


def _register_test_plugin(container, *, grant_project: ProjectId, grant_write: bool = False) -> str:
    plugins = container.create_plugin_service()
    manifest = json.loads((TEST_PLUGIN_DIR / "manifest.json").read_text(encoding="utf-8"))
    registered = plugins.register_plugin(manifest, source_ref=str(TEST_PLUGIN_DIR), idempotency_key="host:register")
    caps = ["read-config"] if not grant_write else ["read-config", "filesystem-write"]
    plugins.grant_capabilities(
        registered["plugin_id"],
        grant_project,
        capabilities=caps,
        trust_acknowledgment=_trust_ack(),
        idempotency_key="host:grant",
    )
    return registered["plugin_id"]


def _trust_ack() -> dict:
    return {
        "consent_model": ConsentModel.INTEGRITY_NOT_SANDBOX.value,
        "acknowledged_warning": HONEST_TRUST_WARNING,
        "user_confirmed": True,
    }


def _process_exists(pid: int) -> bool:
    if os.name == "nt":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True
