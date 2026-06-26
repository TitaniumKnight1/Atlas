# Monitoring API Contract

Responsibility: metric sources, series, samples, rollups, alerts, alert events, health summaries, and streaming metrics.

## Privacy Boundary

FiveM server and system metrics (CPU, memory, disk, process state, resource health counts) are **local-only project data**. They are stored in SQLite, queried via loopback API, and streamed on the SSE `metrics` topic. They **never** enter the M2 telemetry pipeline.

## M6a / M6b / M6c Scope

| Slice | Tables / surface | Status |
| --- | --- | --- |
| **M6a** | `metric_sources`, `metric_series`, `metric_samples`; collection start/stop; `GET .../monitoring/sources`, `latest`, `samples`; live `MetricSample` on `metrics` topic | Implemented |
| **M6b** | `metric_rollups`, `metric_rollup_watermarks`, retention/downsampling, time-window and aggregated queries | Implemented |
| **M6c** | `monitoring_alerts`, `monitoring_alert_events`; alert-rule CRUD; evaluation; `AlertFired`/`AlertResolved` on `alerts` topic | Implemented |

## Commands (M6a subset)

| Name | Inputs | Outputs | Errors | Behavior | PRD trace |
| --- | --- | --- | --- | --- | --- |
| `StartMetricCollection` | `project_id`, optional interval | collection status | `ProjectScopeViolation`, `NotFound` | Starts in-process collector loop; not a command/undo module. | Monitoring dashboard |
| `StopMetricCollection` | `project_id` | collection status | `ProjectScopeViolation` | Stops collector and flushes pending sample batch. | Monitoring dashboard |

Commands below are **M6b/M6c** — not implemented in M6a:

| Name | Slice |
| --- | --- |
| `RegisterMetricSource` | M6a internal via collector seam |
| `IngestMetricSample` | M6a internal via collector batch flush |
| `ComputeMetricRollups` | M6b — internal via rollup scheduler / `POST .../rollup/run` |
| `CreateMonitoringAlert` | M6c — `POST .../monitoring/alerts` |
| `UpdateMonitoringAlert` | M6c — `PATCH .../monitoring/alerts/{id}` |
| `RecordAlertEvent` | M6c internal on state transition |

## Queries (M6a subset)

| Name | Inputs | Outputs | Errors | PRD trace |
| --- | --- | --- | --- | --- |
| `ListMetricSources` | `project_id`, filters | sources | `ProjectScopeViolation` | Dashboard sources |
| `QueryLatestMetrics` | `project_id` | latest sample per series | `ProjectScopeViolation` | Dashboard gauges |
| `QueryRecentMetricSamples` | `project_id`, limit | recent raw samples | `ProjectScopeViolation` | Live/historical preview |

Queries below are **M6b/M6c** — deferred:

| Name | Slice |
| --- | --- |
| `ListMetricSeries` | M6b — `GET .../monitoring/series` |
| `QueryMetricSamples` (time range, resolution) | M6b — `GET .../monitoring/history` |
| `GetProjectHealthSummary` | M6c — deferred (dashboard slice) |
| `ListMonitoringAlerts` | M6c — `GET .../monitoring/alerts` |
| `ListAlertEvents` | M6c — `GET .../monitoring/alert-events` |

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

## API Surface (M6a + M6b + M6c)

| Intent | Structural request | Structural response |
| --- | --- | --- |
| `GET /api/v1/projects/{project_id}/monitoring/sources` | filters | source list |
| `GET /api/v1/projects/{project_id}/monitoring/series` | — | metric series list |
| `GET /api/v1/projects/{project_id}/monitoring/latest` | — | latest sample per series |
| `GET /api/v1/projects/{project_id}/monitoring/samples` | limit | recent raw samples |
| `GET /api/v1/projects/{project_id}/monitoring/history` | start_at, end_at, series id, resolution | spike-preserving rollup/raw points |
| `POST /api/v1/projects/{project_id}/monitoring/rollup/run` | — | rollup cycle summary |
| `GET /api/v1/projects/{project_id}/monitoring/alerts` | — | alert rules |
| `POST /api/v1/projects/{project_id}/monitoring/alerts` | rule definition | alert id |
| `PATCH /api/v1/projects/{project_id}/monitoring/alerts/{id}` | patch | updated rule |
| `DELETE /api/v1/projects/{project_id}/monitoring/alerts/{id}` | — | deleted |
| `GET /api/v1/projects/{project_id}/monitoring/alert-events` | limit | alert event history |
| `POST /api/v1/projects/{project_id}/monitoring/alerts/evaluate` | — | evaluation summary |
| `POST /api/v1/projects/{project_id}/monitoring/collection/start` | optional interval | collection status |
| `POST /api/v1/projects/{project_id}/monitoring/collection/stop` | — | collection status |
| `GET /api/v1/projects/{project_id}/stream?topics=metrics` | Last-Event-ID optional | SSE `MetricSample` events (coalesce policy) |
| `GET /api/v1/projects/{project_id}/stream?topics=alerts` | Last-Event-ID optional | SSE `AlertFired`/`AlertResolved` (guaranteed policy) |

M6c emits events only — action execution is M8 automation.

## Open Questions

- Whether high-volume sample ingestion should be internal-only or available to approved plugins through API.

## Deviations

- M6a streams metrics on `GET /api/v1/projects/{project_id}/stream?topics=metrics` (ADR-0008 unified stream endpoint), not a separate `/streams/metrics` path documented earlier.
- M6c added `alerts` topic with Guaranteed delivery (ADR-0016); not in original ADR-0008 table.
