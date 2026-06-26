# ADR-0003: Command Preview, Dry Run, Audit, And Undo Contract

## Status

Accepted

## Context

M1a introduces the Project bounded context and the command template later modules will inherit. Atlas commands must be developer-first: preview intended changes, dry-run validation without mutation, execute through the single-writer Unit of Work, record audit history, and offer undo where a safe compensation exists.

## Decision

Commands expose four lifecycle operations:

1. `preview` returns a human-readable plan and warnings without mutation.
2. `dry_run` performs validation and simulation without persistence or adapter mutation.
3. `execute` applies state changes inside the M0b Unit of Work, records command plan, command execution, audit event, and persisted domain event rows, then publishes domain events after commit.
4. `undo` runs a command-provided compensating action and records its own command execution and audit event.

Undo is not a base-class delete. Each command returns or stores an `UndoPlan` containing a `CompensatingAction`. For `ImportProject`, compensation archives the imported metadata. A future filesystem command could supply a compensation that restores a snapshot, renames a moved file back, or stops a process it started. The command infrastructure only invokes the compensation; it does not assume the resource is a database row.

HTTP undo accepts only a prior `command_execution_id` and rehydrates the compensating action server-side from the stored audit/execution record; clients must not supply action parameters.

## Consequences

- Preview and dry-run are safe to expose before user approval because they do not persist.
- Execute and undo are both auditable writes.
- Domain events remain post-commit per ADR-0002.
- Real migrations remain deferred; M1a uses idempotent SQLAlchemy metadata bootstrap only.
