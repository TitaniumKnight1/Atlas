# Monitoring API Contract

Responsibility: metric sources, series, samples, rollups, alerts, alert events, health summaries, and streaming metrics.

## Commands

| Name | Inputs | Outputs | Errors | Behavior | PRD trace |
| --- | --- | --- | --- | --- | --- |
| `RegisterMetricSource` | `project_id`, source type/ref, metadata | metric source id | `ProjectScopeViolation`, `ValidationFailed` | Usually internal or plugin-mediated. | Monitoring dashboard |
| `IngestMetricSample` | `project_id`, series id, timestamp, value, quality | sample id or accepted count | `ProjectScopeViolation`, `ValidationFailed` | High-volume; short write transaction. | Historical graphs |
| `ComputeMetricRollups` | `project_id`, series ids, time bucket | rollup summary | `ProjectScopeViolation`, `ExternalAdapterFailed` | Scheduled/background operation. | Historical graphs |
| `CreateMonitoringAlert` | `project_id`, metric/condition/severity | alert id | `ValidationFailed`, `ProjectScopeViolation` | Audited write. | Alerts creating incidents |
| `UpdateMonitoringAlert` | `project_id`, alert id, patch | updated alert | `NotFound`, `Conflict` | Audited write. | Monitoring alerts |
| `RecordAlertEvent` | `project_id`, alert id, status, details | alert event id | `NotFound`, `ValidationFailed` | May publish incident-triggering event. | Alerts |

## Queries

| Name | Inputs | Outputs | Errors | PRD trace |
| --- | --- | --- | --- | --- |
| `ListMetricSources` | `project_id`, filters | sources | `ProjectScopeViolation` | Dashboard sources |
| `ListMetricSeries` | `project_id`, source filters | series | `ProjectScopeViolation` | Dashboard charts |
| `QueryMetricSamples` | `project_id`, series ids, time range, resolution | sample or rollup points | `ValidationFailed` | Historical graphs |
| `GetProjectHealthSummary` | `project_id`, environment id | health summary | `ProjectScopeViolation` | Monitoring dashboard |
| `ListMonitoringAlerts` | `project_id`, enabled/status filters | alerts | `ProjectScopeViolation` | Alert config |
| `ListAlertEvents` | `project_id`, filters, pagination | alert event history | `ProjectScopeViolation` | Alert history |

## Published Events

| Event | Payload summary | Consumers |
| --- | --- | --- |
| `MetricSourceRegistered` | `project_id`, source id, type | Audit |
| `MetricThresholdBreached` | `project_id`, metric, value, severity | Incident, Automation |
| `MonitoringAlertTriggered` | `project_id`, alert id, severity | Incident, Automation, Audit |
| `MonitoringAlertResolved` | `project_id`, alert id | Automation, Audit |
| `ResourceHealthChanged` | `project_id`, resource id, health | Resources, Incident |

## Subscribed Events

| Source event | Reaction | Reason |
| --- | --- | --- |
| `ProjectImported` | Register default metric sources | Populate dashboard. |
| `SetupRunCompleted` | Refresh process/resource sources | New server process may exist. |
| `ResourceInventoryChanged` | Update resource metric sources | Keep resource health aligned. |
| `ServerProcessCrashed` | Emit alert/health event | Incident pipeline. |
| `PluginCapabilityDenied` | Disable plugin metric collector if needed | Plugin safety. |

## Required Domain Ports

| Port | Purpose | Project scoping | Adapter target |
| --- | --- | --- | --- |
| `MonitoringRepositoryPort` | Persist metric sources, samples, rollups, alerts | Requires `project_id` | `persistence` |
| `ProcessMetricsPort` | Collect CPU/memory/process metrics | Requires `project_id`, process refs | `process` |
| `FilesystemMetricsPort` | Collect disk/path metrics | Requires project path allowlist | `filesystem` |
| `PluginMetricsPort` | Receive approved plugin collectors | Requires capability grant and `project_id` | `plugin` |
| `IncidentCreationPort` | Request incident from critical alert | Event or application call to Incident | application |

## API Surface

| Intent | Structural request | Structural response |
| --- | --- | --- |
| `GET /api/v1/projects/{project_id}/monitoring/sources` | filters | source list |
| `GET /api/v1/projects/{project_id}/monitoring/series` | filters | series list |
| `GET /api/v1/projects/{project_id}/monitoring/samples` | series ids, time range, resolution | chart points |
| `GET /api/v1/projects/{project_id}/monitoring/health` | environment | health summary |
| `GET /api/v1/projects/{project_id}/monitoring/alerts` | filters | alerts |
| `POST /api/v1/projects/{project_id}/monitoring/alerts` | alert definition | alert id |
| `GET /api/v1/projects/{project_id}/streams/metrics` | source/series filters | metric stream topic |

## Open Questions

- Whether high-volume sample ingestion should be internal-only or available to approved plugins through API.

## Deviations

None.
