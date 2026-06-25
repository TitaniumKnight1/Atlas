# Configuration Schema

Feature traceability: GUI configuration editing, live validation, search, diff viewer, undo history, snapshots, and secret detection warnings.

## Tables

### `config_files`

| Column | Type | Notes |
| --- | --- | --- |
| `config_file_id` | `TEXT` | Primary key. |
| `project_id` | `TEXT` | Required FK to `projects`. |
| `environment_id` | `TEXT` | Nullable FK to `environment_profiles`. |
| `path` | `TEXT` | Required normalized project-relative path. |
| `config_type` | `TEXT` | Required: `server_cfg`, `resource`, `txadmin`, `database`, `unknown`. |
| `parser_kind` | `TEXT` | Nullable parser/validator id. |
| `content_hash` | `TEXT` | Nullable last observed hash. |
| `last_scanned_at` | `TEXT` | Nullable UTC timestamp. |

Keys and constraints: PK `config_file_id`; unique `(project_id, environment_id, path)`.
Indexes: `idx_config_files_project_type(project_id, config_type)`.
Lifecycle: current inventory; missing files handled by validation findings.
Rationale: central index of editable config files without storing live file contents.

### `config_snapshots`

| Column | Type | Notes |
| --- | --- | --- |
| `config_snapshot_id` | `TEXT` | Primary key. |
| `config_file_id` | `TEXT` | Required FK to `config_files`. |
| `snapshot_kind` | `TEXT` | Required: `before`, `after`, `manual`, `validation`. |
| `content_hash` | `TEXT` | Required. |
| `local_file_id` | `TEXT` | Nullable FK to `local_files` for stored snapshot body. |
| `captured_at` | `TEXT` | Required UTC timestamp. |
| `metadata_json` | `JSON` | Nullable parser metadata. |

Keys and constraints: PK `config_snapshot_id`.
Indexes: `idx_config_snapshots_file_time(config_file_id, captured_at)`.
Lifecycle: retain snapshots tied to changes/incidents; prune unreferenced old snapshots by policy.
Rationale: supports diff and undo without forcing all content into SQLite.

### `config_change_sets`

| Column | Type | Notes |
| --- | --- | --- |
| `config_change_set_id` | `TEXT` | Primary key. |
| `project_id` | `TEXT` | Required FK to `projects`. |
| `command_execution_id` | `TEXT` | Nullable FK to `command_executions`. |
| `status` | `TEXT` | Required: `planned`, `applied`, `reverted`, `failed`. |
| `summary` | `TEXT` | Nullable. |
| `before_snapshot_id` | `TEXT` | Nullable FK to `config_snapshots`. |
| `after_snapshot_id` | `TEXT` | Nullable FK to `config_snapshots`. |
| `created_at` | `TEXT` | Required UTC timestamp. |
| `applied_at` | `TEXT` | Nullable UTC timestamp. |

Keys and constraints: PK `config_change_set_id`; check `status`.
Indexes: `idx_config_change_sets_project_time(project_id, created_at)`.
Lifecycle: retain with audit history.
Rationale: groups previewed and applied config edits.

### `config_validation_runs`

| Column | Type | Notes |
| --- | --- | --- |
| `config_validation_run_id` | `TEXT` | Primary key. |
| `project_id` | `TEXT` | Required FK to `projects`. |
| `config_file_id` | `TEXT` | Nullable FK to `config_files`. |
| `validator_id` | `TEXT` | Required builtin or plugin validator id. |
| `status` | `TEXT` | Required: `pass`, `warning`, `fail`, `error`. |
| `started_at` | `TEXT` | Required UTC timestamp. |
| `finished_at` | `TEXT` | Nullable UTC timestamp. |
| `summary_json` | `JSON` | Nullable. |

Keys and constraints: PK `config_validation_run_id`; check `status`.
Indexes: `idx_config_validation_project_time(project_id, started_at)`, `idx_config_validation_status(status)`.
Lifecycle: retain recent validation history; findings may be compacted.
Rationale: supports live validation and setup preflight.

### `config_validation_findings`

| Column | Type | Notes |
| --- | --- | --- |
| `finding_id` | `TEXT` | Primary key. |
| `config_validation_run_id` | `TEXT` | Required FK to `config_validation_runs`. |
| `severity` | `TEXT` | Required: `info`, `warning`, `error`. |
| `rule_id` | `TEXT` | Required. |
| `path` | `TEXT` | Nullable file path. |
| `line` | `INTEGER` | Nullable. |
| `column` | `INTEGER` | Nullable. |
| `message` | `TEXT` | Required. |
| `details_json` | `JSON` | Nullable. |

Keys and constraints: PK `finding_id`.
Indexes: `idx_config_findings_run_severity(config_validation_run_id, severity)`.
Lifecycle: follows validation run retention.
Rationale: makes validation explainable and linkable to incidents.

### `secret_scan_findings`

| Column | Type | Notes |
| --- | --- | --- |
| `secret_finding_id` | `TEXT` | Primary key. |
| `project_id` | `TEXT` | Required FK to `projects`. |
| `config_file_id` | `TEXT` | Nullable FK to `config_files`. |
| `detector_id` | `TEXT` | Required detector name. |
| `severity` | `TEXT` | Required. |
| `path` | `TEXT` | Nullable. |
| `line` | `INTEGER` | Nullable. |
| `redacted_preview` | `TEXT` | Nullable; never raw secret. |
| `status` | `TEXT` | Required: `open`, `ignored`, `resolved`. |
| `detected_at` | `TEXT` | Required UTC timestamp. |

Keys and constraints: PK `secret_finding_id`; check `status`.
Indexes: `idx_secret_findings_project_status(project_id, status)`.
Lifecycle: retain until resolved plus audit window.
Rationale: supports privacy-first warnings without persisting secret values.

## Relationships

`config_files` belongs to a project and optional environment. Snapshots and change sets record before/after state. Validation and secret findings may create incidents when severe.

## Open Questions

- Whether config snapshots should store small file contents inline or always through `local_files`.
- How to model structured config keys if live search inside config values becomes a requirement.

## Deviations

None.
