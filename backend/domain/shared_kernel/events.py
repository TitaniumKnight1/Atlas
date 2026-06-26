from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from backend.domain.shared_kernel.audit import AuditMetadata
from backend.domain.shared_kernel.identifiers import AggregateRef, ProjectId, StableIdentifier


@dataclass(frozen=True, slots=True)
class DomainEventEnvelope:
    event_id: StableIdentifier
    event_type: str
    occurred_at: datetime
    aggregate_ref: AggregateRef
    payload: dict[str, Any]
    project_id: ProjectId | None = None
    audit: AuditMetadata | None = None

    @classmethod
    def create(
        cls,
        *,
        event_type: str,
        aggregate_ref: AggregateRef,
        payload: dict[str, Any] | None = None,
        project_id: ProjectId | None = None,
        audit: AuditMetadata | None = None,
    ) -> DomainEventEnvelope:
        return cls(
            event_id=StableIdentifier.new(),
            event_type=event_type,
            occurred_at=datetime.now(UTC),
            aggregate_ref=aggregate_ref,
            payload=payload or {},
            project_id=project_id,
            audit=audit,
        )

    def __post_init__(self) -> None:
        if not self.event_type.strip():
            raise ValueError("event_type cannot be empty")
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware UTC")

    def to_record(self) -> dict[str, Any]:
        return {
            "domain_event_id": str(self.event_id),
            "project_id": str(self.project_id) if self.project_id is not None else None,
            "event_type": self.event_type,
            "aggregate_type": self.aggregate_ref.aggregate_type,
            "aggregate_id": self.aggregate_ref.aggregate_id,
            "occurred_at": self.occurred_at.isoformat(),
            "payload_json": self.payload,
        }
