from __future__ import annotations

import builtins
import json
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import func, select

from backend.adapters.persistence.models import CommandExecutionRecord, PluginRegistrationRecord, TelemetryQueueRecord, TelemetryRejectionRecord
from backend.domain.plugin import HONEST_TRUST_WARNING, ConsentModel
from backend.domain.shared_kernel import ProjectId
from backend.infrastructure.di import create_application_container


def test_manifest_validation_accepts_well_formed_manifest(tmp_path: Path) -> None:
    result = _validate(tmp_path, _valid_manifest())
    assert result["valid"] is True
    assert result["plugin_id"] == "com.example.config-helper"
    assert "read-config" in result["requested_capabilities"]


def test_manifest_validation_rejects_unknown_capability(tmp_path: Path) -> None:
    manifest = _valid_manifest()
    manifest["requested_capabilities"] = ["read-config", "admin-all-access"]
    result = _validate(tmp_path, manifest)
    assert result["valid"] is False
    assert any(issue["code"] == "unknown_capability" for issue in result["issues"])


def test_manifest_validation_rejects_wildcard_capability(tmp_path: Path) -> None:
    manifest = _valid_manifest()
    manifest["requested_capabilities"] = ["*"]
    result = _validate(tmp_path, manifest)
    assert result["valid"] is False
    assert any(issue["code"] == "wildcard_capability" for issue in result["issues"])


def test_manifest_validation_rejects_over_broad_unjustified_capability(tmp_path: Path) -> None:
    manifest = _valid_manifest()
    manifest["requested_capabilities"] = ["read-config", "network"]
    result = _validate(tmp_path, manifest)
    assert result["valid"] is False
    assert any(issue["code"] == "over_broad" for issue in result["issues"])


def test_manifest_validation_rejects_all_capabilities(tmp_path: Path) -> None:
    manifest = _valid_manifest()
    manifest["requested_capabilities"] = [
        "read-project-metadata",
        "read-config",
        "read-incidents",
        "read-git-metadata",
        "invoke-resource-lifecycle",
        "invoke-backup-restore",
        "invoke-setup-process",
        "filesystem-read",
        "filesystem-write",
        "network",
        "telemetry-submit",
        "contribute-automation",
        "contribute-monitoring",
        "render-ui",
    ]
    result = _validate(tmp_path, manifest)
    assert result["valid"] is False
    assert any(issue["code"] == "over_broad" for issue in result["issues"])


def test_registration_records_plugin_without_executing_code(tmp_path: Path) -> None:
    container = create_application_container(tmp_path / "app-data")
    plugins = container.create_plugin_service()
    manifest_path = tmp_path / "plugin.manifest.json"
    manifest_path.write_text(json.dumps(_valid_manifest()), encoding="utf-8")
    import_tracker = {"count": 0}
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):  # noqa: ANN001
        if name.startswith("com.") or "plugin_entry" in name:
            import_tracker["count"] += 1
        return original_import(name, *args, **kwargs)

    try:
        with patch("builtins.__import__", side_effect=guarded_import):
            registered = plugins.register_plugin(_valid_manifest(), source_ref=str(manifest_path), idempotency_key="reg:1")
        assert registered["trust_status"] == "pending_consent"
        assert registered["is_enabled"] is False
        assert registered["requested_capabilities"] == ["read-config"]
        assert import_tracker["count"] == 0
        loaded = plugins.validate_manifest_file(str(manifest_path))
        assert loaded["valid"] is True
    finally:
        container.close()


def test_no_capability_granted_without_explicit_grant(tmp_path: Path) -> None:
    container, project_id = _fixture(tmp_path)
    plugins = container.create_plugin_service()
    try:
        registered = plugins.register_plugin(_valid_manifest(), idempotency_key="reg:2")
        caps = plugins.list_capabilities(registered["plugin_id"], project_id)
        assert caps["granted_capabilities"] == []
        assert caps["requested_capabilities"] == ["read-config"]
        try:
            plugins.set_plugin_enabled(registered["plugin_id"], enabled=True)
        except Exception as error:  # noqa: BLE001
            assert "grant" in str(error).lower()
        else:
            raise AssertionError("enable should fail without granted capabilities")
    finally:
        container.close()


def test_grant_and_revoke_are_audited(tmp_path: Path) -> None:
    container, project_id = _fixture(tmp_path)
    plugins = container.create_plugin_service()
    try:
        registered = plugins.register_plugin(_valid_manifest(), idempotency_key="reg:3")
        plugins.grant_capabilities(
            registered["plugin_id"],
            project_id,
            capabilities=["read-config"],
            trust_acknowledgment=_trust_ack(),
            idempotency_key="grant:1",
        )
        with container.session_factory() as session:
            assert int(session.scalar(select(func.count()).select_from(CommandExecutionRecord)) or 0) >= 1
        plugins.revoke_capability(registered["plugin_id"], project_id, capability="read-config", idempotency_key="revoke:1")
        caps = plugins.list_capabilities(registered["plugin_id"], project_id)
        assert caps["granted_capabilities"] == []
        assert caps["trust_status"] == "revoked"
    finally:
        container.close()


def test_honest_trust_posture_recorded_on_grant(tmp_path: Path) -> None:
    container, project_id = _fixture(tmp_path)
    plugins = container.create_plugin_service()
    try:
        registered = plugins.register_plugin(_valid_manifest(), idempotency_key="reg:4")
        caps = plugins.grant_capabilities(
            registered["plugin_id"],
            project_id,
            capabilities=["read-config"],
            trust_acknowledgment=_trust_ack(),
        )
        assert caps["consent_model"] == ConsentModel.INTEGRITY_NOT_SANDBOX.value
        assert caps["trust_acknowledgment"]["acknowledged_warning"] == HONEST_TRUST_WARNING
        assert "no real security sandbox" in HONEST_TRUST_WARNING.lower()
    finally:
        container.close()


def test_grant_rejects_bad_trust_acknowledgment(tmp_path: Path) -> None:
    container, project_id = _fixture(tmp_path)
    plugins = container.create_plugin_service()
    try:
        registered = plugins.register_plugin(_valid_manifest(), idempotency_key="reg:5")
        bad_ack = _trust_ack()
        bad_ack["user_confirmed"] = False
        try:
            plugins.grant_capabilities(registered["plugin_id"], project_id, capabilities=["read-config"], trust_acknowledgment=bad_ack)
        except Exception as error:  # noqa: BLE001
            assert "confirmation" in str(error).lower()
        else:
            raise AssertionError("grant should require user_confirmed")
    finally:
        container.close()


def test_global_kill_switch_and_per_plugin_disable(tmp_path: Path) -> None:
    container, project_id = _fixture(tmp_path)
    plugins = container.create_plugin_service()
    try:
        registered = plugins.register_plugin(_valid_manifest(), idempotency_key="reg:6")
        plugins.grant_capabilities(
            registered["plugin_id"],
            project_id,
            capabilities=["read-config"],
            trust_acknowledgment=_trust_ack(),
        )
        plugins.set_plugin_enabled(registered["plugin_id"], enabled=True)
        plugins.set_global_enabled(enabled=False)
        try:
            plugins.set_plugin_enabled(registered["plugin_id"], enabled=True)
        except Exception as error:  # noqa: BLE001
            assert "kill switch" in str(error).lower()
        else:
            raise AssertionError("enable should fail when global kill switch off")
        plugins.set_global_enabled(enabled=True)
        plugins.set_plugin_enabled(registered["plugin_id"], enabled=False)
        updated = plugins.get_plugin(registered["plugin_id"])
        assert updated["is_enabled"] is False
        assert updated["registration_status"] == "disabled"
    finally:
        container.close()


def test_project_scoping_isolation(tmp_path: Path) -> None:
    container = create_application_container(tmp_path / "app-data")
    plugins = container.create_plugin_service()
    root_a = _project_root(tmp_path, "plugin-a")
    root_b = _project_root(tmp_path, "plugin-b")
    try:
        project_a = ProjectId(container.create_project_service().execute_import_project(root_path=root_a).result["project_id"])
        project_b = ProjectId(container.create_project_service().execute_import_project(root_path=root_b).result["project_id"])
        registered = plugins.register_plugin(_valid_manifest(), idempotency_key="reg:7")
        plugins.grant_capabilities(registered["plugin_id"], project_a, capabilities=["read-config"], trust_acknowledgment=_trust_ack())
        caps_a = plugins.list_capabilities(registered["plugin_id"], project_a)
        caps_b = plugins.list_capabilities(registered["plugin_id"], project_b)
        assert caps_a["granted_capabilities"] == ["read-config"]
        assert caps_b["granted_capabilities"] == []
    finally:
        container.close()


def test_plugin_registry_not_sent_to_telemetry(tmp_path: Path) -> None:
    container, project_id = _fixture(tmp_path)
    plugins = container.create_plugin_service()
    try:
        registered = plugins.register_plugin(_valid_manifest(), idempotency_key="reg:8")
        plugins.grant_capabilities(
            registered["plugin_id"],
            project_id,
            capabilities=["read-config"],
            trust_acknowledgment=_trust_ack(),
        )
        with container.session_factory() as session:
            assert int(session.scalar(select(func.count()).select_from(TelemetryQueueRecord)) or 0) == 0
            assert int(session.scalar(select(func.count()).select_from(TelemetryRejectionRecord)) or 0) == 0
            assert int(session.scalar(select(func.count()).select_from(PluginRegistrationRecord)) or 0) == 1
    finally:
        container.close()


def test_declarative_manifest_reader_never_imports_plugin_dir(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "evil-plugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.manifest.json").write_text(json.dumps(_valid_manifest()), encoding="utf-8")
    (plugin_dir / "entry.py").write_text("raise RuntimeError('should not execute')\n", encoding="utf-8")
    container = create_application_container(tmp_path / "app-data")
    try:
        result = container.create_plugin_service().validate_manifest_file(str(plugin_dir / "plugin.manifest.json"))
        assert result["valid"] is True
        assert "entry.py" not in str(result)
    finally:
        container.close()


def _validate(tmp_path: Path, manifest: dict) -> dict:
    container = create_application_container(tmp_path / "validate-app-data")
    try:
        return container.create_plugin_service().validate_manifest(manifest)
    finally:
        container.close()


def _fixture(tmp_path: Path):
    container = create_application_container(tmp_path / "app-data")
    root = _project_root(tmp_path, "plugin-project")
    project_id = ProjectId(container.create_project_service().execute_import_project(root_path=root).result["project_id"])
    return container, project_id


def _project_root(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    (root / "resources").mkdir(parents=True)
    (root / "server-data").mkdir(parents=True)
    return root


def _valid_manifest() -> dict:
    return {
        "manifest_version": "1",
        "plugin_id": "com.example.config-helper",
        "name": "Config Helper",
        "version": "1.0.0",
        "author": "Example Author",
        "contribution_points": ["config-validators"],
        "requested_capabilities": ["read-config"],
    }


def _trust_ack() -> dict:
    return {
        "consent_model": ConsentModel.INTEGRITY_NOT_SANDBOX.value,
        "acknowledged_warning": HONEST_TRUST_WARNING,
        "user_confirmed": True,
    }

