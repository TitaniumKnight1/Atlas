# Project Schema

Feature traceability: project management, multiple server projects, environment profiles, workspace management, templates, and project trust from `docs/prd.md`.

## Tables

### `projects`

| Column | Type | Notes |
| --- | --- | --- |
| `project_id` | `TEXT` | Primary key. Stable Atlas identifier. |
| `slug` | `TEXT` | Required, unique, URL/path-safe display slug. |
| `display_name` | `TEXT` | Required user-facing name. |
| `description` | `TEXT` | Optional. |
| `status` | `TEXT` | Required: `active`, `archived`, `missing`, `deleted`. |
| `default_environment_id` | `TEXT` | Nullable FK to `environment_profiles.environment_id`. |
| `created_at` | `TEXT` | Required UTC timestamp. |
| `updated_at` | `TEXT` | Required UTC timestamp. |
| `last_opened_at` | `TEXT` | Nullable UTC timestamp. |

Keys and constraints: PK `project_id`; unique `slug`; check `status`.
Indexes: `idx_projects_status_updated_at(status, updated_at)`.
Lifecycle: long-lived; soft-delete through `status`.
Rationale: central project record for every project-scoped table.

### `project_paths`

| Column | Type | Notes |
| --- | --- | --- |
| `project_path_id` | `TEXT` | Primary key. |
| `project_id` | `TEXT` | Required FK to `projects`. |
| `path_role` | `TEXT` | Required: `root`, `server_data`, `resources`, `txdata`, `artifacts`, `backups`, `logs`. |
| `absolute_path` | `TEXT` | Required normalized local path. |
| `exists_last_checked` | `INTEGER` | Boolean 0/1. |
| `content_hash` | `TEXT` | Nullable for small tracked files only. |
| `last_checked_at` | `TEXT` | Nullable UTC timestamp. |
| `created_at` | `TEXT` | Required UTC timestamp. |

Keys and constraints: PK `project_path_id`; FK `project_id`; unique `(project_id, path_role, absolute_path)`.
Indexes: `idx_project_paths_project_role(project_id, path_role)`.
Lifecycle: updated on project import/rescan; never stores file contents.
Rationale: preserves Atlas-app vs FiveM-project boundary by storing references, not project data.

### `environment_profiles`

| Column | Type | Notes |
| --- | --- | --- |
| `environment_id` | `TEXT` | Primary key. |
| `project_id` | `TEXT` | Required FK to `projects`. |
| `name` | `TEXT` | Required: commonly `local`, `staging`, `production`. |
| `display_name` | `TEXT` | Required. |
| `artifact_channel` | `TEXT` | Nullable: `recommended`, `latest`, `pinned`. |
| `settings_json` | `JSON` | Optional profile settings snapshot. |
| `is_default` | `INTEGER` | Boolean 0/1. |
| `created_at` | `TEXT` | Required UTC timestamp. |
| `updated_at` | `TEXT` | Required UTC timestamp. |

Keys and constraints: PK `environment_id`; unique `(project_id, name)`; check `is_default in (0,1)`.
Indexes: `idx_environment_profiles_project_default(project_id, is_default)`.
Lifecycle: retained while project exists; settings JSON is allowed because profile shape can evolve.
Rationale: scopes artifact pins, automation policy, validation rules, and incident context.

### `project_settings`

| Column | Type | Notes |
| --- | --- | --- |
| `project_setting_id` | `TEXT` | Primary key. |
| `project_id` | `TEXT` | Required FK to `projects`. |
| `setting_key` | `TEXT` | Required dotted key. |
| `value_json` | `JSON` | Required value payload. |
| `value_type` | `TEXT` | Required: `string`, `number`, `boolean`, `object`, `array`. |
| `updated_at` | `TEXT` | Required UTC timestamp. |
| `updated_by` | `TEXT` | Nullable actor id. |

Keys and constraints: PK `project_setting_id`; unique `(project_id, setting_key)`.
Indexes: `idx_project_settings_key(setting_key)`.
Lifecycle: current-value table; changes that affect safety also create `audit_events`.
Rationale: flexible project metadata without creating columns for every future setting.

### `workspace_trust_decisions`

| Column | Type | Notes |
| --- | --- | --- |
| `trust_decision_id` | `TEXT` | Primary key. |
| `project_id` | `TEXT` | Required FK to `projects`. |
| `trust_state` | `TEXT` | Required: `trusted`, `restricted`, `revoked`. |
| `scope` | `TEXT` | Required: `project`, `plugin`, `path`. |
| `scope_ref` | `TEXT` | Nullable plugin id or path id. |
| `reason` | `TEXT` | Nullable. |
| `decided_at` | `TEXT` | Required UTC timestamp. |
| `decided_by` | `TEXT` | Nullable actor id. |

Keys and constraints: PK `trust_decision_id`; check `trust_state`; unique `(project_id, scope, scope_ref)`.
Indexes: `idx_workspace_trust_project_state(project_id, trust_state)`.
Lifecycle: append/update current trust state; important changes audited.
Rationale: supports project trust before scripts, plugins, or downloaded resources execute.

### `project_templates`

| Column | Type | Notes |
| --- | --- | --- |
| `template_id` | `TEXT` | Primary key. |
| `template_slug` | `TEXT` | Required unique slug. |
| `display_name` | `TEXT` | Required. |
| `source_type` | `TEXT` | Required: `builtin`, `plugin`, `local`. |
| `source_ref` | `TEXT` | Nullable plugin id or path. |
| `template_json` | `JSON` | Required versioned template definition. |
| `created_at` | `TEXT` | Required UTC timestamp. |
| `updated_at` | `TEXT` | Required UTC timestamp. |

Keys and constraints: PK `template_id`; unique `template_slug`; check `source_type`.
Indexes: `idx_project_templates_source(source_type, source_ref)`.
Lifecycle: builtin templates migrate with app; plugin/local templates follow their source lifecycle.
Rationale: supports wizard-driven setup while keeping template definitions versioned.

## Relationships

`projects` is the parent for all project-owned data. `environment_profiles` provides project-local scope for setup, incidents, automations, backups, and monitoring. `project_paths` references external FiveM files without owning their contents.

## Open Questions

- Whether `project_templates.template_json` should later be normalized if template search becomes important.
- Whether workspace trust history should be append-only instead of current-state plus audit events.

## Deviations

None.
