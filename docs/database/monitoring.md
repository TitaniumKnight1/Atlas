# Monitoring Schema

Feature traceability: CPU, memory, disk, network, server FPS, players, database health, resource health, historical graphs, alerts, and incident creation from monitoring failures.

## Tables

### `metric_sources`

| Column | Type | Notes |
| --- | --- | --- |
| `metric_source_id` | `TEXT` | Primary key. |
| `project_id` | `TEXT` | Required FK to `projects`. |
| `environment_id` | `TEXT` | Nullable FK to `environment_profiles`. |
| `source_type` | `TEXT` | Required: `process`, `resource`, `database`, `network`, `disk`, `plugin`. |
| `source_ref` | `TEXT` | Nullable process id, resource id, or plugin id. |
| `display_name` | `TEXT` | Required. |
| `is_enabled` | `INTEGER` | Boolean 0/1. |
| `metadata_json` | `JSON` | Nullable provider details. |

Keys and constraints: PK `metric_source_id`; unique `(project_id, source_type, source_ref)`.
Indexes: `idx_metric_sources_project_enabled(project_id, is_enabled)`.
Lifecycle: current source inventory.
Rationale: identifies where time-series metrics originate.

### `metric_series`

| Column | Type | Notes |
| --- | --- | --- |
| `metric_series_id` | `TEXT` | Primary key. |
| `metric_source_id` | `TEXT` | Required FK to `metric_sources`. |
| `metric_name` | `TEXT` | Required, e.g. `cpu_percent`, `server_fps`. |
| `unit` | `TEXT` | Required. |
| `value_type` | `TEXT` | Required: `gauge`, `counter`, `status`. |
| `retention_class` | `TEXT` | Required: `high`, `standard`, `long`. |
| `created_at` | `TEXT` | Required UTC timestamp. |

Keys and constraints: PK `metric_series_id`; unique `(metric_source_id, metric_name)`.
Indexes: `idx_metric_series_name(metric_name)`.
Lifecycle: retained while source exists; old unused series can be archived.
Rationale: separates series metadata from high-volume samples.

### `metric_samples`

| Column | Type | Notes |
| --- | --- | --- |
| `sample_id` | `TEXT` | Primary key. |
| `metric_series_id` | `TEXT` | Required FK to `metric_series`. |
| `sampled_at` | `TEXT` | Required UTC timestamp. |
| `value_real` | `REAL` | Nullable numeric value. |
| `value_text` | `TEXT` | Nullable status/text value. |
| `quality` | `TEXT` | Required: `ok`, `estimated`, `missing`. |

Keys and constraints: PK `sample_id`; unique `(metric_series_id, sampled_at)`.
Indexes: `idx_metric_samples_series_time(metric_series_id, sampled_at)`.
Lifecycle: high-volume; raw samples retained short-term, then rolled up and pruned.
Rationale: powers live and recent historical graphs.

### `metric_rollups`

| Column | Type | Notes |
| --- | --- | --- |
| `rollup_id` | `TEXT` | Primary key. |
| `metric_series_id` | `TEXT` | Required FK to `metric_series`. |
| `bucket_start` | `TEXT` | Required UTC timestamp. |
| `bucket_size_seconds` | `INTEGER` | Required. |
| `min_value` | `REAL` | Nullable. |
| `max_value` | `REAL` | Nullable. |
| `avg_value` | `REAL` | Nullable. |
| `sample_count` | `INTEGER` | Required. |

Keys and constraints: PK `rollup_id`; unique `(metric_series_id, bucket_start, bucket_size_seconds)`.
Indexes: `idx_metric_rollups_series_bucket(metric_series_id, bucket_size_seconds, bucket_start)`.
Lifecycle: retain longer than raw samples; coarser buckets retained longest.
Rationale: supports long-range charts without unbounded raw sample growth.

### `monitoring_alerts`

| Column | Type | Notes |
| --- | --- | --- |
| `monitoring_alert_id` | `TEXT` | Primary key. |
| `project_id` | `TEXT` | Required FK to `projects`. |
| `metric_series_id` | `TEXT` | Nullable FK to `metric_series`. |
| `name` | `TEXT` | Required. |
| `severity` | `TEXT` | Required. |
| `condition_json` | `JSON` | Required versioned condition. |
| `is_enabled` | `INTEGER` | Boolean 0/1. |
| `created_at` | `TEXT` | Required UTC timestamp. |
| `updated_at` | `TEXT` | Required UTC timestamp. |

Keys and constraints: PK `monitoring_alert_id`; unique `(project_id, name)`.
Indexes: `idx_monitoring_alerts_enabled(project_id, is_enabled)`.
Lifecycle: current alert definition; changes audited.
Rationale: bridges monitoring to incidents and automations.

### `monitoring_alert_events`

| Column | Type | Notes |
| --- | --- | --- |
| `alert_event_id` | `TEXT` | Primary key. |
| `monitoring_alert_id` | `TEXT` | Required FK to `monitoring_alerts`. |
| `project_id` | `TEXT` | Required FK to `projects`. |
| `status` | `TEXT` | Required: `triggered`, `resolved`, `suppressed`. |
| `triggered_at` | `TEXT` | Required UTC timestamp. |
| `resolved_at` | `TEXT` | Nullable UTC timestamp. |
| `incident_group_id` | `TEXT` | Nullable FK to `incident_groups`. |
| `details_json` | `JSON` | Nullable alert context. |

Keys and constraints: PK `alert_event_id`; check `status`.
Indexes: `idx_monitoring_alert_events_project_time(project_id, triggered_at)`, `idx_monitoring_alert_events_status(status)`.
Lifecycle: retain alert event summaries; details JSON compacted after retention window.
Rationale: tracks alert lifecycle and incident creation.

## Retention

Default intent: raw samples short-term, minute/hour/day rollups long-term. Resource-specific health snapshots should follow the same retention class as their underlying source.

## Open Questions

- Exact retention windows for raw samples and rollups.
- Whether status metrics should use `value_text` or normalized status tables if heavily queried.

## Deviations

None.
