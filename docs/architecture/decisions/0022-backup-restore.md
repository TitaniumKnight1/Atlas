# ADR-0022: Backup and Restore

## Status

Accepted (M8c)

## Context

Atlas needs local-only project backups with honest consistency guarantees and reversible restore — the most dangerous operation in the system. M8b deferred nightly backup until this module existed.

## Decisions

### Local-only boundary

Backup archives are written under `{app_data_dir}/backups/{project_id}/`. They are never telemetry, never auto-uploaded, and never leave the machine without an explicit future feature.

### Consistency at capture

1. Files are staged via M3a filesystem copy semantics into a staging tree, then compressed with stdlib `zipfile`.
2. Project SQLite databases use the SQLite backup API (`connection.backup`), not raw mid-write file copy.
3. The Atlas application database (`atlas.sqlite3`) is never included in project backups.
4. When M3b reports a running/stopped/starting server process, capture is **best-effort** with an explicit warning. When the server is stopped, capture is **quiesced**. We never claim crash consistency while the server is running.

### Backup is additive

Creating a backup reads project state and writes a local archive. It is audited but does not require undo; deleting/pruning is the inverse and is separately audited.

### Restore is destructive and reversible

Restore flow:

1. **Preview** — list paths that will be overwritten and surface warnings.
2. **Pre-restore snapshot** — copy the current project root to `.atlas-snapshots/{project_id}/pre-restore-{restore_id}` via M3a snapshot semantics.
3. **Execute** — extract archive into the project root inside a UoW with command audit + undo plan.
4. **Undo** — `RestorePathFromSnapshotCompensation` (M5b composite compensation) restores the pre-restore snapshot byte-for-byte.

If pre-restore snapshot fails, restore requires `confirm_destructive=true`; never silent destroy.

### Retention

Retention evaluation reuses M6b-style horizon thinking (`keep_count`, `keep_days`, optional `allow_prune_last`). Pruning is audited and idempotent. The last remaining succeeded backup is protected unless `allow_prune_last` is explicitly set.

### Scheduling

Scheduled backups use the M8a in-process DB poll pattern (`BackupSchedulerService`), not APScheduler. The poll respects the automation global kill switch. M8b nightly maintenance wires `CREATE_BACKUP` as **AUTO** (additive/read-only safety class).

### Compression

Stdlib `zipfile` only — no additional compression dependencies.

## Consequences

- Operators get honest warnings for hot backups while the FXServer is running.
- Restore mistakes are recoverable via undo when snapshot succeeds.
- Backup archives are the most complete local copy of project data; treat filesystem permissions accordingly.
