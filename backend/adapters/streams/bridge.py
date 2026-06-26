from __future__ import annotations

from typing import Any

from backend.domain.shared_kernel.events import DomainEventEnvelope
from backend.domain.shared_kernel.identifiers import AggregateRef, ProjectId
from backend.infrastructure.event_bus import InProcessEventBus
from backend.infrastructure.streams import ProjectStreamHub, STREAM_EVENT_TYPES


class StreamEventPublisher:
    """Publish operational stream notifications through the in-process event bus."""

    def __init__(self, event_bus: InProcessEventBus) -> None:
        self._event_bus = event_bus

    def publish(
        self,
        *,
        event_type: str,
        project_id: ProjectId,
        payload: dict[str, Any],
    ) -> None:
        self._event_bus.publish(
            [
                DomainEventEnvelope.create(
                    event_type=event_type,
                    aggregate_ref=AggregateRef("StreamNotification", event_type),
                    project_id=project_id,
                    payload=payload,
                )
            ]
        )

    def publish_server_output_line(
        self,
        *,
        project_id: ProjectId,
        process_run_id: str,
        stream: str,
        line: str,
    ) -> None:
        event_type = "ServerOutputLine" if stream == "stdout" else "ServerErrorLine"
        self.publish(
            event_type=event_type,
            project_id=project_id,
            payload={"process_run_id": process_run_id, "stream": stream, "line": line},
        )

    def publish_operation_progress(
        self,
        *,
        project_id: ProjectId,
        operation_id: str,
        message: str,
        bytes_received: int | None = None,
        total_bytes: int | None = None,
        step_key: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {"operation_id": operation_id, "message": message}
        if bytes_received is not None:
            payload["bytes_received"] = bytes_received
        if total_bytes is not None:
            payload["total_bytes"] = total_bytes
        if step_key is not None:
            payload["step_key"] = step_key
        self.publish(event_type="OperationProgress", project_id=project_id, payload=payload)

    def publish_metric_sample(self, *, project_id: ProjectId, sample: dict[str, Any]) -> None:
        self.publish(event_type="MetricSample", project_id=project_id, payload=sample)


class StreamEventBridge:
    """Maps committed domain facts and stream notifications onto the SSE hub."""

    def __init__(self, hub: ProjectStreamHub) -> None:
        self._hub = hub

    def register(self, event_bus: InProcessEventBus) -> None:
        for event_type in STREAM_EVENT_TYPES:
            event_bus.register(event_type, self._handle_event)

    def _handle_event(self, event: DomainEventEnvelope) -> None:
        if event.project_id is None:
            return
        topic = STREAM_EVENT_TYPES.get(event.event_type)
        if topic is None:
            return
        self._hub.publish(
            topic=topic,
            event_type=event.event_type,
            project_id=str(event.project_id),
            payload=event.payload,
            occurred_at=event.occurred_at.isoformat(),
        )
