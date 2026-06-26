from __future__ import annotations

import json
import threading
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from backend.infrastructure.streams.types import (
    COALESCE_BUFFER_LIMIT,
    DeliveryPolicy,
    GUARANTEED_QUEUE_LIMIT,
    REPLAY_BUFFER_LIMIT,
    TOPIC_DELIVERY_POLICIES,
    StreamEvent,
    StreamTopic,
)


@dataclass(slots=True)
class StreamSubscriber:
    subscriber_id: str
    project_id: str
    topics: frozenset[str]
    queue: deque[StreamEvent] = field(default_factory=deque)
    closed: bool = False
    slow_consumer: bool = False
    _condition: threading.Condition = field(default_factory=threading.Condition)

    def close(self) -> None:
        with self._condition:
            self.closed = True
            self._condition.notify_all()

    def push(self, event: StreamEvent) -> None:
        policy = TOPIC_DELIVERY_POLICIES.get(event.topic, DeliveryPolicy.GUARANTEED)
        with self._condition:
            if self.closed:
                return
            if policy is DeliveryPolicy.COALESCE:
                same_topic = [item for item in self.queue if item.topic == event.topic]
                other = [item for item in self.queue if item.topic != event.topic]
                same_topic.append(event)
                if len(same_topic) > COALESCE_BUFFER_LIMIT:
                    same_topic = same_topic[-COALESCE_BUFFER_LIMIT:]
                self.queue = deque(other + same_topic)
            else:
                if len(self.queue) >= GUARANTEED_QUEUE_LIMIT:
                    self.slow_consumer = True
                    self.closed = True
                    self._condition.notify_all()
                    return
                self.queue.append(event)
            self._condition.notify_all()

    def wait_next(self, timeout: float) -> StreamEvent | None:
        with self._condition:
            while not self.queue and not self.closed:
                notified = self._condition.wait(timeout)
                if not notified and not self.queue:
                    return None
            if self.queue:
                return self.queue.popleft()
            return None


class ProjectStreamHub:
    """Multiplexed in-process stream hub for loopback SSE subscribers."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sequence = 0
        self._subscribers: dict[str, list[StreamSubscriber]] = {}
        self._replay: dict[str, deque[StreamEvent]] = {}

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return sum(len(items) for items in self._subscribers.values())

    def publish(
        self,
        *,
        topic: str,
        event_type: str,
        project_id: str,
        payload: dict[str, Any],
        occurred_at: str | None = None,
    ) -> StreamEvent:
        with self._lock:
            self._sequence += 1
            event = StreamEvent(
                sequence=self._sequence,
                topic=topic,
                event_type=event_type,
                project_id=project_id,
                payload=payload,
                occurred_at=occurred_at or datetime.now(UTC).isoformat(),
            )
            replay = self._replay.setdefault(project_id, deque(maxlen=REPLAY_BUFFER_LIMIT))
            replay.append(event)
            subscribers = list(self._subscribers.get(project_id, ()))
        for subscriber in subscribers:
            if event.topic in subscriber.topics or event.topic == StreamTopic.SYSTEM:
                subscriber.push(event)
        return event

    def heartbeat(self, project_id: str) -> StreamEvent:
        return self.publish(
            topic=StreamTopic.SYSTEM,
            event_type="heartbeat",
            project_id=project_id,
            payload={"alive": True},
        )

    def subscribe(self, project_id: str, topics: set[str], last_event_id: int | None = None) -> StreamSubscriber:
        subscriber = StreamSubscriber(subscriber_id=str(uuid.uuid4()), project_id=project_id, topics=frozenset(topics))
        with self._lock:
            replay = self._replay.get(project_id, deque())
            if last_event_id is not None:
                for event in replay:
                    if event.sequence <= last_event_id:
                        continue
                    if event.topic in subscriber.topics or event.topic == StreamTopic.SYSTEM:
                        subscriber.push(event)
            self._subscribers.setdefault(project_id, []).append(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: StreamSubscriber) -> None:
        subscriber.close()
        with self._lock:
            bucket = self._subscribers.get(subscriber.project_id, [])
            self._subscribers[subscriber.project_id] = [item for item in bucket if item.subscriber_id != subscriber.subscriber_id]
            if not self._subscribers[subscriber.project_id]:
                self._subscribers.pop(subscriber.project_id, None)


def format_sse(event: StreamEvent, *, heartbeat: bool = False) -> str:
    if heartbeat or event.event_type == "heartbeat":
        payload = json.dumps(event.to_sse_data())
        return f"event: heartbeat\ndata: {payload}\n\n"
    data = json.dumps(event.to_sse_data())
    return f"id: {event.sequence}\nevent: {event.topic}\ndata: {data}\n\n"
