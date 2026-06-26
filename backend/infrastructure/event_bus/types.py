from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from backend.domain.shared_kernel.events import DomainEventEnvelope


class EventHandler(Protocol):
    def __call__(self, event: DomainEventEnvelope) -> None:
        """Handle a domain event synchronously."""


@dataclass(frozen=True, slots=True)
class HandlerFailure:
    event: DomainEventEnvelope
    handler_name: str
    error: Exception


@dataclass(frozen=True, slots=True)
class DispatchReport:
    published_count: int
    handler_count: int
    failures: tuple[HandlerFailure, ...]


class EventDispatchError(RuntimeError):
    def __init__(self, report: DispatchReport) -> None:
        self.report = report
        super().__init__(
            f"{len(report.failures)} event handler(s) failed while publishing "
            f"{report.published_count} event(s)"
        )
