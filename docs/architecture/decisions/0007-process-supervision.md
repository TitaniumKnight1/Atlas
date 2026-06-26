# ADR-0007: Process Supervision Lifecycle Commands

## Status

Accepted

## Context

M3b starts, observes, and stops an FXServer process prepared by M3a. This process is user-owned, may crash independently, and may spawn child processes.

## Decision

Start, stop, and restart are audited lifecycle operations in the M1 command model, not filesystem mutations. A start command may expose a lifecycle inverse whose undo is stop, but no snapshot-style compensation is created. Stop records the operational fact that Atlas attempted graceful termination followed by full process-tree cleanup. Restart composes stop plus start.

The process adapter follows the M0a sidecar termination discipline: on Windows it assigns the server root process to a Job Object configured with `KILL_ON_JOB_CLOSE`, then uses forced full-tree cleanup (`taskkill /T /F`) when stopping. This prevents orphaned FXServer children when the root process exits or hangs. Non-Windows test support uses a process group with terminate/kill fallback.

Unexpected FXServer exit is local-only. M3b records a process-run row and emits `ServerCrashed`; it does not call telemetry or incident capture.

Process run history uses a new `setup_process_runs` table. Existing `setup_runs` rows describe setup wizard executions, not live server processes, so reusing them would blur setup history with runtime state.

## Monitoring Seam

M3b exposes only minimal process status and bounded stdout/stderr tails through the setup API. It does not introduce CPU, memory, FPS, player, alert, or graph collectors. M6 should define the reusable monitoring collector seam once those metric sources are designed, and can consume M3b's process status as one input. This avoids building a second monitoring mechanism before the dashboard requirements exist.

## Streaming

Live streaming is deferred. M3b returns queryable status and log buffers only; any streaming transport should follow the cross-cutting conventions owned by the M6 streaming concern rather than inventing a one-off process stream.
