# Audit And Shared Schema

Feature traceability: developer-first transparency, command dry runs, audit history, plugin capability approvals, app settings, local file references, tagging, and future migration bookkeeping.

## Tables

### `schema_migrations`

| Column | Type | Notes |
| --- | --- | --- |
| `migration_id` | `TEXT` | Primary key. |
| `version` | `TEXT` | Required unique migration version. |
| `description` | `TEXT` | Required. |
| `checksum` | `TEXT` | Nullable future script checksum. |
| `applied_at` | `TEXT` | Required UTC timestamp. |
| `applied_by_app_version` | `TEXT` | Nullable Atlas version. |

Keys and constraints: PK `migration_id`; unique `version`.
Indexes: `idx_schema_migrations_applied_at(applied_at)`.
Lifecycle: permanent.
Rationale: documents intended migration bookkeeping without choosing a migration tool.

### `audit_events`

| Column | Type | Notes |
| --- | --- | --- |
| `audit_event_id` | `TEXT` | Primary key. |
| `project_id` | `TEXT` | Nullable FK to `projects`. |
| `event_type` | `TEXT` | Required. |
| `entity_type` | `TEXT` | Required. |
| `entity_id` | `TEXT` | Nullable polymorphic entity id. |
| `actor_type` | `TEXT` | Required: `user`, `automation`, `plugin`, `system`. |
| `actor_id` | `TEXT` | Nullable. |
| `occurred_at` | `TEXT` | Required UTC timestamp. |
| `summary` | `TEXT` | Required. |
| `details_json` | `JSON` | Nullable non-sensitive details. |

Keys and constraints: PK `audit_event_id`; check `actor_type`.
Indexes: `idx_audit_events_project_time(project_id, occurred_at)`, `idx_audit_events_entity(entity_type, entity_id)`.
Lifecycle: long-term; archive only by explicit user policy.
Rationale: central developer-first history of visible actions.

### `command_plans`

| Column | Type | Notes |
| --- | --- | --- |
| `command_plan_id` | `TEXT` | Primary key. |
| `project_id` | `TEXT` | Nullable FK to `projects`. |
| `command_type` | `TEXT` | Required. |
| `status` | `TEXT` | Required: `draft`, `presented`, `approved`, `expired`, `cancelled`. |
| `risk_level` | `TEXT` | Required: `low`, `medium`, `high`, `destructive`. |
| `dry_run_plan_json` | `JSON` | Required preview, diff, undo plan. |
| `created_at` | `TEXT` | Required UTC timestamp. |
| `expires_at` | `TEXT` | Nullable UTC timestamp. |

Keys and constraints: PK `command_plan_id`; check `status`; check `risk_level`.
Indexes: `idx_command_plans_project_time(project_id, created_at)`, `idx_command_plans_status(status)`.
Lifecycle: prune expired unexecuted plans; retain executed plans via command executions.
Rationale: persists dry-run previews before mutation.

### `command_executions`

| Column | Type | Notes |
| --- | --- | --- |
| `command_execution_id` | `TEXT` | Primary key. |
| `command_plan_id` | `TEXT` | Nullable FK to `command_plans`. |
| `project_id` | `TEXT` | Nullable FK to `projects`. |
| `status` | `TEXT` | Required: `queued`, `running`, `succeeded`, `failed`, `cancelled`. |
| `started_at` | `TEXT` | Nullable UTC timestamp. |
| `finished_at` | `TEXT` | Nullable UTC timestamp. |
| `idempotency_key` | `TEXT` | Nullable unique key. |
| `result_json` | `JSON` | Nullable sanitized result. |
| `audit_event_id` | `TEXT` | Nullable FK to `audit_events`. |

Keys and constraints: PK `command_execution_id`; unique `idempotency_key` when present.
Indexes: `idx_command_executions_project_time(project_id, started_at)`, `idx_command_executions_status(status)`.
Lifecycle: long-term summaries; large result payloads externalized if needed.
Rationale: records the actual execution of previewed commands.

### `domain_events`

| Column | Type | Notes |
| --- | --- | --- |
| `domain_event_id` | `TEXT` | Primary key. |
| `project_id` | `TEXT` | Nullable FK to `projects`. |
| `event_type` | `TEXT` | Required, e.g. `IncidentCreated`. |
| `aggregate_type` | `TEXT` | Required. |
| `aggregate_id` | `TEXT` | Required. |
| `occurred_at` | `TEXT` | Required UTC timestamp. |
| `payload_json` | `JSON` | Required versioned event payload. |
| `published_at` | `TEXT` | Nullable UTC timestamp. |

Keys and constraints: PK `domain_event_id`.
Indexes: `idx_domain_events_project_time(project_id, occurred_at)`, `idx_domain_events_type_time(event_type, occurred_at)`, `idx_domain_events_aggregate(aggregate_type, aggregate_id)`.
Lifecycle: event log retained long-term or archived; payloads must remain local.
Rationale: supports event bus replay, automation triggers, and audit correlation.

### `app_settings`

| Column | Type | Notes |
| --- | --- | --- |
| `app_setting_id` | `TEXT` | Primary key. |
| `setting_key` | `TEXT` | Required unique dotted key. |
| `value_json` | `JSON` | Required setting value. |
| `value_type` | `TEXT` | Required. |
| `updated_at` | `TEXT` | Required UTC timestamp. |
| `updated_by` | `TEXT` | Nullable actor id. |

Keys and constraints: PK `app_setting_id`; unique `setting_key`.
Indexes: `idx_app_settings_key(setting_key)`.
Lifecycle: current-value table; changes audited if safety/privacy relevant.
Rationale: app-global Atlas settings distinct from project settings.

### `plugin_registrations`

| Column | Type | Notes |
| --- | --- | --- |
| `plugin_registration_id` | `TEXT` | Primary key. |
| `plugin_identifier` | `TEXT` | Required stable plugin id. |
| `display_name` | `TEXT` | Required. |
| `version` | `TEXT` | Required. |
| `source_type` | `TEXT` | Required: `local`, `marketplace`, `builtin`. |
| `source_ref` | `TEXT` | Nullable. |
| `manifest_json` | `JSON` | Required manifest snapshot. |
| `enabled_state` | `TEXT` | Required: `enabled`, `disabled`, `restricted`. |
| `installed_at` | `TEXT` | Required UTC timestamp. |
| `updated_at` | `TEXT` | Required UTC timestamp. |

Keys and constraints: PK `plugin_registration_id`; unique `(plugin_identifier, version)`.
Indexes: `idx_plugin_registrations_state(enabled_state)`.
Lifecycle: retain registrations while installed; past versions can be archived.
Rationale: supports plugin discovery and capability enforcement.

### `plugin_capability_grants`

| Column | Type | Notes |
| --- | --- | --- |
| `capability_grant_id` | `TEXT` | Primary key. |
| `plugin_registration_id` | `TEXT` | Required FK to `plugin_registrations`. |
| `project_id` | `TEXT` | Nullable FK to `projects`. |
| `capability` | `TEXT` | Required capability id. |
| `grant_state` | `TEXT` | Required: `granted`, `denied`, `revoked`. |
| `scope_json` | `JSON` | Nullable path/project scope. |
| `decided_at` | `TEXT` | Required UTC timestamp. |
| `decided_by` | `TEXT` | Nullable actor id. |

Keys and constraints: PK `capability_grant_id`; unique `(plugin_registration_id, project_id, capability)`.
Indexes: `idx_plugin_capability_project(project_id, grant_state)`.
Lifecycle: current grants; changes audited.
Rationale: enforces plugin trust and privacy boundaries.

### `local_files`

| Column | Type | Notes |
| --- | --- | --- |
| `local_file_id` | `TEXT` | Primary key. |
| `project_id` | `TEXT` | Nullable FK to `projects`. |
| `file_role` | `TEXT` | Required: `backup`, `snapshot`, `incident_context`, `export`, `artifact_cache`, `diff`. |
| `absolute_path` | `TEXT` | Required normalized local path. |
| `content_hash` | `TEXT` | Nullable. |
| `size_bytes` | `INTEGER` | Nullable. |
| `created_at` | `TEXT` | Required UTC timestamp. |
| `last_verified_at` | `TEXT` | Nullable UTC timestamp. |

Keys and constraints: PK `local_file_id`; unique `(file_role, absolute_path)`.
Indexes: `idx_local_files_project_role(project_id, file_role)`, `idx_local_files_hash(content_hash)`.
Lifecycle: reference table; file retention determined by owning subsystem.
Rationale: keeps large blobs out of SQLite while preserving metadata.

### `tags`

| Column | Type | Notes |
| --- | --- | --- |
| `tag_id` | `TEXT` | Primary key. |
| `project_id` | `TEXT` | Nullable FK to `projects`; null means global. |
| `tag_key` | `TEXT` | Required. |
| `tag_value` | `TEXT` | Required. |
| `created_at` | `TEXT` | Required UTC timestamp. |

Keys and constraints: PK `tag_id`; unique `(project_id, tag_key, tag_value)`.
Indexes: `idx_tags_key_value(tag_key, tag_value)`.
Lifecycle: retained while referenced.
Rationale: common labeling for incidents, backups, automations, and resources.

### `entity_tags`

| Column | Type | Notes |
| --- | --- | --- |
| `entity_tag_id` | `TEXT` | Primary key. |
| `tag_id` | `TEXT` | Required FK to `tags`. |
| `entity_type` | `TEXT` | Required. |
| `entity_id` | `TEXT` | Required. |
| `created_at` | `TEXT` | Required UTC timestamp. |

Keys and constraints: PK `entity_tag_id`; unique `(tag_id, entity_type, entity_id)`.
Indexes: `idx_entity_tags_entity(entity_type, entity_id)`.
Lifecycle: deleted when entity or tag is removed.
Rationale: generic tags without adding tag tables to every context.

## Open Questions

- Whether domain events should become a strict outbox table for process restart recovery.
- Whether plugin registrations should support publisher signatures in the first implementation.

## Deviations

`schema_migrations` is documented as an intended table, but no migration tool or migration files are created in Phase 5.
