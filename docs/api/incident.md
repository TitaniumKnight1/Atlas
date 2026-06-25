# Incident API Contract

Responsibility: local incident ingestion, fingerprinting, grouping, occurrence append, breadcrumbs, context snapshots, stack traces, related groups, rules, notes, compare, and Markdown export.

## Commands

| Name | Inputs | Outputs | Errors | Behavior | PRD trace |
| --- | --- | --- | --- | --- | --- |
| `IngestIncident` | `project_id`, source, severity, category, message, context refs, `idempotency_key` | incident group id, occurrence id | `ValidationFailed`, `ProjectScopeViolation` | Normalizes, fingerprints, dedupes. | Local incident capture |
| `AppendIncidentOccurrence` | `project_id`, group id, occurrence payload | occurrence id | `NotFound`, `ProjectScopeViolation` | Adds occurrence to existing group. | Deduplication/history |
| `AttachBreadcrumbs` | `project_id`, occurrence id, breadcrumbs | accepted count | `NotFound`, `ValidationFailed` | Local-only timeline write. | Timeline/breadcrumbs |
| `AttachIncidentContextSnapshot` | `project_id`, occurrence id, context type, snapshot/local file ref | context snapshot id | `NotFound`, `ValidationFailed` | Stores local debugging context. | Environment/config/log snapshots |
| `RecordStackTrace` | `project_id`, occurrence id, stack trace/frames | stack trace id | `NotFound`, `ValidationFailed` | Supports grouping/export. | Stack traces |
| `RelateIncidentGroups` | `project_id`, source group, target group, relation type | relation id | `NotFound`, `Conflict` | User/system related incidents. | Related incidents |
| `UpdateIncidentGroupStatus` | `project_id`, group id, status, reason | group summary | `NotFound`, `Conflict` | Audited triage action. | Incident history |
| `CreateIncidentGroupRule` | `project_id`, rule type, match/action | rule id | `ValidationFailed` | Local grouping customization. | Fingerprinting rules |
| `AddIncidentNote` | `project_id`, group id, body | note id | `NotFound` | Local triage notes. | Incident history |
| `ExportIncidentMarkdown` | `project_id`, group/occurrence id, redaction profile | export id, local file ref/warnings | `NotFound`, `PermissionDenied` | Manual export only; no AI API. | AI-ready Markdown export |

## Queries

| Name | Inputs | Outputs | Errors | PRD trace |
| --- | --- | --- | --- | --- |
| `ListIncidentGroups` | `project_id`, status/severity/category filters, pagination | group summaries | `ProjectScopeViolation` | Incident history |
| `GetIncidentGroup` | `project_id`, group id | group detail | `NotFound` | Incident detail |
| `ListIncidentOccurrences` | `project_id`, group id, time range | occurrences | `NotFound` | Incident timeline |
| `GetIncidentTimeline` | `project_id`, occurrence id | breadcrumbs/context/stack refs | `NotFound` | Timeline |
| `CompareIncidents` | `project_id`, group ids or occurrence ids | comparison report | `NotFound`, `ValidationFailed` | Compare incidents |
| `ListIncidentExports` | `project_id`, group id | export history | `NotFound` | Markdown export history |
| `ListIncidentGroupRules` | `project_id`, enabled filter | rules | `ProjectScopeViolation` | Fingerprinting rules |

## Published Events

| Event | Payload summary | Consumers |
| --- | --- | --- |
| `IncidentCreated` | `project_id`, group id, occurrence id, severity | Automation, Monitoring, Audit |
| `IncidentOccurrenceAppended` | `project_id`, group id, occurrence id | Automation, Audit |
| `IncidentStatusChanged` | `project_id`, group id, status | Automation, Audit |
| `IncidentMarkdownExported` | `project_id`, group id, export id | Audit |
| `IncidentGroupingRuleChanged` | `project_id`, rule id | Audit |

## Subscribed Events

| Source event | Reaction | Reason |
| --- | --- | --- |
| `DependencyCheckFailed` | Create validation/setup incident if severe | Setup failures. |
| `ConfigValidationFailed` | Create or update validation incident | Config errors. |
| `BackupFailed` | Create backup incident | Backup failures. |
| `MonitoringAlertTriggered` | Create monitoring incident | Operational health. |
| `AutomationRunFailed` | Create automation incident | Workflow failure. |
| `GitOperationCompleted` | Attach recent Git context to timeline | Debug context. |
| `ResourceUpdated` | Attach resource change breadcrumb | Debug context. |
| `TelemetryRejected` | Create Atlas privacy/system incident only when user-visible | App reliability. |

## Required Domain Ports

| Port | Purpose | Project scoping | Adapter target |
| --- | --- | --- | --- |
| `IncidentRepositoryPort` | Persist groups, occurrences, fingerprints, timeline, exports | Requires `project_id` | `persistence` |
| `FingerprintingPort` | Generate stable local fingerprints | Requires project/category/source context | domain service |
| `IncidentContextPort` | Collect logs, config excerpts, resources, runtime snapshots | Requires project path allowlist | `filesystem`, `process`, application contracts |
| `MarkdownExportPort` | Render and write local Markdown export | Requires explicit user action and `project_id` | `filesystem` |
| `RedactionPort` | Evaluate export redaction warnings | Requires `project_id`, redaction profile | domain service |
| `AuditPort` | Record incident triage/export actions | Includes `project_id` | `persistence` |

## API Surface

| Intent | Structural request | Structural response |
| --- | --- | --- |
| `GET /api/v1/projects/{project_id}/incidents` | filters, pagination | incident groups |
| `POST /api/v1/projects/{project_id}/incidents/ingest` | incident payload | group/occurrence refs |
| `GET /api/v1/projects/{project_id}/incidents/{group_id}` | ids | incident detail |
| `GET /api/v1/projects/{project_id}/incidents/{group_id}/timeline` | occurrence/time filters | timeline |
| `POST /api/v1/projects/{project_id}/incidents/{group_id}/status` | status/reason | group summary |
| `POST /api/v1/projects/{project_id}/incidents/compare` | group/occurrence ids | comparison report |
| `POST /api/v1/projects/{project_id}/incidents/{group_id}/exports/markdown` | redaction profile | export ref/warnings |
| `GET /api/v1/projects/{project_id}/streams/incidents` | filters | incident stream topic |

## Open Questions

- Whether incident ingestion API is internal-only or exposed to approved plugins.

## Deviations

None.
