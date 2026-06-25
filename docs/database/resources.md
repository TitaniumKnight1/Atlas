# Resources Schema

Feature traceability: resource install, update, enable, disable, delete, rollback, dependency graph, version management, Git integration, and health monitoring.

## Tables

### `resources`

| Column | Type | Notes |
| --- | --- | --- |
| `resource_id` | `TEXT` | Primary key. |
| `project_id` | `TEXT` | Required FK to `projects`. |
| `resource_name` | `TEXT` | Required resource folder/name. |
| `relative_path` | `TEXT` | Required path relative to resources root. |
| `resource_type` | `TEXT` | Required: `script`, `map`, `framework`, `library`, `unknown`. |
| `enabled_state` | `TEXT` | Required: `enabled`, `disabled`, `unknown`. |
| `startup_order` | `INTEGER` | Nullable. |
| `current_version_id` | `TEXT` | Nullable FK to `resource_versions`. |
| `git_repository_id` | `TEXT` | Nullable FK to `git_repositories`. |
| `created_at` | `TEXT` | Required UTC timestamp. |
| `updated_at` | `TEXT` | Required UTC timestamp. |

Keys and constraints: PK `resource_id`; unique `(project_id, resource_name)`; check `enabled_state`.
Indexes: `idx_resources_project_state(project_id, enabled_state)`, `idx_resources_startup(project_id, startup_order)`.
Lifecycle: retained while detected; missing/deleted states recorded through state changes.
Rationale: canonical inventory row for every project resource.

### `resource_versions`

| Column | Type | Notes |
| --- | --- | --- |
| `resource_version_id` | `TEXT` | Primary key. |
| `resource_id` | `TEXT` | Required FK to `resources`. |
| `version_label` | `TEXT` | Nullable semantic or source version. |
| `git_commit_sha` | `TEXT` | Nullable. |
| `source_ref` | `TEXT` | Nullable URL, local path, or marketplace id. |
| `content_hash` | `TEXT` | Nullable directory/file hash. |
| `manifest_json` | `JSON` | Nullable resource manifest snapshot. |
| `detected_at` | `TEXT` | Required UTC timestamp. |

Keys and constraints: PK `resource_version_id`; unique `(resource_id, content_hash)` when hash exists.
Indexes: `idx_resource_versions_resource_time(resource_id, detected_at)`.
Lifecycle: retained for rollback history; old versions may compact manifest JSON.
Rationale: supports version management independent of Git.

### `resource_dependencies`

| Column | Type | Notes |
| --- | --- | --- |
| `resource_dependency_id` | `TEXT` | Primary key. |
| `project_id` | `TEXT` | Required FK to `projects`. |
| `source_resource_id` | `TEXT` | Required FK to `resources`. |
| `target_resource_id` | `TEXT` | Nullable FK to `resources` if resolved. |
| `target_name` | `TEXT` | Required dependency name. |
| `dependency_type` | `TEXT` | Required: `requires`, `optional`, `conflicts`, `loads_after`. |
| `declared_in_path` | `TEXT` | Nullable local path reference. |
| `detected_at` | `TEXT` | Required UTC timestamp. |

Keys and constraints: PK `resource_dependency_id`; unique `(source_resource_id, target_name, dependency_type)`.
Indexes: `idx_resource_dependencies_project(project_id)`, `idx_resource_dependencies_target(target_resource_id)`.
Lifecycle: refreshed on dependency scan.
Rationale: powers dependency graph and startup-order validation.

### `resource_state_changes`

| Column | Type | Notes |
| --- | --- | --- |
| `resource_state_change_id` | `TEXT` | Primary key. |
| `resource_id` | `TEXT` | Required FK to `resources`. |
| `change_type` | `TEXT` | Required: `install`, `update`, `enable`, `disable`, `delete`, `rollback`. |
| `from_state` | `TEXT` | Nullable. |
| `to_state` | `TEXT` | Nullable. |
| `command_execution_id` | `TEXT` | Nullable FK to `command_executions`. |
| `audit_event_id` | `TEXT` | Nullable FK to `audit_events`. |
| `changed_at` | `TEXT` | Required UTC timestamp. |
| `details_json` | `JSON` | Nullable diff/undo metadata. |

Keys and constraints: PK `resource_state_change_id`; check `change_type`.
Indexes: `idx_resource_state_changes_resource_time(resource_id, changed_at)`.
Lifecycle: audit history; retain long-term or archive.
Rationale: makes resource automation transparent and reversible.

### `resource_health_snapshots`

| Column | Type | Notes |
| --- | --- | --- |
| `resource_health_snapshot_id` | `TEXT` | Primary key. |
| `resource_id` | `TEXT` | Required FK to `resources`. |
| `environment_id` | `TEXT` | Nullable FK to `environment_profiles`. |
| `health_status` | `TEXT` | Required: `healthy`, `warning`, `error`, `unknown`. |
| `server_fps` | `REAL` | Nullable. |
| `cpu_percent` | `REAL` | Nullable. |
| `memory_mb` | `REAL` | Nullable. |
| `sampled_at` | `TEXT` | Required UTC timestamp. |
| `details_json` | `JSON` | Nullable local health details. |

Keys and constraints: PK `resource_health_snapshot_id`.
Indexes: `idx_resource_health_resource_time(resource_id, sampled_at)`, `idx_resource_health_status(health_status)`.
Lifecycle: downsample or prune with monitoring retention.
Rationale: resource-specific health view separate from generic metrics.

### `resource_install_sources`

| Column | Type | Notes |
| --- | --- | --- |
| `resource_install_source_id` | `TEXT` | Primary key. |
| `resource_id` | `TEXT` | Required FK to `resources`. |
| `source_type` | `TEXT` | Required: `git`, `zip`, `local`, `plugin`, `manual`. |
| `source_uri` | `TEXT` | Nullable. |
| `plugin_id` | `TEXT` | Nullable FK to `plugin_registrations`. |
| `trusted_at` | `TEXT` | Nullable UTC timestamp. |
| `metadata_json` | `JSON` | Nullable provider-specific metadata. |

Keys and constraints: PK `resource_install_source_id`; unique `(resource_id, source_type, source_uri)`.
Indexes: `idx_resource_install_sources_type(source_type)`.
Lifecycle: retained for provenance and updates.
Rationale: supports safe updates and source trust decisions.

## Open Questions

- Whether resource manifest snapshots should move to `local_files` when large.
- Whether dependency scan history should be versioned or current-state only.

## Deviations

None.
