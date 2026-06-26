# ADR-0008: Multiplexed SSE Streaming Transport

## Status

Accepted

## Context

Atlas deferred live streaming across M3a setup progress, M3b server output buffers, and the cross-cutting data-flow note. M6 monitoring will add high-frequency metric samples. Browsers limit concurrent HTTP/1.1 connections per origin, so opening one connection per topic would exhaust the budget once monitoring, logs, and progress streams coexist.

Server stdout/stderr, setup progress, and future metrics are FiveM project data. They must remain on the local loopback transport and never enter the M2 telemetry path.

## Decision

Atlas standardizes on one multiplexed Server-Sent Events (SSE) channel per project subscriber:

- Endpoint: `GET /api/v1/projects/{project_id}/stream?topics=...`
- Each SSE message is typed JSON with `sequence`, `topic`, `event_type`, `project_id`, `payload`, and `occurred_at`.
- Topics are filtered inside the single connection; consumers do not open per-topic HTTP connections.
- `Last-Event-ID` replays recent buffered events for resume where feasible.

Events reach the stream through the M0b in-process event bus:

- Committed domain facts are published post-commit by the Unit of Work and bridged into the stream hub.
- Operational notifications (`ServerOutputLine`, `OperationProgress`) are published through the same bus from adapters/application callbacks and bridged into the hub.
- The SSE router is a transport adapter; it does not reach into domain internals.

Per-topic delivery policy:

| Topic | Policy | Behavior |
| --- | --- | --- |
| `server-output` | Guaranteed | No silent drops; slow consumers are closed when the bounded queue fills |
| `process-lifecycle` | Guaranteed | Same as server output |
| `op-progress` | Guaranteed | Same as server output |
| `metrics` | Coalesce | Bounded buffer keeps the newest samples and drops oldest under pressure |
| `system` | Guaranteed | Heartbeats and transport notices |

Heartbeats emit every 15 seconds. Subscriber teardown unregisters the consumer and closes the async generator when the client disconnects.

## Rejected Alternative: WebSocket

WebSocket would add bidirectional transport Atlas does not need for read-only project telemetry and logs, increase frontend/backend lifecycle complexity inside Tauri, and still require custom multiplexing and scoping rules. SSE matches the one-way event fan-out model, works with standard HTTP loopback, supports `Last-Event-ID`, and keeps the transport choice aligned with FastAPI `StreamingResponse`.

## Alignment With ADR-0007

ADR-0007 left the reusable monitoring collector seam for M6 to define. This ADR defines only the transport/topic layer. M6 metric collectors should publish `MetricSample` events on the `metrics` topic through the same bus and stream hub without introducing a second monitoring transport.

## Consequences

- M4 git/setup progress and M6 dashboards inherit one stream client primitive.
- Loss-sensitive project data stays local-only and outside telemetry.
- Slow metric consumers can coalesce without blocking log delivery because topics are isolated at delivery policy boundaries within one connection.
