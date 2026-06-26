from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class StableIdentifier:
    """Small typed wrapper for stable string identifiers."""

    value: str

    @classmethod
    def new(cls) -> StableIdentifier:
        return cls(str(uuid4()))

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise ValueError(f"{type(self).__name__} cannot be empty")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ProjectId(StableIdentifier):
    """Identifier for app-global rows scoped to a project."""


@dataclass(frozen=True, slots=True)
class EnvironmentId(StableIdentifier):
    """Identifier for a project environment profile."""


@dataclass(frozen=True, slots=True)
class AggregateRef:
    aggregate_type: str
    aggregate_id: str

    def __post_init__(self) -> None:
        if not self.aggregate_type.strip():
            raise ValueError("aggregate_type cannot be empty")
        if not self.aggregate_id.strip():
            raise ValueError("aggregate_id cannot be empty")


@dataclass(frozen=True, slots=True)
class PathReference:
    """A normalized local path reference without filesystem side effects."""

    value: str

    @classmethod
    def from_path(cls, path: Path) -> PathReference:
        return cls(str(path.expanduser().resolve()))

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise ValueError("PathReference cannot be empty")
