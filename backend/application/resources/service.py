from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from backend.adapters.filesystem.resource_scanner import LocalResourceScanner, infer_resource_type
from backend.adapters.persistence import ProjectRepository, ResourceRepository
from backend.adapters.persistence.models import ProjectPathRecord, ResourceVersionRecord
from backend.domain.resources import (
    DependencyGraphBuilder,
    DependencyType,
    EnabledState,
    HealthStatus,
    build_dependency_graph,
    dependency_issue_detected,
    detect_duplicate_resource_names,
    resource_inventory_changed,
    resources_scanned,
)
from backend.domain.shared_kernel import ErrorCode, ProjectId, StableIdentifier
from backend.infrastructure.unit_of_work import RepositoryContext


class ResourceApplicationError(RuntimeError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


class ResourceApplicationService:
    def __init__(self, *, container: Any, filesystem: Any) -> None:
        self._container = container
        self._filesystem = filesystem
        self._scanner = LocalResourceScanner(filesystem)

    def execute_rescan_resources(self, *, project_id: ProjectId, path_filters: list[str] | None = None) -> dict[str, Any]:
        now = datetime.now(UTC)
        discovered = self._scanner.discover_resources([Path(item) for item in (path_filters or self._resource_roots(project_id))])
        enabled_map = self._enabled_resources(project_id)
        added = changed = 0
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            self._require_project(uow.repository(ProjectRepository), project_id)
            repository = uow.repository(ResourceRepository)
            existing_by_name = {record.resource_name: record for record in repository.list_resources(project_id)}
            stored: list[tuple[Any, Any]] = []
            for item in discovered:
                prior = existing_by_name.get(item.resource_name)
                resource_id = StableIdentifier(prior.resource_id) if prior else StableIdentifier.new()
                if item.resource_name in enabled_map:
                    enabled_state = EnabledState.ENABLED.value
                    startup_order = list(enabled_map.keys()).index(item.resource_name) + 1
                else:
                    enabled_state = EnabledState.DISABLED.value
                    startup_order = None
                record = repository.upsert_resource(
                    resource_id=resource_id,
                    project_id=project_id,
                    resource_name=item.resource_name,
                    relative_path=item.relative_path,
                    resource_type=infer_resource_type(item.manifest, item.resource_name),
                    enabled_state=enabled_state,
                    startup_order=startup_order,
                    current_version_id=None,
                    git_repository_id=None,
                    created_at=now,
                    updated_at=now,
                )
                uow.session.flush()
                version = repository.add_version(
                    version_id=StableIdentifier.new(),
                    resource_id=record.resource_id,
                    version_label=item.manifest.version,
                    content_hash=item.content_hash,
                    manifest_json=_manifest_json(item),
                    detected_at=now,
                    source_ref=item.absolute_path,
                )
                record.current_version_id = version.resource_version_id
                repository.upsert_install_source(
                    resource_id=record.resource_id,
                    source_type="local",
                    source_uri=item.relative_path,
                    metadata={"absolute_path": item.absolute_path},
                    trusted_at=now,
                )
                stored.append((record, item))
                if prior:
                    changed += 1
                else:
                    added += 1
            name_to_id = {record.resource_name: record.resource_id for record, _ in stored}
            for record, item in stored:
                repository.replace_dependencies(
                    project_id=project_id,
                    source_resource_id=record.resource_id,
                    dependencies=[
                        {
                            "target_name": dependency,
                            "dependency_type": DependencyType.REQUIRES.value,
                            "declared_in_path": item.manifest_path,
                        }
                        for dependency in item.manifest.dependencies
                    ],
                    detected_at=now,
                    name_to_id=name_to_id,
                )
            graph = self._build_graph_snapshot(project_id)
            for record, item in stored:
                health = _health_for_item(item, enabled_map.get(item.resource_name, False), graph, record.resource_name)
                repository.replace_health_snapshot(
                    resource_id=record.resource_id,
                    health_status=health["health_status"],
                    sampled_at=now,
                    details=health,
                )
            for finding in graph.findings:
                uow.collect_event(dependency_issue_detected(project_id, finding.finding_type.value, finding.nodes))
            uow.collect_event(resources_scanned(project_id, added + changed))
            uow.collect_event(resource_inventory_changed(project_id, added, 0, changed))
            uow.commit()
        return {"project_id": str(project_id), "added": added, "changed": changed, "total": len(discovered)}

    def list_resources(self, project_id: ProjectId) -> list[dict[str, Any]]:
        with self._container.session_factory() as session:
            return [_resource_data(record) for record in ResourceRepository(RepositoryContext(session=session, project_id=project_id)).list_resources(project_id)]

    def get_resource(self, project_id: ProjectId, resource_id: str) -> dict[str, Any]:
        return _resource_data(self._get_resource(project_id, resource_id))

    def get_dependency_graph(self, project_id: ProjectId, root: str | None = None) -> dict[str, Any]:
        return _graph_data(self._build_graph_snapshot(project_id, root=root), root=root)

    def get_graph_health(self, project_id: ProjectId) -> dict[str, Any]:
        snapshot = self._build_graph_snapshot(project_id)
        return {
            "is_healthy": snapshot.is_healthy,
            "findings": [_finding_data(item) for item in snapshot.findings],
            "topological_order": snapshot.topological_order,
        }

    def get_safe_start_order(self, project_id: ProjectId) -> dict[str, Any]:
        snapshot = self._build_graph_snapshot(project_id)
        blocking = [
            item
            for item in snapshot.findings
            if item.finding_type.value in {"cycle", "missing_dependency", "duplicate_name", "duplicate_provide"}
        ]
        if blocking or snapshot.topological_order is None:
            return {
                "ok": False,
                "order": None,
                "findings": [_finding_data(item) for item in blocking or snapshot.findings],
            }
        return {"ok": True, "order": snapshot.topological_order, "findings": []}

    def get_resource_dependencies(self, project_id: ProjectId, resource_id: str, transitive: bool = False) -> list[str]:
        record = self._get_resource(project_id, resource_id)
        return self._graph_builder(project_id).dependencies(record.resource_name, transitive=transitive)

    def get_resource_dependents(self, project_id: ProjectId, resource_id: str, transitive: bool = False) -> list[str]:
        record = self._get_resource(project_id, resource_id)
        return self._graph_builder(project_id).dependents(record.resource_name, transitive=transitive)

    def get_resource_health(self, project_id: ProjectId, resource_id: str) -> dict[str, Any]:
        record = self._get_resource(project_id, resource_id)
        with self._container.session_factory() as session:
            health = ResourceRepository(RepositoryContext(session=session, project_id=project_id)).get_latest_health(record.resource_id)
        if health is None:
            return {"resource_id": resource_id, "health_status": HealthStatus.UNKNOWN.value, "details": {}}
        return {
            "resource_id": resource_id,
            "health_status": health.health_status,
            "sampled_at": health.sampled_at,
            "details": health.details_json or {},
        }

    def _build_graph_snapshot(self, project_id: ProjectId, root: str | None = None):
        with self._container.session_factory() as session:
            repository = ResourceRepository(RepositoryContext(session=session, project_id=project_id))
            records = repository.list_resources(project_id)
            dependencies = repository.list_dependencies(project_id)
            versions = {
                record.resource_id: session.get(ResourceVersionRecord, record.current_version_id)
                for record in records
                if record.current_version_id
            }
        dep_map: dict[str, list[str]] = {record.resource_name: [] for record in records}
        provides: dict[str, list[str]] = {}
        id_to_name = {record.resource_id: record.resource_name for record in records}
        for record in records:
            version = versions.get(record.resource_id)
            provides[record.resource_name] = list((version.manifest_json or {}).get("provides", [])) if version else []
        for dep in dependencies:
            source = id_to_name.get(dep.source_resource_id)
            if source is None:
                continue
            dep_map.setdefault(source, []).append(dep.target_name)
        duplicate_findings = detect_duplicate_resource_names([record.resource_name for record in records])
        snapshot = build_dependency_graph(dep_map, provides)
        if duplicate_findings:
            snapshot = type(snapshot)(
                nodes=snapshot.nodes,
                edges=snapshot.edges,
                provides=snapshot.provides,
                findings=[*snapshot.findings, *duplicate_findings],
                topological_order=snapshot.topological_order,
                is_healthy=False,
            )
        if root is None:
            return snapshot
        builder = DependencyGraphBuilder()
        for name, deps in dep_map.items():
            builder.add_resource(name, deps, provides.get(name, []))
        subset = {root, *builder.dependencies(root, transitive=True), *builder.dependents(root, transitive=True)}
        sub_map = {name: [target for target in dep_map.get(name, []) if target in subset] for name in subset}
        sub_provides = {name: provides.get(name, []) for name in subset}
        return build_dependency_graph(sub_map, sub_provides)

    def _graph_builder(self, project_id: ProjectId) -> DependencyGraphBuilder:
        snapshot = self._build_graph_snapshot(project_id)
        builder = DependencyGraphBuilder()
        for node in snapshot.nodes:
            deps = [edge.target for edge in snapshot.edges if edge.source == node]
            builder.add_resource(node, deps, snapshot.provides.get(node, []))
        builder.findings = list(snapshot.findings)
        return builder

    def _resource_roots(self, project_id: ProjectId) -> list[str]:
        roots: list[str] = []
        with self._container.session_factory() as session:
            paths = session.execute(select(ProjectPathRecord).where(ProjectPathRecord.project_id == str(project_id))).scalars()
            for record in paths:
                if record.path_role == "resources":
                    roots.append(record.absolute_path)
                if record.path_role == "root":
                    for candidate in (
                        Path(record.absolute_path) / "resources",
                        Path(record.absolute_path) / "server-data" / "resources",
                    ):
                        if candidate.exists():
                            roots.append(str(candidate))
        return list(dict.fromkeys(roots))

    def _enabled_resources(self, project_id: ProjectId) -> dict[str, bool]:
        try:
            config_service = self._container.create_config_service()
            files = config_service.list_config_files(project_id)
            server_cfg = next((item for item in files if item["path"].endswith("server.cfg")), None)
            if server_cfg is None:
                return {}
            view = config_service.get_config_file_view(project_id, server_cfg["config_file_id"])
            return self._scanner.parse_server_cfg_enabled(view.get("content"))
        except Exception:
            return {}

    def _get_resource(self, project_id: ProjectId, resource_id: str):
        with self._container.session_factory() as session:
            record = ResourceRepository(RepositoryContext(session=session, project_id=project_id)).get_resource(project_id, StableIdentifier(resource_id))
            if record is None:
                raise ResourceApplicationError(ErrorCode.NOT_FOUND, f"Resource not found: {resource_id}")
            return record

    def _require_project(self, repository: ProjectRepository, project_id: ProjectId) -> None:
        if repository.get_project(project_id) is None:
            raise ResourceApplicationError(ErrorCode.NOT_FOUND, f"Project not found: {project_id}")


def _health_for_item(item: Any, enabled: bool, graph: Any, resource_name: str) -> dict[str, Any]:
    missing = [f for f in graph.findings if resource_name in f.nodes and f.finding_type.value == "missing_dependency"]
    cyclic = [f for f in graph.findings if resource_name in f.nodes and f.finding_type.value == "cycle"]
    status = HealthStatus.HEALTHY.value
    if not item.manifest.manifest_valid:
        status = HealthStatus.ERROR.value
    elif missing or cyclic:
        status = HealthStatus.ERROR.value
    elif not enabled:
        status = HealthStatus.WARNING.value
    return {
        "health_status": status,
        "manifest_valid": item.manifest.manifest_valid,
        "dependency_satisfied": not missing,
        "enabled_state": EnabledState.ENABLED.value if enabled else EnabledState.DISABLED.value,
        "manifest_errors": item.manifest.errors,
    }


def _manifest_json(item: Any) -> dict[str, Any]:
    return {
        "manifest_kind": item.manifest_kind,
        "fx_version": item.manifest.fx_version,
        "games": item.manifest.games,
        "version": item.manifest.version,
        "dependencies": item.manifest.dependencies,
        "provides": item.manifest.provides,
        "manifest_valid": item.manifest.manifest_valid,
        "errors": item.manifest.errors,
    }


def _resource_data(record: Any) -> dict[str, Any]:
    return {
        "resource_id": record.resource_id,
        "project_id": record.project_id,
        "resource_name": record.resource_name,
        "relative_path": record.relative_path,
        "resource_type": record.resource_type,
        "enabled_state": record.enabled_state,
        "startup_order": record.startup_order,
        "current_version_id": record.current_version_id,
        "git_repository_id": record.git_repository_id,
        "updated_at": record.updated_at,
    }


def _finding_data(item: Any) -> dict[str, Any]:
    return {
        "finding_type": item.finding_type.value,
        "severity": item.severity.value,
        "message": item.message,
        "nodes": item.nodes,
        "details": item.details,
    }


def _graph_data(snapshot: Any, root: str | None = None) -> dict[str, Any]:
    return {
        "root": root,
        "nodes": snapshot.nodes,
        "edges": [{"source": edge.source, "target": edge.target, "dependency_type": edge.dependency_type} for edge in snapshot.edges],
        "provides": snapshot.provides,
        "findings": [_finding_data(item) for item in snapshot.findings],
        "topological_order": snapshot.topological_order,
        "is_healthy": snapshot.is_healthy,
    }
