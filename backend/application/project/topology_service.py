from __future__ import annotations

from pathlib import Path

from backend.adapters.persistence import ProjectRepository
from backend.application.project.service import ProjectApplicationError
from backend.domain.project.topology import (
    ProjectRepoTopology,
    discover_project_repo_topology,
    resolve_path_owner_detail,
)
from backend.domain.shared_kernel import ErrorCode, ProjectId
from backend.infrastructure.unit_of_work import RepositoryContext


class ProjectTopologyService:
    def __init__(self, *, container) -> None:
        self._container = container

    def get_topology(self, project_id: ProjectId) -> dict[str, object]:
        root = self._project_root(project_id)
        topology = discover_project_repo_topology(root)
        return topology.to_dict()

    def resolve_path_owner(self, project_id: ProjectId, file_path: Path) -> dict[str, object]:
        root = self._project_root(project_id)
        topology = discover_project_repo_topology(root)
        return resolve_path_owner_detail(root, file_path, topology)

    def discover_topology(self, root_path: Path) -> ProjectRepoTopology:
        return discover_project_repo_topology(root_path)

    def _project_root(self, project_id: ProjectId) -> Path:
        with self._container.session_factory() as session:
            repository = ProjectRepository(RepositoryContext(session=session, project_id=project_id))
            project = repository.get_project()
            if project is None:
                raise ProjectApplicationError(ErrorCode.NOT_FOUND, f"Project not found: {project_id}")
            root_path = repository.get_root_path(project_id)
            if not root_path:
                raise ProjectApplicationError(ErrorCode.PRECONDITION_FAILED, f"Project has no root path: {project_id}")
            return Path(root_path)
