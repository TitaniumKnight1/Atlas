from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class StreamTopic(StrEnum):
    SERVER_OUTPUT = "server-output"
    PROCESS_LIFECYCLE = "process-lifecycle"
    OP_PROGRESS = "op-progress"
    METRICS = "metrics"
    ALERTS = "alerts"
    SYSTEM = "system"


class DeliveryPolicy(StrEnum):
    GUARANTEED = "guaranteed"
    COALESCE = "coalesce"


TOPIC_DELIVERY_POLICIES: dict[str, DeliveryPolicy] = {
    StreamTopic.SERVER_OUTPUT: DeliveryPolicy.GUARANTEED,
    StreamTopic.PROCESS_LIFECYCLE: DeliveryPolicy.GUARANTEED,
    StreamTopic.OP_PROGRESS: DeliveryPolicy.GUARANTEED,
    StreamTopic.METRICS: DeliveryPolicy.COALESCE,
    StreamTopic.ALERTS: DeliveryPolicy.GUARANTEED,
    StreamTopic.SYSTEM: DeliveryPolicy.GUARANTEED,
}

GUARANTEED_QUEUE_LIMIT = 1000
COALESCE_BUFFER_LIMIT = 100
REPLAY_BUFFER_LIMIT = 500
HEARTBEAT_INTERVAL_SECONDS = 15.0


@dataclass(frozen=True, slots=True)
class StreamEvent:
    sequence: int
    topic: str
    event_type: str
    project_id: str
    payload: dict[str, Any]
    occurred_at: str

    def to_sse_data(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "topic": self.topic,
            "event_type": self.event_type,
            "project_id": self.project_id,
            "payload": self.payload,
            "occurred_at": self.occurred_at,
        }


STREAM_EVENT_TYPES: dict[str, str] = {
    "ServerStarted": StreamTopic.PROCESS_LIFECYCLE,
    "ServerStopped": StreamTopic.PROCESS_LIFECYCLE,
    "ServerCrashed": StreamTopic.PROCESS_LIFECYCLE,
    "ArtifactInstalled": StreamTopic.OP_PROGRESS,
    "SetupRunCompleted": StreamTopic.OP_PROGRESS,
    "ServerOutputLine": StreamTopic.SERVER_OUTPUT,
    "ServerErrorLine": StreamTopic.SERVER_OUTPUT,
    "OperationProgress": StreamTopic.OP_PROGRESS,
    "GitOperationStarted": StreamTopic.OP_PROGRESS,
    "GitOperationCompleted": StreamTopic.OP_PROGRESS,
    "MetricSample": StreamTopic.METRICS,
    "AlertFired": StreamTopic.ALERTS,
    "AlertResolved": StreamTopic.ALERTS,
}
