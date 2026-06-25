# Telemetry Schema

Feature traceability: optional Atlas application telemetry, user-visible telemetry controls, SDK-side sanitization, rejection of FiveM project data, and delivery audit records.

This schema is for **Atlas application telemetry only**. FiveM resources, logs, configs, databases, player data, identifiers, and project secrets are never valid telemetry payloads.

## Tables

### `telemetry_preferences`

| Column | Type | Notes |
| --- | --- | --- |
| `telemetry_preference_id` | `TEXT` | Primary key. |
| `project_id` | `TEXT` | Nullable FK to `projects`; null means global. |
| `telemetry_enabled` | `INTEGER` | Boolean 0/1. |
| `crash_reporting_enabled` | `INTEGER` | Boolean 0/1. |
| `plugin_telemetry_enabled` | `INTEGER` | Boolean 0/1. |
| `last_prompted_at` | `TEXT` | Nullable UTC timestamp. |
| `updated_at` | `TEXT` | Required UTC timestamp. |
| `updated_by` | `TEXT` | Nullable actor id. |

Keys and constraints: PK `telemetry_preference_id`; unique `project_id`; check booleans.
Indexes: `idx_telemetry_preferences_project(project_id)`.
Lifecycle: current preferences; changes audited.
Rationale: supports disable/opt-in controls globally and optionally per project.

### `telemetry_queue`

| Column | Type | Notes |
| --- | --- | --- |
| `telemetry_event_id` | `TEXT` | Primary key. |
| `event_type` | `TEXT` | Required Atlas event name. |
| `subsystem` | `TEXT` | Required: `frontend`, `backend`, `tauri`, `plugin`, `startup`. |
| `severity` | `TEXT` | Required. |
| `event_payload_json` | `JSON` | Required sanitized/minimal payload candidate. |
| `status` | `TEXT` | Required: `queued`, `blocked`, `delivered`, `failed`, `expired`. |
| `created_at` | `TEXT` | Required UTC timestamp. |
| `next_attempt_at` | `TEXT` | Nullable UTC timestamp. |
| `expires_at` | `TEXT` | Required UTC timestamp. |

Keys and constraints: PK `telemetry_event_id`; check `status`.
Indexes: `idx_telemetry_queue_status_next(status, next_attempt_at)`, `idx_telemetry_queue_expires(expires_at)`.
Lifecycle: delivered/expired payloads pruned quickly; summaries remain in sanitization/delivery records.
Rationale: durable local queue that can respect offline and opt-out state.

### `telemetry_sanitization_results`

| Column | Type | Notes |
| --- | --- | --- |
| `sanitization_result_id` | `TEXT` | Primary key. |
| `telemetry_event_id` | `TEXT` | Nullable FK to `telemetry_queue`. |
| `telemetry_rejection_id` | `TEXT` | Nullable FK to `telemetry_rejections`. |
| `result_state` | `TEXT` | Required: `allowed`, `redacted`, `rejected`. |
| `rules_applied_json` | `JSON` | Required list of sanitizer rules. |
| `redaction_count` | `INTEGER` | Required. |
| `created_at` | `TEXT` | Required UTC timestamp. |

Keys and constraints: PK `sanitization_result_id`; at least one of event or rejection references must exist.
Indexes: `idx_telemetry_sanitization_event(telemetry_event_id)`, `idx_telemetry_sanitization_state(result_state, created_at)`.
Lifecycle: retain longer than raw queue payloads for auditability.
Rationale: proves SDK-side sanitization happened before upload.

### `telemetry_rejections`

| Column | Type | Notes |
| --- | --- | --- |
| `telemetry_rejection_id` | `TEXT` | Primary key. |
| `event_type` | `TEXT` | Required. |
| `rejection_reason` | `TEXT` | Required: `disabled`, `contains_project_data`, `contains_secret`, `contains_identifier`, `oversized`, `policy`. |
| `subsystem` | `TEXT` | Required. |
| `fingerprint` | `TEXT` | Nullable local rejection fingerprint. |
| `created_at` | `TEXT` | Required UTC timestamp. |
| `summary_json` | `JSON` | Nullable non-sensitive summary. |

Keys and constraints: PK `telemetry_rejection_id`; check `rejection_reason`.
Indexes: `idx_telemetry_rejections_reason_time(rejection_reason, created_at)`.
Lifecycle: retain summaries; never retain rejected raw FiveM data.
Rationale: auditable privacy boundary without leaking the blocked payload.

### `telemetry_delivery_attempts`

| Column | Type | Notes |
| --- | --- | --- |
| `delivery_attempt_id` | `TEXT` | Primary key. |
| `telemetry_event_id` | `TEXT` | Required FK to `telemetry_queue`. |
| `attempt_number` | `INTEGER` | Required. |
| `status` | `TEXT` | Required: `succeeded`, `failed`, `skipped`. |
| `attempted_at` | `TEXT` | Required UTC timestamp. |
| `http_status` | `INTEGER` | Nullable. |
| `error_summary` | `TEXT` | Nullable. |

Keys and constraints: PK `delivery_attempt_id`; unique `(telemetry_event_id, attempt_number)`.
Indexes: `idx_telemetry_delivery_event(telemetry_event_id)`, `idx_telemetry_delivery_status_time(status, attempted_at)`.
Lifecycle: retain attempt summaries after queue payload pruning.
Rationale: transparent delivery behavior without storing sensitive payloads.

## Retention

Telemetry payloads are short-lived. Delivered events are removed after a short audit window. Rejections retain non-sensitive reason summaries longer than queue payloads. Any rejected payload containing FiveM project data is never stored.

## Open Questions

- Whether telemetry defaults to disabled or first-run opt-in.
- Whether users can preview the exact sanitized event before sending in all cases.

## Deviations

None.
