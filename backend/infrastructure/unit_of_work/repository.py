from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, TypeVar

from sqlalchemy.orm import Session

from backend.domain.shared_kernel.identifiers import ProjectId


@dataclass(frozen=True, slots=True)
class RepositoryContext:
    session: Session
    project_id: ProjectId | None = None

    def require_project_id(self) -> ProjectId:
        if self.project_id is None:
            raise ProjectScopeRequired("Repository operation requires project_id scope")
        return self.project_id


class ProjectScopeRequired(RuntimeError):
    """Raised when a project-scoped repository is requested without project_id."""


class RepositoryFactory(Protocol):
    def __call__(self, context: RepositoryContext) -> object:
        """Create a repository bound to a UoW-owned session."""


TRepository = TypeVar("TRepository")
TypedRepositoryFactory = Callable[[RepositoryContext], TRepository]
