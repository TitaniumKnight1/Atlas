# 0026: Delete-Rollback Placeholder Semantics

## Status
Accepted

## Context
Atlas implements a strict Single-Writer model using an in-process `RLock` and SQLAlchemy Unit of Work (UoW) pattern. Part of the platform's command contract requires every command to be previewable, dry-runnable, and undoable via a CompensatingAction.

For resource management, when a resource is deleted, its UoW commit deletes the corresponding record in the database. However, this deletion can conflict with the undo contract if that deletion is later rolled back. If a rollback tries to record state changes (`from_state: deleted`, `to_state: rolled_back`) pointing to the original `resource_id`, the database will throw a foreign-key IntegrityError because the original resource row was removed.

## Decision
We will satisfy the foreign key constraint and reversibility requirements by dynamically recreating a "placeholder" resource record during a rollback if the target resource no longer exists.

Specifically:
1. When rolling back a deletion, the rollback engine checks if the target `resource_id` exists in the database.
2. If it is missing, the engine creates a placeholder record using the original `resource_id` and `resource_name` with unknown/default properties (`resource_type="unknown"`, `enabled_state="unknown"`, `startup_order=0`).
3. State changes can then be safely recorded against this placeholder, preventing the FK IntegrityError.
4. The filesystem is considered the source of truth; when the next synchronization or directory scan occurs, the placeholder's missing data will be populated correctly from the restored filesystem state (identified by the `resource_name`).

## Consequences

**Positive:**
- Fixes the `IntegrityError` that blocked undoing a resource deletion.
- Preserves referential integrity for the rollback's state-change records.
- Allows rollback operations to complete without needing complex out-of-band FK-deferral logic.

**Negative/Neutral:**
- Temporarily creates a stubbed record in the database (`resource_type="unknown"`) until the next background scan catches up and hydrates it with real filesystem data.
- The `resource_name` must be reliably preserved and passed down to the rollback operation so that the placeholder can be properly matched and updated during the subsequent scan.
