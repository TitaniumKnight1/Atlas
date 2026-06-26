from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from backend.domain.shared_kernel.audit import AuditRef
from backend.domain.shared_kernel.identifiers import ProjectId, StableIdentifier
from backend.infrastructure.unit_of_work import SingleWriterSQLiteUnitOfWork


class CommandStatus(StrEnum):
    DRAFT = "draft"
    PRESENTED = "presented"
    APPROVED = "approved"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    DESTRUCTIVE = "destructive"


@dataclass(frozen=True, slots=True)
class CommandPreview:
    command_type: str
    summary: str
    preview: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.LOW


@dataclass(frozen=True, slots=True)
class DryRunResult:
    command_type: str
    valid: bool
    simulation: dict[str, Any]
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class CommandContext:
    uow: SingleWriterSQLiteUnitOfWork
    now: Callable[[], datetime] = field(default_factory=lambda: lambda: datetime.now(UTC))


class CompensatingAction(Protocol):
    action_type: str

    def describe(self) -> dict[str, Any]:
        """Return a durable, non-secret undo description."""

    def apply(self, context: CommandContext) -> dict[str, Any]:
        """Apply the compensation inside the caller-owned Unit of Work."""


@dataclass(frozen=True, slots=True)
class UndoPlan:
    command_type: str
    summary: str
    action: CompensatingAction
    payload: dict[str, Any]
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class CommandExecutionResult:
    command_type: str
    command_plan_id: StableIdentifier
    command_execution_id: StableIdentifier
    audit_ref: AuditRef
    result: dict[str, Any]
    undo_plan: UndoPlan | None = None
    project_id: ProjectId | None = None
