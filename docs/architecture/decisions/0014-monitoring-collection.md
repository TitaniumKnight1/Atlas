# ADR 0014: Monitoring Collection (M6a)

## Status

Accepted

## Context

ADR-0007 deferred the reusable monitoring collector seam to M6 and limited M3b to minimal process status. ADR-0008 defined the SSE `metrics` topic with a coalesce/drop-oldest bounded-buffer policy. M6a must collect obtainable metrics, stream them live, and persist raw samples for M6b rollups — without retention, alerting, or command/undo ceremony.

## Decision

1. **Collector seam** — `MetricCollectorPort` + `MetricCollectorRegistry` in `backend/adapters/monitoring/` register pluggable collectors. M6b/M6c and future plugin collectors extend this seam.
2. **M3b reuse** — `SupervisedProcessMetricCollector` reads `ProcessPort.status()` from M3b; no second process-status mechanism.
3. **M5a reuse** — `ResourceHealthMetricCollector` calls `ResourceApplicationService` health queries; inventory/graph logic is not rebuilt.
4. **Implemented sources (M6a)** — host memory, project disk usage, supervised-process state/pid/memory, resource-health counts.
5. **Deferred sources (stubbed, not faked)** — host CPU (`psutil` not added), server FPS, player count, network throughput, database latency — emitted with `quality=missing` and `deferred_reason`.
6. **Live streaming** — every collected sample publishes `MetricSample` on the existing `metrics` topic via `StreamEventPublisher` → `InProcessEventBus` → `StreamEventBridge` → `ProjectStreamHub` → SSE. Project-scoped; coalesce policy per ADR-0008.
7. **Cadence** — default 2s in-process timer per active collection session (no APScheduler).
8. **Persistence batching** — samples buffer in memory; flush every 10s or 30 samples in a single UoW write. Series/source metadata resolves in one UoW per tick (cached per session). Streaming bypasses per-sample DB commits to respect the M0b single-writer model.
9. **Privacy** — server/system metrics are FiveM project data (local-only); they never enter the telemetry pipeline.
10. **Out of scope** — rollups/retention (M6b), alerts (M6c), dashboard UI, preview/dry-run/undo for read-only collection.

## Consequences

- M6b can roll up `metric_samples` without changing the collector seam.
- Rich host CPU on Windows likely needs `psutil` or platform counters — paused pending explicit approval.
- High-frequency live metrics are intentionally loss-tolerant on the SSE transport.
