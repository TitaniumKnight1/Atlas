# Config API Contract

Responsibility: configuration inventory, snapshots, preview/apply/revert change sets, validation, findings, search, diff support, undo history, and secret scans.

## Commands

| Name | Inputs | Outputs | Errors | Behavior | PRD trace |
| --- | --- | --- | --- | --- | --- |
| `RescanConfigFiles` | `project_id`, optional environment/path filters | config delta | `ProjectScopeViolation`, `ExternalAdapterFailed` | Read scan that updates inventory. | Configuration editor |
| `CreateConfigSnapshot` | `project_id`, `config_file_id`, snapshot kind | snapshot id | `NotFound`, `ExternalAdapterFailed` | Captures hash and optional external file ref. | Undo history |
| `PlanConfigChangeSet` | `project_id`, file id, proposed edits | `command_plan_id`, diff, findings | `ValidationFailed`, `ProjectScopeViolation` | Preview-first. | Diff viewer/live validation |
| `ApplyConfigChangeSet` | `project_id`, approved plan, `idempotency_key` | change set id, execution id | `Conflict`, `PermissionDenied`, `ExternalAdapterFailed` | Writes files through adapter, creates snapshots. | GUI config editing |
| `RevertConfigChangeSet` | `project_id`, change set id, `idempotency_key` | revert summary | `NotFound`, `Conflict`, `PreconditionFailed` | Preview-first when risky. | Undo history |
| `RunConfigValidation` | `project_id`, optional file/filter, validator ids | validation run id, findings | `ExternalAdapterFailed` | Can be sync or long-running. | Live validation |
| `RunSecretScan` | `project_id`, paths or config ids | finding summary | `ProjectScopeViolation`, `ExternalAdapterFailed` | Never persists raw secrets. | Secret detection warnings |

## Queries

| Name | Inputs | Outputs | Errors | PRD trace |
| --- | --- | --- | --- | --- |
| `ListConfigFiles` | `project_id`, environment/type filters | config file list | `ProjectScopeViolation` | Config inventory |
| `GetConfigFileView` | `project_id`, config id | metadata and safe preview ref | `NotFound` | Editor display |
| `ListConfigSnapshots` | `project_id`, config id | snapshot list | `NotFound` | Undo history |
| `GetConfigDiff` | `project_id`, snapshot/change refs | structured diff | `NotFound` | Diff viewer |
| `ListValidationFindings` | `project_id`, filters | findings | `ProjectScopeViolation` | Live validation |
| `ListSecretFindings` | `project_id`, status filters | redacted findings | `ProjectScopeViolation` | Secret warnings |

## Published Events

| Event | Payload summary | Consumers |
| --- | --- | --- |
| `ConfigInventoryChanged` | `project_id`, changed file count | Automation, Audit |
| `ConfigChangePlanned` | `project_id`, file refs, risk | Backup, Audit |
| `ConfigChanged` | `project_id`, change set id, affected files | Resource, Automation, Incident, Audit |
| `ConfigValidationFailed` | `project_id`, validator id, severity | Incident, Automation, Resources |
| `SecretScanFindingDetected` | `project_id`, severity, redacted preview | Telemetry, Audit |

## Subscribed Events

| Source event | Reaction | Reason |
| --- | --- | --- |
| `ProjectImported` | Scan config files | Populate editor. |
| `SetupRunCompleted` | Rescan generated configs | Setup can create server.cfg/resource configs. |
| `ResourceInstalled` | Scan resource config | New resources may add configs. |
| `GitOperationCompleted` | Revalidate changed configs | Pulls can alter configs. |

## Required Domain Ports

| Port | Purpose | Project scoping | Adapter target |
| --- | --- | --- | --- |
| `ConfigRepositoryPort` | Persist config files, snapshots, changes, findings | Requires `project_id` | `persistence` |
| `ConfigFilesystemPort` | Read/write config files and snapshots | Requires project path allowlist and approved plan | `filesystem` |
| `ConfigValidationPort` | Run builtin/plugin validators | Requires `project_id`, file scope | `plugin`/domain validators |
| `SecretScannerPort` | Detect secrets without persisting raw values | Requires `project_id`, path scope | `filesystem` |
| `BackupRequestPort` | Request pre-change snapshots | Direct app call to Backup contract | application |
| `AuditPort` | Record config operations | Includes `project_id` | `persistence` |

## API Surface

| Intent | Structural request | Structural response |
| --- | --- | --- |
| `GET /api/v1/projects/{project_id}/config-files` | filters | config list |
| `POST /api/v1/projects/{project_id}/config-files/rescan` | path filters | scan result |
| `POST /api/v1/projects/{project_id}/config/change-plan` | proposed edits | command plan and diff |
| `POST /api/v1/projects/{project_id}/config/change-sets/apply` | approved plan | execution refs |
| `POST /api/v1/projects/{project_id}/config/change-sets/{change_set_id}/revert-plan` | id | command plan |
| `POST /api/v1/projects/{project_id}/config/validation-runs` | validator filters | run/findings |
| `GET /api/v1/projects/{project_id}/config/findings` | filters | findings |

## Open Questions

- Whether config search indexes belong in this context or a future search/read-model context.

## Deviations

None.
