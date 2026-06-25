# Telemetry API Contract

Responsibility: Atlas application telemetry preferences, sanitizer checks, queueing, rejection records, delivery attempts, and privacy-preserving audit. This context never accepts FiveM project data as telemetry.

## Commands

| Name | Inputs | Outputs | Errors | Behavior | PRD trace |
| --- | --- | --- | --- | --- | --- |
| `UpdateTelemetryPreferences` | optional `project_id`, preference patch | updated preferences | `ValidationFailed`, `ProjectScopeViolation` | Audited privacy setting. | Telemetry controls |
| `EvaluateTelemetryEvent` | Atlas event candidate, subsystem, optional plugin id | sanitizer result | `TelemetryRejected`, `ValidationFailed` | SDK-side sanitizer contract. | Sanitization |
| `QueueTelemetryEvent` | sanitized Atlas event, idempotency key | telemetry event id | `TelemetryRejected`, `PermissionDenied` | Stores only allowed payload. | Optional Sentry integration |
| `RejectTelemetryEvent` | event type, rejection reason, non-sensitive summary | rejection id | `ValidationFailed` | Never stores raw rejected project data. | Privacy-first telemetry |
| `RecordTelemetryDeliveryAttempt` | telemetry event id, attempt status | attempt id | `NotFound`, `ExternalAdapterFailed` | Delivery audit only. | Application telemetry |
| `PruneTelemetryQueue` | retention policy | prune summary | `ValidationFailed` | Removes delivered/expired payloads. | Retention |

## Queries

| Name | Inputs | Outputs | Errors | PRD trace |
| --- | --- | --- | --- | --- |
| `GetTelemetryPreferences` | optional `project_id` | effective preferences | `ProjectScopeViolation` | Disable telemetry |
| `ListTelemetryQueue` | status filters, pagination | queued event summaries | none | Telemetry transparency |
| `ListTelemetryRejections` | reason/time filters | rejection summaries | none | Sanitization audit |
| `GetSanitizationResult` | event or rejection id | sanitizer rules and result | `NotFound` | Privacy audit |
| `ListDeliveryAttempts` | event id or status filters | delivery attempts | `NotFound` | Delivery audit |

## Published Events

| Event | Payload summary | Consumers |
| --- | --- | --- |
| `TelemetryPreferencesUpdated` | optional `project_id`, changed keys | Audit |
| `TelemetryEventQueued` | telemetry event id, subsystem, severity | Audit |
| `TelemetryEventDelivered` | event id, attempt number | Audit |
| `TelemetryRejected` | reason, subsystem, optional `project_id` if known | Project, Plugin, Incident, Audit |
| `TelemetryQueuePruned` | counts by status | Audit |

## Subscribed Events

| Source event | Reaction | Reason |
| --- | --- | --- |
| `PluginFailureRecorded` | Evaluate Atlas plugin failure telemetry | Atlas app telemetry only. |
| `PluginCapabilityDenied` | Optionally record non-sensitive Atlas security event | Plugin trust observability. |
| `WorkspaceTrustChanged` | Re-evaluate project-scoped plugin telemetry permissions | Privacy controls. |
| `IncidentMarkdownExported` | Do nothing with export body; optional non-sensitive app event only | Prevent FiveM data upload. |

## Required Domain Ports

| Port | Purpose | Project scoping | Adapter target |
| --- | --- | --- | --- |
| `TelemetryRepositoryPort` | Persist preferences, queue, sanitizer results, rejections, attempts | Optional `project_id`; global allowed only for app settings | `persistence` |
| `TelemetrySanitizerPort` | Remove/reject secrets, IPs, identifiers, project data | Rejects any FiveM payload; optional project context for policy | `telemetry` |
| `TelemetryDeliveryPort` | Send sanitized Atlas event to configured Sentry project | Only allowed sanitized payloads | `telemetry` |
| `PluginTelemetryPolicyPort` | Check plugin telemetry capability | Requires plugin grant and optional `project_id` | `plugin` |
| `AuditPort` | Record preference and rejection outcomes | Includes `project_id` only when scoped | `persistence` |

## API Surface

| Intent | Structural request | Structural response |
| --- | --- | --- |
| `GET /api/v1/telemetry/preferences` | optional project id | effective preferences |
| `PATCH /api/v1/telemetry/preferences` | preference patch | updated preferences |
| `POST /api/v1/telemetry/evaluate` | Atlas event candidate | sanitizer result |
| `POST /api/v1/telemetry/queue` | sanitized event | queue id |
| `GET /api/v1/telemetry/rejections` | filters | rejection summaries |
| `GET /api/v1/telemetry/delivery-attempts` | filters | attempt summaries |

## Open Questions

- Whether users can preview every sanitized payload before delivery or only sampled recent payloads.

## Deviations

None.
