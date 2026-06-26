from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from backend.domain.shared_kernel.identifiers import ProjectId


class ActorType(StrEnum):
    USER = "user"
    AUTOMATION = "automation"
    PLUGIN = "plugin"
    SYSTEM = "system"


@dataclass(frozen=True, slots=True)
class AuditRef:
    ref_type: str
    ref_id: str

    def __post_init__(self) -> None:
        if not self.ref_type.strip():
            raise ValueError("ref_type cannot be empty")
        if not self.ref_id.strip():
            raise ValueError("ref_id cannot be empty")


@dataclass(frozen=True, slots=True)
class AuditMetadata:
    actor_type: ActorType
    summary: str
    project_id: ProjectId | None = None
    actor_id: str | None = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.summary.strip():
            raise ValueError("summary cannot be empty")
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware UTC")
