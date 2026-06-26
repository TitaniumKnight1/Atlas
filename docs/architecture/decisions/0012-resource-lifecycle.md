# ADR-0012: Single-Resource Lifecycle and Composite Compensation

## Status

Accepted (M5b)

## Context

Resource install, update, enable, disable, and delete each touch multiple adapters (filesystem, git, server.cfg). Undo must honestly reverse every effect without leaving partial state.

## Decision

1. **Composite compensation** — `CompositeCompensation` holds an ordered tuple of `CompensatingAction` steps. `apply()` runs sub-compensations in **reverse order** (LIFO), so a forward sequence of file placement then config edit undoes config first, then files.
2. **Per-operation M1 commands** — Each mutation exposes preview, dry-run, execute, and undo via `ResourceLifecycleService`, recording audit rows and `resource_state_changes` where applicable.
3. **Reuse existing adapters** — File writes use M3a `LocalSetupFilesystem`; server.cfg edits snapshot via M4a `RestoreConfigFileCompensation`; git sourcing uses M4b `GitPythonProvider` with SSE `OperationProgress` (no parallel mechanisms).
4. **Graph safety (warn vs block)** — Install/enable **warn** when declared dependencies are missing from inventory. Disable/delete **warn** in preview and **block** execute when **enabled** dependents (present in `server.cfg` ensure lines) rely on the target resource. Graph queries come from M5a (`get_resource_dependents`, `get_resource_dependencies`); M5b does not rebuild graph logic.
5. **Ensure-line ordering** — When adding an `ensure` line, insert immediately after the last existing ensure line of declared dependencies (if any are present in `server.cfg`). If no dependency line exists, append at end. Unrelated ensure lines are not reordered.

## Consequences

- M5c multi-resource rollback can compose the same `CompositeCompensation` primitive across ordered steps.
- Delete undo restores files from an on-disk snapshot when feasible; preview states when reversal is not honest.
- Resource mutation domain events (`ResourceInstalled`, etc.) carry IDs and names only — local event bus, never telemetry.

## Out of scope

Dependency-ordered multi-resource rollback (M5c).
