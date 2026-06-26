from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from threading import RLock

from backend.domain.shared_kernel.events import DomainEventEnvelope
from backend.infrastructure.event_bus.types import DispatchReport, EventDispatchError, EventHandler, HandlerFailure


class InProcessEventBus:
    """Synchronous in-process event bus.

    The bus itself dispatches immediately. The Unit of Work is responsible for
    deferring publication until after a successful commit.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._lock = RLock()

    def register(self, event_type: str, handler: EventHandler) -> None:
        if not event_type.strip():
            raise ValueError("event_type cannot be empty")
        with self._lock:
            self._handlers[event_type].append(handler)

    def publish(self, events: Iterable[DomainEventEnvelope]) -> DispatchReport:
        event_list = list(events)
        failures: list[HandlerFailure] = []
        handler_count = 0

        for event in event_list:
            with self._lock:
                handlers = tuple(self._handlers.get(event.event_type, ()))

            for handler in handlers:
                handler_count += 1
                try:
                    handler(event)
                except Exception as error:  # noqa: BLE001 - isolate handlers and report all failures.
                    failures.append(
                        HandlerFailure(
                            event=event,
                            handler_name=getattr(handler, "__name__", type(handler).__name__),
                            error=error,
                        )
                    )

        report = DispatchReport(
            published_count=len(event_list),
            handler_count=handler_count,
            failures=tuple(failures),
        )
        if failures:
            raise EventDispatchError(report)
        return report
