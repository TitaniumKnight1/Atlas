# Automation Schema

Feature traceability: visual trigger/action workflows, schedules, dry runs, approvals, undo plans, audit logs, durable schedule metadata, and failure incidents.

## Tables

### `automation_workflows`

| Column | Type | Notes |
| --- | --- | --- |
| `workflow_id` | `TEXT` | Primary key. |
| `project_id` | `TEXT` | Required FK to `projects`. |
| `name` | `TEXT` | Required. |
| `description` | `TEXT` | Nullable. |
| `is_enabled` | `INTEGER` | Boolean 0/1. |
| `current_version_id` | `TEXT` | Nullable FK to `automation_workflow_versions`. |
| `created_at` | `TEXT` | Required UTC timestamp. |
| `updated_at` | `TEXT` | Required UTC timestamp. |

Keys and constraints: PK `workflow_id`; unique `(project_id, name)`.
Indexes: `idx_automation_workflows_enabled(project_id, is_enabled)`.
Lifecycle: soft-disabled rather than deleted when history exists.
Rationale: stable workflow identity across versions and runs.

### `automation_workflow_versions`

| Column | Type | Notes |
| --- | --- | --- |
| `workflow_version_id` | `TEXT` | Primary key. |
| `workflow_id` | `TEXT` | Required FK to `automation_workflows`. |
| `version_number` | `INTEGER` | Required. |
| `definition_json` | `JSON` | Required versioned visual workflow definition. |
| `required_capabilities_json` | `JSON` | Required capability list snapshot. |
| `created_at` | `TEXT` | Required UTC timestamp. |
| `created_by` | `TEXT` | Nullable actor id. |

Keys and constraints: PK `workflow_version_id`; unique `(workflow_id, version_number)`.
Indexes: `idx_automation_versions_workflow(workflow_id, version_number)`.
Lifecycle: immutable after creation.
Rationale: automation runs must reference the exact definition that executed.

### `automation_triggers`

| Column | Type | Notes |
| --- | --- | --- |
| `trigger_id` | `TEXT` | Primary key. |
| `workflow_version_id` | `TEXT` | Required FK to `automation_workflow_versions`. |
| `trigger_type` | `TEXT` | Required: `git_pull_completed`, `server_crashed`, `resource_changed`, `schedule`, `validation_failed`, `backup_completed`, `incident_created`, `plugin`. |
| `config_json` | `JSON` | Required trigger configuration. |
| `sort_order` | `INTEGER` | Required. |

Keys and constraints: PK `trigger_id`; unique `(workflow_version_id, sort_order)`.
Indexes: `idx_automation_triggers_type(trigger_type)`.
Lifecycle: immutable with workflow version.
Rationale: stores event sources that start workflows.

### `automation_conditions`

| Column | Type | Notes |
| --- | --- | --- |
| `condition_id` | `TEXT` | Primary key. |
| `workflow_version_id` | `TEXT` | Required FK to `automation_workflow_versions`. |
| `condition_type` | `TEXT` | Required. |
| `config_json` | `JSON` | Required condition configuration. |
| `sort_order` | `INTEGER` | Required. |

Keys and constraints: PK `condition_id`; unique `(workflow_version_id, sort_order)`.
Indexes: `idx_automation_conditions_version(workflow_version_id)`.
Lifecycle: immutable with workflow version.
Rationale: conditions are shape-flexible and evaluated by workflow runner.

### `automation_actions`

| Column | Type | Notes |
| --- | --- | --- |
| `action_id` | `TEXT` | Primary key. |
| `workflow_version_id` | `TEXT` | Required FK to `automation_workflow_versions`. |
| `action_type` | `TEXT` | Required: `restart_server`, `restart_resource`, `run_validation`, `create_backup`, `export_report`, `notify_local`, `run_command`, `plugin`. |
| `safety_class` | `TEXT` | Required: `read_only`, `reversible_write`, `process_control`, `destructive`, `external`. |
| `requires_approval` | `INTEGER` | Boolean 0/1. |
| `config_json` | `JSON` | Required action configuration. |
| `sort_order` | `INTEGER` | Required. |

Keys and constraints: PK `action_id`; unique `(workflow_version_id, sort_order)`.
Indexes: `idx_automation_actions_safety(safety_class, requires_approval)`.
Lifecycle: immutable with workflow version.
Rationale: makes action safety and approval policy queryable.

### `automation_schedules`

| Column | Type | Notes |
| --- | --- | --- |
| `schedule_id` | `TEXT` | Primary key. |
| `workflow_id` | `TEXT` | Required FK to `automation_workflows`. |
| `trigger_id` | `TEXT` | Nullable FK to `automation_triggers`. |
| `schedule_key` | `TEXT` | Required stable scheduler id. |
| `timezone` | `TEXT` | Required. |
| `schedule_json` | `JSON` | Required cron/interval definition. |
| `next_run_at` | `TEXT` | Nullable UTC timestamp. |
| `is_enabled` | `INTEGER` | Boolean 0/1. |
| `updated_at` | `TEXT` | Required UTC timestamp. |

Keys and constraints: PK `schedule_id`; unique `schedule_key`.
Indexes: `idx_automation_schedules_due(is_enabled, next_run_at)`.
Lifecycle: current scheduler state; changes audited.
Rationale: supports APScheduler ownership with stable IDs.

### `automation_runs`

| Column | Type | Notes |
| --- | --- | --- |
| `run_id` | `TEXT` | Primary key. |
| `workflow_id` | `TEXT` | Required FK to `automation_workflows`. |
| `workflow_version_id` | `TEXT` | Required FK to `automation_workflow_versions`. |
| `project_id` | `TEXT` | Required FK to `projects`. |
| `trigger_event_id` | `TEXT` | Nullable FK to `domain_events`. |
| `status` | `TEXT` | Required: `queued`, `running`, `waiting_approval`, `succeeded`, `failed`, `cancelled`, `skipped`. |
| `started_at` | `TEXT` | Nullable UTC timestamp. |
| `finished_at` | `TEXT` | Nullable UTC timestamp. |
| `dry_run_plan_json` | `JSON` | Nullable plan shown to user. |

Keys and constraints: PK `run_id`; check `status`.
Indexes: `idx_automation_runs_project_time(project_id, started_at)`, `idx_automation_runs_status(status)`.
Lifecycle: retain run summaries; compact detailed step payloads by policy.
Rationale: durable record of every workflow execution.

### `automation_run_steps`

| Column | Type | Notes |
| --- | --- | --- |
| `run_step_id` | `TEXT` | Primary key. |
| `run_id` | `TEXT` | Required FK to `automation_runs`. |
| `action_id` | `TEXT` | Nullable FK to `automation_actions`. |
| `step_order` | `INTEGER` | Required. |
| `status` | `TEXT` | Required. |
| `started_at` | `TEXT` | Nullable UTC timestamp. |
| `finished_at` | `TEXT` | Nullable UTC timestamp. |
| `result_json` | `JSON` | Nullable sanitized action result. |
| `incident_group_id` | `TEXT` | Nullable FK to `incident_groups` on failure. |

Keys and constraints: PK `run_step_id`; unique `(run_id, step_order)`.
Indexes: `idx_automation_run_steps_run_status(run_id, status)`.
Lifecycle: follows run retention.
Rationale: supports progress UI, audit, and failure incident creation.

### `automation_approvals`

| Column | Type | Notes |
| --- | --- | --- |
| `approval_id` | `TEXT` | Primary key. |
| `run_id` | `TEXT` | Required FK to `automation_runs`. |
| `action_id` | `TEXT` | Nullable FK to `automation_actions`. |
| `approval_state` | `TEXT` | Required: `pending`, `approved`, `denied`, `expired`. |
| `requested_at` | `TEXT` | Required UTC timestamp. |
| `decided_at` | `TEXT` | Nullable UTC timestamp. |
| `decided_by` | `TEXT` | Nullable actor id. |
| `approval_reason` | `TEXT` | Nullable. |

Keys and constraints: PK `approval_id`; check `approval_state`.
Indexes: `idx_automation_approvals_pending(approval_state, requested_at)`.
Lifecycle: retained with run.
Rationale: enforces developer-first approval gates.

### `automation_idempotency_keys`

| Column | Type | Notes |
| --- | --- | --- |
| `idempotency_key_id` | `TEXT` | Primary key. |
| `run_id` | `TEXT` | Required FK to `automation_runs`. |
| `key_value` | `TEXT` | Required. |
| `operation_type` | `TEXT` | Required. |
| `created_at` | `TEXT` | Required UTC timestamp. |
| `expires_at` | `TEXT` | Nullable UTC timestamp. |

Keys and constraints: PK `idempotency_key_id`; unique `key_value`.
Indexes: `idx_automation_idempotency_expires(expires_at)`.
Lifecycle: prune expired keys after retry window.
Rationale: prevents duplicate scheduler and retry writes under SQLite single-writer constraints.

## Open Questions

- Whether workflow definitions should be optionally exported to project-local YAML for version control.
- Which action safety classes are allowed unattended in MVP.

## Deviations

None.
