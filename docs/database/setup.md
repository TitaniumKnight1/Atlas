# Setup Schema

Feature traceability: initial server setup, artifact downloads, txAdmin configuration, dependency validation, setup recipes, and preflight checks.

## Tables

### `artifact_versions`

| Column | Type | Notes |
| --- | --- | --- |
| `artifact_version_id` | `TEXT` | Primary key. |
| `platform` | `TEXT` | Required: `windows`, `linux`. |
| `channel` | `TEXT` | Required: `recommended`, `latest`, `optional`, `pinned`. |
| `build_number` | `TEXT` | Required. |
| `download_url` | `TEXT` | Nullable source URL. |
| `sha256` | `TEXT` | Nullable verification hash. |
| `released_at` | `TEXT` | Nullable UTC timestamp. |
| `discovered_at` | `TEXT` | Required UTC timestamp. |
| `metadata_json` | `JSON` | Optional source metadata. |

Keys and constraints: PK `artifact_version_id`; unique `(platform, build_number)`.
Indexes: `idx_artifact_versions_channel(platform, channel, released_at)`.
Lifecycle: retained as cache metadata; old rows compactable after no project references them.
Rationale: separates artifact discovery from per-project pins.

### `project_artifact_pins`

| Column | Type | Notes |
| --- | --- | --- |
| `artifact_pin_id` | `TEXT` | Primary key. |
| `project_id` | `TEXT` | Required FK to `projects`. |
| `environment_id` | `TEXT` | Nullable FK to `environment_profiles`. |
| `artifact_version_id` | `TEXT` | Nullable FK to `artifact_versions`. |
| `channel_preference` | `TEXT` | Required: `recommended`, `latest`, `pinned`. |
| `pinned_reason` | `TEXT` | Nullable. |
| `created_at` | `TEXT` | Required UTC timestamp. |
| `updated_at` | `TEXT` | Required UTC timestamp. |

Keys and constraints: PK `artifact_pin_id`; unique `(project_id, environment_id)`.
Indexes: `idx_project_artifact_pins_project(project_id)`.
Lifecycle: current state; changes audited.
Rationale: supports environment-specific artifact policy.

### `setup_recipes`

| Column | Type | Notes |
| --- | --- | --- |
| `setup_recipe_id` | `TEXT` | Primary key. |
| `recipe_slug` | `TEXT` | Required unique slug. |
| `display_name` | `TEXT` | Required. |
| `source_type` | `TEXT` | Required: `builtin`, `plugin`, `local`. |
| `source_ref` | `TEXT` | Nullable plugin id or path. |
| `recipe_version` | `TEXT` | Required. |
| `definition_json` | `JSON` | Required versioned recipe payload. |
| `created_at` | `TEXT` | Required UTC timestamp. |
| `updated_at` | `TEXT` | Required UTC timestamp. |

Keys and constraints: PK `setup_recipe_id`; unique `(recipe_slug, recipe_version)`.
Indexes: `idx_setup_recipes_source(source_type, source_ref)`.
Lifecycle: retained while referenced by setup runs.
Rationale: recipe shape is plugin-extensible, so JSON is appropriate.

### `setup_runs`

| Column | Type | Notes |
| --- | --- | --- |
| `setup_run_id` | `TEXT` | Primary key. |
| `project_id` | `TEXT` | Required FK to `projects`. |
| `environment_id` | `TEXT` | Nullable FK to `environment_profiles`. |
| `setup_recipe_id` | `TEXT` | Nullable FK to `setup_recipes`. |
| `status` | `TEXT` | Required: `planned`, `running`, `succeeded`, `failed`, `cancelled`. |
| `dry_run` | `INTEGER` | Boolean 0/1. |
| `started_at` | `TEXT` | Nullable UTC timestamp. |
| `finished_at` | `TEXT` | Nullable UTC timestamp. |
| `summary_json` | `JSON` | Nullable run summary. |

Keys and constraints: PK `setup_run_id`; check `status`; check `dry_run in (0,1)`.
Indexes: `idx_setup_runs_project_time(project_id, started_at)`, `idx_setup_runs_status(status)`.
Lifecycle: retained as project history; old detailed steps can be compacted after audit retention window.
Rationale: records setup workflow state and result.

### `setup_run_steps`

| Column | Type | Notes |
| --- | --- | --- |
| `setup_step_id` | `TEXT` | Primary key. |
| `setup_run_id` | `TEXT` | Required FK to `setup_runs`. |
| `step_order` | `INTEGER` | Required. |
| `step_key` | `TEXT` | Required stable recipe step key. |
| `status` | `TEXT` | Required. |
| `started_at` | `TEXT` | Nullable UTC timestamp. |
| `finished_at` | `TEXT` | Nullable UTC timestamp. |
| `details_json` | `JSON` | Nullable details, paths, warnings. |

Keys and constraints: PK `setup_step_id`; unique `(setup_run_id, step_order)`.
Indexes: `idx_setup_run_steps_run_status(setup_run_id, status)`.
Lifecycle: detailed retention follows setup run policy.
Rationale: supports transparent setup progress and troubleshooting.

### `dependency_checks`

| Column | Type | Notes |
| --- | --- | --- |
| `dependency_check_id` | `TEXT` | Primary key. |
| `setup_run_id` | `TEXT` | Nullable FK to `setup_runs`. |
| `project_id` | `TEXT` | Required FK to `projects`. |
| `check_key` | `TEXT` | Required. |
| `category` | `TEXT` | Required: `binary`, `database`, `config`, `network`, `filesystem`. |
| `status` | `TEXT` | Required: `pass`, `warning`, `fail`, `skipped`. |
| `message` | `TEXT` | Nullable. |
| `details_json` | `JSON` | Nullable. |
| `checked_at` | `TEXT` | Required UTC timestamp. |

Keys and constraints: PK `dependency_check_id`.
Indexes: `idx_dependency_checks_project_time(project_id, checked_at)`, `idx_dependency_checks_status(status)`.
Lifecycle: retain recent checks; summarize older checks in audit history.
Rationale: supports preflight validation before launch.

### `txadmin_instances`

| Column | Type | Notes |
| --- | --- | --- |
| `txadmin_instance_id` | `TEXT` | Primary key. |
| `project_id` | `TEXT` | Required FK to `projects`. |
| `txdata_path_id` | `TEXT` | Nullable FK to `project_paths`. |
| `host` | `TEXT` | Nullable, usually loopback. |
| `port` | `INTEGER` | Nullable. |
| `detected_version` | `TEXT` | Nullable. |
| `last_seen_at` | `TEXT` | Nullable UTC timestamp. |
| `metadata_json` | `JSON` | Nullable local detection data. |

Keys and constraints: PK `txadmin_instance_id`; unique `(project_id, txdata_path_id)`.
Indexes: `idx_txadmin_instances_project(project_id)`.
Lifecycle: refreshed on project scan; stale instances marked via metadata.
Rationale: models txAdmin integration without treating txAdmin as a normal resource.

## Open Questions

- Whether artifact download cache files should be tracked here or in `local_files`.
- How much txAdmin API state should be persisted versus read on demand.

## Deviations

None.
