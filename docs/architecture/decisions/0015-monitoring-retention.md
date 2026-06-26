# ADR 0015: Monitoring Retention And Downsampling (M6b)

## Status

Accepted

## Context

M6a persists raw `metric_samples` with single-writer batched flushes and streams live metrics. M6b must roll up raw samples into faithful aggregates, enforce retention horizons, and expose historical queries — without alerting (M6c) or a second writer.

## Decision

1. **Aggregate content** — each rollup bucket stores `min_value`, `max_value`, `sum_value`, `avg_value`, and `sample_count`, plus `bucket_start` and derived `bucket_end`. Peaks survive aggregation; averages alone are never stored without min/max/count.
2. **Rollup tiers** — raw → 1-minute (`60s`) → 1-hour (`3600s`) per series per project. Hour buckets compose from minute buckets (not re-scanned raw) using min-of-mins, max-of-maxes, summed counts, and sum-of-sums for weighted average.
3. **Retention horizons** — raw samples: **24 hours**; minute rollups: **7 days**; hour rollups: **90 days**. Raw samples are deleted only when a minute rollup exists for their bucket and the bucket end is past the raw horizon. Minute rollups are deleted only when an hour rollup covers their hour window.
4. **Idempotency** — upsert on `(metric_series_id, bucket_start, bucket_size_seconds)`; re-aggregation replaces prior values without double-counting.
5. **Resumability** — `metric_rollup_watermarks` per `(project_id, tier)` records the last fully processed bucket end; missed ticks catch up from the watermark (or oldest data) forward.
6. **Single-writer coordination** — rollup/retention runs in one daemon thread and every write uses `create_unit_of_work()` → shared `writer_lock` (same as M6a collection). No APScheduler, no second writer.
7. **Cadence** — default 60s in-process rollup tick; on-demand via `POST .../monitoring/rollup/run`.
8. **Privacy** — rollups remain local-only project data; no telemetry path.

## Consequences

- Historical graphs can render spike-preserving ranges from rollups.
- `sum_value` is persisted (schema extension) for mathematically correct tier composition.
- `project_id` is denormalized on `metric_rollups` for efficient scoped retention deletes.

## Deviations

- Added `sum_value` and `project_id` columns to `metric_rollups` beyond the Phase-5 schema doc (required for faithful cross-tier composition and scoped retention).
- Added `metric_rollup_watermarks` table (not in Phase-5 doc) for resumable catch-up.
