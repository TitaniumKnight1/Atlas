# ADR 0016: Monitoring Alerting (M6c)

## Status

Accepted

## Context

M6a collects live metric samples; M6b rolls them into faithful aggregates. M6c completes M6 by detecting threshold breaches and emitting alert events for future automation (M8). Alert events are loss-sensitive and must not be coalesced or silently dropped.

## Decision

1. **Events, not actions** — M6c emits `AlertFired` and `AlertResolved` only. It never restarts servers, sends notifications, runs scripts, or calls the automation engine (M8).
2. **Stateful fire-once** — runtime states `ok`, `pending`, `firing`. One `AlertFired` per breach cycle; no re-emit while `firing`; one `AlertResolved` on recovery.
3. **Immediate vs sustained** — `duration_seconds=0` fires on first breach. `duration_seconds>0` requires breach persistence across the window (evaluated against M6a raw samples in the duration window via `recent_numeric_samples` / `latest_sample_value`). Single spikes enter `pending` but do not fire.
4. **Metric read path** — evaluation reads `MonitoringRepository.latest_sample_value` and `recent_numeric_samples` (M6a-persisted data). No re-collection or re-aggregation.
5. **Rule CRUD** — plain project-scoped REST CRUD without M1 preview/dry-run/undo ceremony (config-like rules).
6. **Single-writer evaluation** — 30s in-process daemon; all state transitions via `create_unit_of_work()` + shared `writer_lock`. No APScheduler, no second writer.
7. **SSE topic** — new `alerts` topic with **Guaranteed** delivery policy (ADR-0008 extension). Alert events are not published on the coalescing `metrics` topic.
8. **Privacy** — alert rules and events are local-only project data; never telemetry.

## Consequences

- M8 automation can subscribe to `alerts` topic or query `monitoring_alert_events` to execute actions.
- `runtime_state` and `pending_since` columns added to `monitoring_alerts` for durable state across restarts.

## Deviations

- Added `alerts` SSE topic (not in original ADR-0008 table) because alert events are loss-sensitive unlike metrics.
- Added `runtime_state` / `pending_since` on `monitoring_alerts` beyond Phase-5 schema doc.
