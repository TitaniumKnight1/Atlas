# Incident Schema

Feature traceability: local incident capture, fingerprinting, deduplication, grouping, timeline, breadcrumbs, environment snapshots, Git context, related incidents, comparison, and Markdown export.

## Tables

### `incident_groups`

| Column | Type | Notes |
| --- | --- | --- |
| `incident_group_id` | `TEXT` | Primary key. |
| `project_id` | `TEXT` | Required FK to `projects`. |
| `fingerprint` | `TEXT` | Required stable grouping key. |
| `title` | `TEXT` | Required. |
| `severity` | `TEXT` | Required: `debug`, `info`, `warning`, `error`, `fatal`. |
| `category` | `TEXT` | Required: `crash`, `startup`, `resource`, `validation`, `database`, `automation`, `plugin`, `atlas`. |
| `status` | `TEXT` | Required: `unresolved`, `resolved`, `ignored`, `muted`. |
| `first_seen_at` | `TEXT` | Required UTC timestamp. |
| `last_seen_at` | `TEXT` | Required UTC timestamp. |
| `occurrence_count` | `INTEGER` | Required, default 0. |
| `assigned_to` | `TEXT` | Nullable local actor id. |

Keys and constraints: PK `incident_group_id`; unique `(project_id, fingerprint)`; check `severity`; check `status`.
Indexes: `idx_incident_groups_project_status_last_seen(project_id, status, last_seen_at)`, `idx_incident_groups_severity(severity)`.
Lifecycle: long-lived; groups remain after old occurrences are compacted.
Rationale: top-level deduplicated issue record.

### `incident_occurrences`

| Column | Type | Notes |
| --- | --- | --- |
| `occurrence_id` | `TEXT` | Primary key. |
| `incident_group_id` | `TEXT` | Required FK to `incident_groups`. |
| `project_id` | `TEXT` | Required FK to `projects`. |
| `environment_id` | `TEXT` | Nullable FK to `environment_profiles`. |
| `occurred_at` | `TEXT` | Required UTC timestamp. |
| `source_type` | `TEXT` | Required: `log`, `process`, `validation`, `automation`, `plugin`, `manual`. |
| `message` | `TEXT` | Required normalized message. |
| `raw_message_hash` | `TEXT` | Nullable hash of raw message. |
| `artifact_version_id` | `TEXT` | Nullable FK to `artifact_versions`. |
| `git_status_snapshot_id` | `TEXT` | Nullable FK to `git_worktree_status_snapshots`. |
| `automation_run_id` | `TEXT` | Nullable FK to `automation_runs`. |
| `resource_id` | `TEXT` | Nullable FK to `resources`. |

Keys and constraints: PK `occurrence_id`; check `source_type`.
Indexes: `idx_incident_occurrences_group_time(incident_group_id, occurred_at)`, `idx_incident_occurrences_project_time(project_id, occurred_at)`.
Lifecycle: retain recent occurrences; compact old occurrences into group counters and summaries.
Rationale: point-in-time incident instance with environment, Git, artifact, and resource context.

### `incident_fingerprints`

| Column | Type | Notes |
| --- | --- | --- |
| `incident_fingerprint_id` | `TEXT` | Primary key. |
| `incident_group_id` | `TEXT` | Required FK to `incident_groups`. |
| `fingerprint` | `TEXT` | Required. |
| `algorithm_version` | `TEXT` | Required. |
| `components_json` | `JSON` | Required component list used to compute fingerprint. |
| `is_active` | `INTEGER` | Boolean 0/1. |
| `created_at` | `TEXT` | Required UTC timestamp. |

Keys and constraints: PK `incident_fingerprint_id`; unique `(incident_group_id, fingerprint, algorithm_version)`.
Indexes: `idx_incident_fingerprints_active(fingerprint, is_active)`.
Lifecycle: retain when algorithm changes to preserve grouping history.
Rationale: supports future regrouping and explainable deduplication.

### `incident_breadcrumbs`

| Column | Type | Notes |
| --- | --- | --- |
| `breadcrumb_id` | `TEXT` | Primary key. |
| `occurrence_id` | `TEXT` | Required FK to `incident_occurrences`. |
| `timestamp` | `TEXT` | Required UTC timestamp. |
| `category` | `TEXT` | Required: `server`, `resource`, `git`, `config`, `automation`, `process`, `log`. |
| `level` | `TEXT` | Required: `debug`, `info`, `warning`, `error`, `fatal`. |
| `message` | `TEXT` | Required. |
| `data_json` | `JSON` | Nullable local context. |
| `sort_order` | `INTEGER` | Required. |

Keys and constraints: PK `breadcrumb_id`; unique `(occurrence_id, sort_order)`.
Indexes: `idx_incident_breadcrumbs_occurrence_time(occurrence_id, timestamp)`.
Lifecycle: high-volume; prune or summarize old breadcrumbs while retaining occurrence summary.
Rationale: local Sentry-like timeline before the failure.

### `incident_context_snapshots`

| Column | Type | Notes |
| --- | --- | --- |
| `context_snapshot_id` | `TEXT` | Primary key. |
| `occurrence_id` | `TEXT` | Required FK to `incident_occurrences`. |
| `context_type` | `TEXT` | Required: `environment`, `runtime`, `resources`, `startup_order`, `config_excerpt`, `logs`, `database`, `system`. |
| `content_hash` | `TEXT` | Nullable. |
| `local_file_id` | `TEXT` | Nullable FK to `local_files` for large snapshot. |
| `snapshot_json` | `JSON` | Nullable inline snapshot for small/versioned data. |
| `redaction_state` | `TEXT` | Required: `raw_local`, `redacted`, `export_safe`, `blocked`. |
| `captured_at` | `TEXT` | Required UTC timestamp. |

Keys and constraints: PK `context_snapshot_id`; check `redaction_state`.
Indexes: `idx_incident_context_occurrence_type(occurrence_id, context_type)`.
Lifecycle: retain recent detailed snapshots; externalize or prune large old contexts by project policy.
Rationale: stores fully local debugging context without uploading it.

### `incident_stack_traces`

| Column | Type | Notes |
| --- | --- | --- |
| `stack_trace_id` | `TEXT` | Primary key. |
| `occurrence_id` | `TEXT` | Required FK to `incident_occurrences`. |
| `exception_type` | `TEXT` | Nullable. |
| `exception_value` | `TEXT` | Nullable normalized message. |
| `language` | `TEXT` | Nullable: `lua`, `js`, `csharp`, `python`, `unknown`. |
| `thread_name` | `TEXT` | Nullable. |
| `is_primary` | `INTEGER` | Boolean 0/1. |

Keys and constraints: PK `stack_trace_id`.
Indexes: `idx_incident_stack_traces_occurrence(occurrence_id)`, `idx_incident_stack_traces_exception(exception_type)`.
Lifecycle: follows occurrence retention; top frames may be preserved in group summary.
Rationale: first-class stack traces for grouping and AI-ready exports.

### `incident_stack_frames`

| Column | Type | Notes |
| --- | --- | --- |
| `stack_frame_id` | `TEXT` | Primary key. |
| `stack_trace_id` | `TEXT` | Required FK to `incident_stack_traces`. |
| `frame_index` | `INTEGER` | Required. |
| `function_name` | `TEXT` | Nullable. |
| `file_path` | `TEXT` | Nullable. |
| `line_number` | `INTEGER` | Nullable. |
| `column_number` | `INTEGER` | Nullable. |
| `resource_id` | `TEXT` | Nullable FK to `resources`. |
| `in_app` | `INTEGER` | Boolean 0/1. |
| `frame_hash` | `TEXT` | Nullable normalized frame hash. |

Keys and constraints: PK `stack_frame_id`; unique `(stack_trace_id, frame_index)`.
Indexes: `idx_incident_stack_frames_trace_index(stack_trace_id, frame_index)`, `idx_incident_stack_frames_hash(frame_hash)`.
Lifecycle: follows stack trace retention.
Rationale: supports stable fingerprinting based on top in-app frames.

### `incident_related_groups`

| Column | Type | Notes |
| --- | --- | --- |
| `incident_relation_id` | `TEXT` | Primary key. |
| `source_group_id` | `TEXT` | Required FK to `incident_groups`. |
| `target_group_id` | `TEXT` | Required FK to `incident_groups`. |
| `relation_type` | `TEXT` | Required: `same_root_cause`, `caused_by`, `duplicates`, `regression`, `user_linked`. |
| `confidence` | `REAL` | Nullable 0.0-1.0. |
| `created_at` | `TEXT` | Required UTC timestamp. |

Keys and constraints: PK `incident_relation_id`; unique `(source_group_id, target_group_id, relation_type)`.
Indexes: `idx_incident_related_source(source_group_id)`, `idx_incident_related_target(target_group_id)`.
Lifecycle: retained with groups.
Rationale: supports related incident navigation and comparison.

### `incident_exports`

| Column | Type | Notes |
| --- | --- | --- |
| `incident_export_id` | `TEXT` | Primary key. |
| `incident_group_id` | `TEXT` | Required FK to `incident_groups`. |
| `occurrence_id` | `TEXT` | Nullable FK to `incident_occurrences`. |
| `export_format` | `TEXT` | Required: `markdown`. |
| `redaction_profile` | `TEXT` | Required. |
| `local_file_id` | `TEXT` | Nullable FK to `local_files`. |
| `content_hash` | `TEXT` | Nullable. |
| `created_at` | `TEXT` | Required UTC timestamp. |
| `warning_json` | `JSON` | Nullable export warnings. |

Keys and constraints: PK `incident_export_id`.
Indexes: `idx_incident_exports_group_time(incident_group_id, created_at)`.
Lifecycle: store metadata/path/hash; avoid duplicating large Markdown bodies in SQLite.
Rationale: supports manual AI debugging exports without AI API calls.

### `incident_group_rules`

| Column | Type | Notes |
| --- | --- | --- |
| `incident_group_rule_id` | `TEXT` | Primary key. |
| `project_id` | `TEXT` | Required FK to `projects`. |
| `rule_type` | `TEXT` | Required: `merge`, `split`, `ignore`, `fingerprint_override`. |
| `match_json` | `JSON` | Required versioned matcher. |
| `action_json` | `JSON` | Required versioned action. |
| `is_enabled` | `INTEGER` | Boolean 0/1. |
| `created_at` | `TEXT` | Required UTC timestamp. |
| `updated_at` | `TEXT` | Required UTC timestamp. |

Keys and constraints: PK `incident_group_rule_id`.
Indexes: `idx_incident_group_rules_project_enabled(project_id, is_enabled)`.
Lifecycle: current rule definitions; changes audited.
Rationale: mirrors Sentry-like grouping customization locally.

### `incident_notes`

| Column | Type | Notes |
| --- | --- | --- |
| `incident_note_id` | `TEXT` | Primary key. |
| `incident_group_id` | `TEXT` | Required FK to `incident_groups`. |
| `body` | `TEXT` | Required local note. |
| `created_at` | `TEXT` | Required UTC timestamp. |
| `updated_at` | `TEXT` | Nullable UTC timestamp. |
| `created_by` | `TEXT` | Nullable actor id. |

Keys and constraints: PK `incident_note_id`.
Indexes: `idx_incident_notes_group_time(incident_group_id, created_at)`.
Lifecycle: retained with incident group.
Rationale: supports local triage notes and debugging memory.

## Retention

Incident groups are long-lived. Occurrences, breadcrumbs, stack frames, and context snapshots can be compacted by age and project policy. Large context snapshots should move to `local_files`; old Markdown exports retain metadata, hash, and path even when export content is removed.

## Open Questions

- Exact size threshold for externalizing context snapshots.
- Whether `incident_group_rules` should support global rules in addition to project rules.
- Whether resolved groups should be archived separately after long inactivity.

## Deviations

None.
