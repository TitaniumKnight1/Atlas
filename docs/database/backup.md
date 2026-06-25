# Backup Schema

Feature traceability: scheduled backups, one-click restore, database backups, configuration backups, version snapshots, compression, retention policies, and local export/import.

## Tables

### `backup_plans`

| Column | Type | Notes |
| --- | --- | --- |
| `backup_plan_id` | `TEXT` | Primary key. |
| `project_id` | `TEXT` | Required FK to `projects`. |
| `environment_id` | `TEXT` | Nullable FK to `environment_profiles`. |
| `name` | `TEXT` | Required. |
| `backup_scope` | `TEXT` | Required: `config`, `resources`, `database`, `full`, `custom`. |
| `schedule_id` | `TEXT` | Nullable FK to `automation_schedules`. |
| `retention_policy_json` | `JSON` | Required versioned policy. |
| `is_enabled` | `INTEGER` | Boolean 0/1. |
| `created_at` | `TEXT` | Required UTC timestamp. |
| `updated_at` | `TEXT` | Required UTC timestamp. |

Keys and constraints: PK `backup_plan_id`; unique `(project_id, name)`; check `is_enabled`.
Indexes: `idx_backup_plans_project_enabled(project_id, is_enabled)`.
Lifecycle: current plan state; history in `backup_runs` and audit events.
Rationale: separates reusable policy from individual backup execution.

### `backup_runs`

| Column | Type | Notes |
| --- | --- | --- |
| `backup_run_id` | `TEXT` | Primary key. |
| `backup_plan_id` | `TEXT` | Nullable FK to `backup_plans`. |
| `project_id` | `TEXT` | Required FK to `projects`. |
| `status` | `TEXT` | Required: `planned`, `running`, `succeeded`, `failed`, `cancelled`, `pruned`. |
| `trigger_type` | `TEXT` | Required: `manual`, `scheduled`, `pre_change`, `automation`. |
| `artifact_version_id` | `TEXT` | Nullable FK to `artifact_versions`. |
| `git_status_snapshot_id` | `TEXT` | Nullable FK to `git_worktree_status_snapshots`. |
| `started_at` | `TEXT` | Nullable UTC timestamp. |
| `finished_at` | `TEXT` | Nullable UTC timestamp. |
| `total_bytes` | `INTEGER` | Nullable. |
| `manifest_json` | `JSON` | Nullable backup manifest. |

Keys and constraints: PK `backup_run_id`; check `status`.
Indexes: `idx_backup_runs_project_time(project_id, started_at)`, `idx_backup_runs_status(status)`.
Lifecycle: retained per backup policy; pruned rows keep summary and audit trail.
Rationale: records each backup as a point-in-time recovery candidate.

### `backup_items`

| Column | Type | Notes |
| --- | --- | --- |
| `backup_item_id` | `TEXT` | Primary key. |
| `backup_run_id` | `TEXT` | Required FK to `backup_runs`. |
| `item_type` | `TEXT` | Required: `config`, `resource`, `database`, `artifact_metadata`, `snapshot`, `log`. |
| `source_path` | `TEXT` | Nullable original path. |
| `local_file_id` | `TEXT` | Nullable FK to `local_files`. |
| `content_hash` | `TEXT` | Nullable. |
| `size_bytes` | `INTEGER` | Nullable. |
| `metadata_json` | `JSON` | Nullable. |

Keys and constraints: PK `backup_item_id`.
Indexes: `idx_backup_items_run_type(backup_run_id, item_type)`, `idx_backup_items_hash(content_hash)`.
Lifecycle: follows parent backup run.
Rationale: catalog of what a backup contains without requiring database-embedded file bodies.

### `backup_restore_runs`

| Column | Type | Notes |
| --- | --- | --- |
| `restore_run_id` | `TEXT` | Primary key. |
| `backup_run_id` | `TEXT` | Required FK to `backup_runs`. |
| `project_id` | `TEXT` | Required FK to `projects`. |
| `status` | `TEXT` | Required: `planned`, `running`, `succeeded`, `failed`, `cancelled`. |
| `dry_run` | `INTEGER` | Boolean 0/1. |
| `command_execution_id` | `TEXT` | Nullable FK to `command_executions`. |
| `started_at` | `TEXT` | Nullable UTC timestamp. |
| `finished_at` | `TEXT` | Nullable UTC timestamp. |
| `restore_plan_json` | `JSON` | Required preview/plan. |

Keys and constraints: PK `restore_run_id`; check `dry_run`.
Indexes: `idx_backup_restore_project_time(project_id, started_at)`.
Lifecycle: retained as audit history.
Rationale: supports one-click restore with preview and rollback accountability.

### `backup_retention_events`

| Column | Type | Notes |
| --- | --- | --- |
| `retention_event_id` | `TEXT` | Primary key. |
| `backup_plan_id` | `TEXT` | Nullable FK to `backup_plans`. |
| `backup_run_id` | `TEXT` | Nullable FK to `backup_runs`. |
| `project_id` | `TEXT` | Required FK to `projects`. |
| `event_type` | `TEXT` | Required: `evaluated`, `pruned`, `skipped`, `failed`. |
| `reason` | `TEXT` | Nullable. |
| `occurred_at` | `TEXT` | Required UTC timestamp. |
| `details_json` | `JSON` | Nullable. |

Keys and constraints: PK `retention_event_id`; check `event_type`.
Indexes: `idx_backup_retention_project_time(project_id, occurred_at)`.
Lifecycle: long-term compact audit trail.
Rationale: explains why backups were retained or pruned.

## Open Questions

- Whether Atlas should support immutable backup manifests signed with a content hash.
- Whether backup catalogs should be exportable independently of the main app database.

## Deviations

None.
