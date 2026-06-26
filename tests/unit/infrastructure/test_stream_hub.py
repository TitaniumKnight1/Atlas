from __future__ import annotations

import threading
import time
from unittest.mock import patch

from backend.infrastructure.streams import ProjectStreamHub, StreamTopic


def test_stream_events_are_monotonic_per_project() -> None:
    hub = ProjectStreamHub()
    first = hub.publish(topic=StreamTopic.SERVER_OUTPUT, event_type="ServerOutputLine", project_id="project-a", payload={"line": "one"})
    second = hub.publish(topic=StreamTopic.SERVER_OUTPUT, event_type="ServerOutputLine", project_id="project-a", payload={"line": "two"})
    assert second.sequence > first.sequence


def test_project_isolation_at_stream_boundary() -> None:
    hub = ProjectStreamHub()
    subscriber = hub.subscribe("project-a", {StreamTopic.SERVER_OUTPUT})
    hub.publish(topic=StreamTopic.SERVER_OUTPUT, event_type="ServerOutputLine", project_id="project-b", payload={"line": "foreign"})
    hub.publish(topic=StreamTopic.SERVER_OUTPUT, event_type="ServerOutputLine", project_id="project-a", payload={"line": "local"})
    event = subscriber.wait_next(timeout=1.0)
    assert event is not None
    assert event.payload["line"] == "local"
    assert subscriber.wait_next(timeout=0.1) is None
    hub.unsubscribe(subscriber)


def test_guaranteed_topics_do_not_silently_drop_on_slow_consumer() -> None:
    hub = ProjectStreamHub()
    subscriber = hub.subscribe("project-a", {StreamTopic.SERVER_OUTPUT})
    with patch("backend.infrastructure.streams.hub.GUARANTEED_QUEUE_LIMIT", 2):
        hub.publish(topic=StreamTopic.SERVER_OUTPUT, event_type="ServerOutputLine", project_id="project-a", payload={"line": "1"})
        hub.publish(topic=StreamTopic.SERVER_OUTPUT, event_type="ServerOutputLine", project_id="project-a", payload={"line": "2"})
        hub.publish(topic=StreamTopic.SERVER_OUTPUT, event_type="ServerOutputLine", project_id="project-a", payload={"line": "3"})
    assert subscriber.slow_consumer is True
    assert subscriber.closed is True
    hub.unsubscribe(subscriber)


def test_metrics_topic_coalesces_under_backpressure() -> None:
    hub = ProjectStreamHub()
    subscriber = hub.subscribe("project-a", {StreamTopic.METRICS})
    with patch("backend.infrastructure.streams.hub.COALESCE_BUFFER_LIMIT", 2):
        for index in range(4):
            hub.publish(topic=StreamTopic.METRICS, event_type="MetricSample", project_id="project-a", payload={"value": index})
    first = subscriber.wait_next(timeout=1.0)
    second = subscriber.wait_next(timeout=1.0)
    assert first is not None and second is not None
    assert first.payload["value"] == 2
    assert second.payload["value"] == 3
    hub.unsubscribe(subscriber)


def test_unsubscribe_cleans_up_subscriber() -> None:
    hub = ProjectStreamHub()
    subscriber = hub.subscribe("project-a", {StreamTopic.OP_PROGRESS})
    assert hub.subscriber_count == 1
    hub.unsubscribe(subscriber)
    assert hub.subscriber_count == 0


def test_last_event_id_replays_buffered_events() -> None:
    hub = ProjectStreamHub()
    first = hub.publish(topic=StreamTopic.OP_PROGRESS, event_type="OperationProgress", project_id="project-a", payload={"step": 1})
    hub.publish(topic=StreamTopic.OP_PROGRESS, event_type="OperationProgress", project_id="project-a", payload={"step": 2})
    subscriber = hub.subscribe("project-a", {StreamTopic.OP_PROGRESS}, last_event_id=first.sequence)
    replayed = subscriber.wait_next(timeout=1.0)
    assert replayed is not None
    assert replayed.payload["step"] == 2
    hub.unsubscribe(subscriber)
