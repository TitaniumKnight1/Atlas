# Incident API Contract

Responsibility: local incident ingestion, fingerprinting, grouping, occurrence append, breadcrumbs, context snapshots, stack traces, related groups, rules, notes, compare, and Markdown export.

## M7 slice ownership

| Slice | Scope | M7a status |
| --- | --- | --- |
| **M7a** | Crash-triggered capture, occurrence write, environment snapshot assembly, breadcrumbs, local queries, `IncidentCaptured` event | **Implemented** |
| **M7b** | Fingerprinting, deduplication, grouping, timeline, related groups, compare | **Implemented** |
| **M7c** | Markdown export, export sanitization, export history | **Implemented** |

M7a implements capture and snapshot assembly. M7b implements fingerprinting, deduplication, grouping, group timeline, related groups, compare, and placeholder migration. M7c implements the single always-sanitized Markdown export path and export history.

## Privacy boundary

Incident data is **local-only project data** and must never flow to telemetry (ADR-0005, `telemetry-and-privacy.md`). M7a:

- Persists incidents only in local SQLite project storage.
- Creates **no** telemetry enqueue path and **no** export/outbound path.
- Redacts git remotes in environment snapshots (M4b `redact_remote_url`).
- Includes config secret **finding metadata** only (M4a); never widens secret values into snapshots.
- Emits `IncidentCaptured` on the local in-process bus only (no SSE incidents topic in M7a).

M7c export is the **only sanctioned deliberate outbound artifact**. It always passes through the export sanitizer; there is no raw export bypass. Incident capture/grouping data remains local-only until the user explicitly exports and copies Markdown manually.

## Commands

| Name | Inputs | Outputs | Errors | Behavior | PRD trace |
| --- | --- | --- | --- | --- | --- |
| `CaptureServerCrash` | `project_id`, `process_run_id`, `exit_code` | group id, occurrence id, fingerprint | `NotFound`, `ProjectScopeViolation` | M7a capture + M7b fingerprint/dedupe; auto-triggered on `ServerCrashed`. No preview/undo. | Local crash capture |
| `MigrateIncidentGrouping` | `project_id` | merge/move/delete counts | `ProjectScopeViolation` | M7b: idempotent backfill of M7a placeholder groups. | Placeholder transition |
| `AppendIncidentOccurrence` | `project_id`, group id, occurrence payload | occurrence id | `NotFound`, `ProjectScopeViolation` | Adds occurrence to existing group. | Deduplication/history |
| `AttachBreadcrumbs` | `project_id`, occurrence id, breadcrumbs | accepted count | `NotFound`, `ValidationFailed` | Local-only timeline write. | Timeline/breadcrumbs |
| `AttachIncidentContextSnapshot` | `project_id`, occurrence id, context type, snapshot/local file ref | context snapshot id | `NotFound`, `ValidationFailed` | Stores local debugging context. | Environment/config/log snapshots |
| `RecordStackTrace` | `project_id`, occurrence id, stack trace/frames | stack trace id | `NotFound`, `ValidationFailed` | Supports grouping/export. | Stack traces |
| `RelateIncidentGroups` | `project_id`, source group, target group, relation type | relation id | `NotFound`, `Conflict` | User/system related incidents. | Related incidents |
| `UpdateIncidentGroupStatus` | `project_id`, group id, status, reason | group summary | `NotFound`, `Conflict` | Audited triage action. | Incident history |
| `CreateIncidentGroupRule` | `project_id`, rule type, match/action | rule id | `ValidationFailed` | Local grouping customization. | Fingerprinting rules |
| `AddIncidentNote` | `project_id`, group id, body | note id | `NotFound` | Local triage notes. | Incident history |
| `ExportIncidentMarkdown` | `project_id`, group id, optional occurrence id, redaction profile | export id, sanitized markdown, redaction summary | `NotFound` | M7c: assemble → always sanitize → return Markdown; manual copy only; no AI API. | AI-ready Markdown export |

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
| `IncidentCaptured` | `project_id`, group id, occurrence id, severity, category | Audit (local bus only in M7a) |
| `NewIncidentGroupCreated` | `project_id`, group id, occurrence id, fingerprint | Audit |
| `OccurrenceDeduplicated` | `project_id`, group id, occurrence id, fingerprint | Audit |
| `IncidentGrouped` | `project_id`, group id, fingerprint, occurrence count | Audit |
| `IncidentCreated` | `project_id`, group id, occurrence id, severity | Automation, Monitoring, Audit |
| `IncidentOccurrenceAppended` | `project_id`, group id, occurrence id | Automation, Audit |
| `IncidentStatusChanged` | `project_id`, group id, status | Automation, Audit |
| `IncidentMarkdownExported` | `project_id`, group id, export id | Audit (local bus only) |
| `IncidentGroupingRuleChanged` | `project_id`, rule id | Audit |

## Subscribed Events

| Source event | Reaction | Reason |
| --- | --- | --- |
| `ServerCrashed` | Trigger M7a `CaptureServerCrash` via event subscriber | M3b unexpected process exit. |
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
| `POST /api/v1/projects/{project_id}/incidents/capture/crash` | `process_run_id`, `exit_code` | group/occurrence refs (M7a explicit capture) |
| `GET /api/v1/projects/{project_id}/incidents/{group_id}` | ids | incident detail |
| `GET /api/v1/projects/{project_id}/incidents/occurrences/{occurrence_id}/timeline` | occurrence id | breadcrumbs, context snapshots, stack trace (M7a) |
| `POST /api/v1/projects/{project_id}/incidents/ingest` | incident payload | group/occurrence refs (M7b+) |
| `GET /api/v1/projects/{project_id}/incidents/{group_id}/timeline` | occurrence/time filters | group occurrence timeline (M7b) |
| `POST /api/v1/projects/{project_id}/incidents/compare` | group ids | comparison report (M7b) |
| `POST /api/v1/projects/{project_id}/incidents/migrate-grouping` | ids | placeholder migration stats (M7b) |
| `POST /api/v1/projects/{project_id}/incidents/{group_id}/exports/markdown` | optional occurrence id, redaction profile | sanitized markdown + export record (M7c) |
| `GET /api/v1/projects/{project_id}/incidents/{group_id}/exports` | group id | export history metadata (M7c) |
| `GET /api/v1/projects/{project_id}/streams/incidents` | filters | incident stream topic |

## Open Questions

- Whether incident ingestion API is internal-only or exposed to approved plugins.

## Deviations

- Export sanitizer reuses M2 `SECRET_RULES` / `IDENTIFIER_RULES` with redact-in-place policy (not telemetry fail-closed). Status is **audited + passing as of current release** (ADR-0005 family, ADR-0019).
- M7b automatic related-group linking only for shared `resource_hint` with different fingerprints. User rules, notes, and manual relate APIs remain deferred.
- `incident_group_rules` and `incident_notes` tables exist for future use; no rule/note API yet.
- `incident_stack_frames` table exists; no frame rows until structured stack traces are available.
- Ingest, status triage, and incidents SSE stream remain deferred.
