from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Generic, TypeVar

from backend.domain.shared_kernel.audit import AuditRef


TData = TypeVar("TData")


class ErrorCode(StrEnum):
    NOT_FOUND = "NotFound"
    VALIDATION_FAILED = "ValidationFailed"
    CONFLICT = "Conflict"
    PERMISSION_DENIED = "PermissionDenied"
    PROJECT_SCOPE_VIOLATION = "ProjectScopeViolation"
    PRECONDITION_FAILED = "PreconditionFailed"
    EXTERNAL_ADAPTER_FAILED = "ExternalAdapterFailed"
    TELEMETRY_REJECTED = "TelemetryRejected"
    OPERATION_CANCELLED = "OperationCancelled"


@dataclass(frozen=True, slots=True)
class ErrorPayload:
    code: ErrorCode
    message: str

    def __post_init__(self) -> None:
        if not self.message.strip():
            raise ValueError("message cannot be empty")


@dataclass(frozen=True, slots=True)
class ResultEnvelope(Generic[TData]):
    ok: bool
    data: TData | None = None
    error: ErrorPayload | None = None
    warnings: list[str] = field(default_factory=list)
    audit_ref: AuditRef | None = None

    @classmethod
    def success(
        cls,
        data: TData,
        *,
        warnings: list[str] | None = None,
        audit_ref: AuditRef | None = None,
    ) -> ResultEnvelope[TData]:
        return cls(ok=True, data=data, warnings=warnings or [], audit_ref=audit_ref)

    @classmethod
    def failure(
        cls,
        error: ErrorPayload,
        *,
        warnings: list[str] | None = None,
        audit_ref: AuditRef | None = None,
    ) -> ResultEnvelope[TData]:
        return cls(ok=False, error=error, warnings=warnings or [], audit_ref=audit_ref)

    def __post_init__(self) -> None:
        if self.ok and self.error is not None:
            raise ValueError("successful ResultEnvelope cannot include error")
        if not self.ok and self.error is None:
            raise ValueError("failed ResultEnvelope must include error")
