from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from backend.api.dependencies import get_container
from backend.infrastructure.di import ApplicationContainer
from backend.infrastructure.streams import HEARTBEAT_INTERVAL_SECONDS, ProjectStreamHub, StreamTopic, format_sse


router = APIRouter(prefix="/api/v1", tags=["streams"])

DEFAULT_TOPICS = (
    StreamTopic.SERVER_OUTPUT,
    StreamTopic.PROCESS_LIFECYCLE,
    StreamTopic.OP_PROGRESS,
)


@router.get("/projects/{project_id}/stream")
async def project_event_stream(
    project_id: str,
    request: Request,
    topics: str | None = None,
    container: ApplicationContainer = Depends(get_container),
) -> StreamingResponse:
    selected_topics = _parse_topics(topics)
    last_event_id = _parse_last_event_id(request.headers.get("Last-Event-ID"))
    hub = container.stream_hub

    async def event_generator():
        subscriber = hub.subscribe(project_id, selected_topics, last_event_id)
        try:
            while True:
                if await request.is_disconnected():
                    break
                event = await asyncio.to_thread(subscriber.wait_next, HEARTBEAT_INTERVAL_SECONDS)
                if subscriber.slow_consumer:
                    yield _slow_consumer_event(project_id)
                    break
                if event is None:
                    heartbeat = await asyncio.to_thread(hub.heartbeat, project_id)
                    yield format_sse(heartbeat, heartbeat=True)
                    continue
                yield format_sse(event)
        finally:
            hub.unsubscribe(subscriber)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _parse_topics(raw: str | None) -> set[str]:
    if not raw:
        return set(DEFAULT_TOPICS)
    selected = {item.strip() for item in raw.split(",") if item.strip()}
    allowed = {item.value for item in StreamTopic if item != StreamTopic.SYSTEM}
    invalid = selected - allowed
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unknown stream topics: {sorted(invalid)}")
    return selected


def _parse_last_event_id(raw: str | None) -> int | None:
    if raw is None or not raw.strip():
        return None
    try:
        return int(raw)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Last-Event-ID must be an integer sequence") from error


def _slow_consumer_event(project_id: str) -> str:
    payload = json.dumps(
        {
            "topic": StreamTopic.SYSTEM,
            "event_type": "slow_consumer",
            "project_id": project_id,
            "payload": {"message": "Subscriber queue exceeded guaranteed delivery limit"},
        }
    )
    return f"event: slow_consumer\ndata: {payload}\n\n"
