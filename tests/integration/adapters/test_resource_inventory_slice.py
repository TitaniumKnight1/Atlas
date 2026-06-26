from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select

from backend.adapters.persistence.models import TelemetryQueueRecord, TelemetryRejectionRecord
from backend.domain.shared_kernel import ProjectId
from backend.infrastructure.di import create_application_container


def test_scan_discovers_resources_and_builds_graph(tmp_path: Path) -> None:
    container, project_id, resources_root = _fixture(tmp_path)
    service = container.create_resource_service()
    try:
        result = service.execute_rescan_resources(project_id=project_id, path_filters=[str(resources_root)])
        assert result["total"] == 3
        resources = service.list_resources(project_id)
        assert len(resources) == 3
        graph = service.get_dependency_graph(project_id)
        assert graph["is_healthy"] is False
        assert any(item["finding_type"] == "missing_dependency" for item in graph["findings"])
        order = service.get_safe_start_order(project_id)
        assert order["ok"] is False
    finally:
        container.close()


def test_cycle_resource_makes_graph_unhealthy(tmp_path: Path) -> None:
    container, project_id, resources_root = _fixture(tmp_path, include_cycle=True)
    service = container.create_resource_service()
    try:
        service.execute_rescan_resources(project_id=project_id, path_filters=[str(resources_root)])
        health = service.get_graph_health(project_id)
        assert health["is_healthy"] is False
        assert any(item["finding_type"] == "cycle" for item in health["findings"])
    finally:
        container.close()


def test_dependents_and_dependencies_queries(tmp_path: Path) -> None:
    container, project_id, resources_root = _fixture(tmp_path)
    service = container.create_resource_service()
    try:
        service.execute_rescan_resources(project_id=project_id, path_filters=[str(resources_root)])
        alpha = next(item for item in service.list_resources(project_id) if item["resource_name"] == "alpha")
        deps = service.get_resource_dependencies(project_id, alpha["resource_id"], transitive=True)
        assert "beta" in deps
        beta = next(item for item in service.list_resources(project_id) if item["resource_name"] == "beta")
        dependents = service.get_resource_dependents(project_id, beta["resource_id"], transitive=True)
        assert "alpha" in dependents
    finally:
        container.close()


def test_project_isolation_blocks_foreign_resource(tmp_path: Path) -> None:
    container, first_project_id, resources_root = _fixture(tmp_path, name="alpha")
    second_project_id = ProjectId(container.create_project_service().execute_import_project(root_path=_project_root(tmp_path, "beta")).result["project_id"])
    service = container.create_resource_service()
    try:
        service.execute_rescan_resources(project_id=first_project_id, path_filters=[str(resources_root)])
        resource_id = service.list_resources(first_project_id)[0]["resource_id"]
        try:
            service.get_resource(second_project_id, resource_id)
        except Exception as error:  # noqa: BLE001
            assert "not found" in str(error).lower()
        else:
            raise AssertionError("cross-project resource access was allowed")
    finally:
        container.close()


def test_scan_does_not_write_resource_content_to_telemetry(tmp_path: Path) -> None:
    container, project_id, resources_root = _fixture(tmp_path)
    service = container.create_resource_service()
    try:
        service.execute_rescan_resources(project_id=project_id, path_filters=[str(resources_root)])
        with container.session_factory() as session:
            assert int(session.scalar(select(func.count()).select_from(TelemetryQueueRecord)) or 0) == 0
            assert int(session.scalar(select(func.count()).select_from(TelemetryRejectionRecord)) or 0) == 0
    finally:
        container.close()


def _fixture(tmp_path: Path, name: str = "resource-project", include_cycle: bool = False):
    container = create_application_container(tmp_path / "app-data")
    root = _project_root(tmp_path, name)
    resources_root = root / "resources"
    resources_root.mkdir(parents=True)
    server_data = root / "server-data"
    server_data.mkdir(parents=True)
    (server_data / "server.cfg").write_text(
        'endpoint_add_tcp "0.0.0.0:30120"\nendpoint_add_udp "0.0.0.0:30120"\nsv_licenseKey "cfxk_test"\nensure alpha\n',
        encoding="utf-8",
    )
    _write_resource(resources_root / "alpha", "alpha", ["beta", "missing-lib"])
    _write_resource(resources_root / "beta", "beta", ["gamma"])
    _write_resource(resources_root / "gamma", "gamma", [])
    if include_cycle:
        _write_resource(resources_root / "cycle_a", "cycle_a", ["cycle_b"])
        _write_resource(resources_root / "cycle_b", "cycle_b", ["cycle_a"])
    project_id = ProjectId(container.create_project_service().execute_import_project(root_path=root).result["project_id"])
    return container, project_id, resources_root


def _project_root(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    root.mkdir(parents=True)
    return root


def _write_resource(path: Path, name: str, dependencies: list[str]) -> None:
    path.mkdir(parents=True)
    deps = ",\n  ".join(f"'{item}'" for item in dependencies)
    body = f"""fx_version 'cerulean'
game 'gta5'
version '1.0.0'
dependencies {{
  {deps}
}}
"""
    (path / "fxmanifest.lua").write_text(body, encoding="utf-8")
