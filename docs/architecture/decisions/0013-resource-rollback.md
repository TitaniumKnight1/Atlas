# ADR-0013: Dependency-Ordered Multi-Resource Rollback

## Status

Accepted (M5c)

## Context

M5b provides per-resource composite compensation undo. Operators need to reverse multiple resource operations in dependency-safe order. True atomicity across filesystem and server.cfg for multiple resources is not achievable.

## Decision

1. **Rollback order** — Use M5a `get_safe_start_order` (dependencies before dependents). Rollback order is the **reverse** of that order (dependents first). When the full graph is unhealthy, compute order on the batch subgraph via Kahn's algorithm; refuse with a clear finding if the batch contains an internal cycle.
2. **Orchestration** — `ResourceRollbackService` resolves M5b undo payloads from `command_executions` / `resource_state_changes`, rehydrates stored compensations, and applies each step in order. Does not reimplement file/config/git mutations.
3. **Mid-rollback failure (stop-and-hold)** — If a resource reversal fails, stop immediately. Do not continue to later resources and do not undo completed reversals. Record succeeded / failed / not-attempted outcomes in `resource_rollback_runs` and `resource_rollback_outcomes`.
4. **Batch reporting, not batch atomicity** — Each resource reversal remains atomic via M5b `CompositeCompensation`. The batch command reports precise partial state; it does not claim all-or-nothing multi-resource undo.
5. **Safety** — Rolling back a resource with **enabled** dependents outside the batch warns in preview and blocks execute (consistent with M5b disable/delete policy).
6. **No undo-of-rollback** — The batch command has preview and execute only; reversing a halted rollback is explicitly out of scope.

## Consequences

- Partial rollback state is always queryable via rollback run records and structured execution results.
- SSE `OperationProgress` publishes per-resource rollback steps.
- Mutation audit undo payloads use restorable compensation serialization (`compensation_to_storage`) for cross-session rehydration.

## Out of scope

Automatic/triggered rollback (M8 automation), backup-driven restore.
