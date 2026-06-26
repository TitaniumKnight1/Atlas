# Resources API Contract

Responsibility: resource inventory, dependency graph, install/update/enable/disable/delete/rollback, source provenance, version management, and health summaries.

## Commands

| Name | Inputs | Outputs | Errors | Behavior | PRD trace |
| --- | --- | --- | --- | --- | --- |
| `RescanResources` | `project_id`, optional path filters | inventory delta | `ProjectScopeViolation`, `ExternalAdapterFailed` | Long-running read scan. | Resource inventory |
| `PlanInstallResource` | `project_id`, source, target name/path | `command_plan_id`, dependency and trust warnings | `ValidationFailed`, `PermissionDenied` | Preview-first. | Install resources |
| `InstallResource` | `project_id`, approved plan, `idempotency_key` | `resource_id`, `operation_id` | `Conflict`, `ExternalAdapterFailed` | Long-running file/Git operation. | Install resources |
| `PlanUpdateResource` | `project_id`, `resource_id`, target version | `command_plan_id`, diff/backup requirements | `NotFound`, `Conflict` | Preview-first. | Update/version management |
| `UpdateResource` | `project_id`, approved plan, `idempotency_key` | operation summary | `PermissionDenied`, `ExternalAdapterFailed` | Creates audit event and state change. | Update resources |
| `SetResourceEnabledState` | `project_id`, `resource_id`, desired state | state change summary | `NotFound`, `Conflict`, `ValidationFailed` | Preview required if config files change. | Enable/disable resources |
| `RollbackResource` | `project_id`, `resource_id`, version/snapshot ref | `command_plan_id` or execution summary | `NotFound`, `PreconditionFailed` | Preview-first; may call backup/config contracts. | Rollback |
| `DeleteResource` | `project_id`, `resource_id`, approved plan | deletion summary | `PermissionDenied`, `PreconditionFailed` | Destructive; requires approval. | Delete resources |

## Queries

| Name | Inputs | Outputs | Errors | PRD trace |
| --- | --- | --- | --- | --- |
| `ListResources` | `project_id`, filters, pagination | resource summaries | `ProjectScopeViolation` | Resource manager |
| `GetResource` | `project_id`, `resource_id` | resource detail | `NotFound`, `ProjectScopeViolation` | Resource detail |
| `GetResourceDependencyGraph` | `project_id`, optional root resource | nodes/edges | `ProjectScopeViolation` | Dependency graph |
| `ListResourceVersions` | `project_id`, `resource_id` | version history | `NotFound` | Version management |
| `ListResourceStateChanges` | `project_id`, `resource_id` | state history | `NotFound` | Audit/rollback |
| `GetResourceHealth` | `project_id`, `resource_id`, time range | health snapshots | `NotFound` | Health monitoring |

## Published Events

| Event | Payload summary | Consumers |
| --- | --- | --- |
| `ResourceInventoryChanged` | `project_id`, added/removed/changed counts | Audit, Event bus (local-only; never telemetry) |
| `ResourceInstallPlanned` | `project_id`, source, target | Backup, Audit |
| `ResourceInstalled` | `project_id`, `resource_id`, source | Git, Config, Incident, Audit, Event bus (local-only; never telemetry) |
| `ResourceUpdatePlanned` | `project_id`, `resource_id`, target version | Backup, Automation |
| `ResourceUpdated` | `project_id`, `resource_id`, version | Incident, Audit, Event bus (local-only) |
| `ResourceEnabledStateChanged` | `project_id`, `resource_id`, state | Automation, Audit, Event bus (local-only) |
| `ResourceDeleted` | `project_id`, `resource_id` | Incident, Audit, Event bus (local-only; never telemetry) |
| `ResourceRolledBack` | `project_id`, `resource_id`, `rollback_run_id` | Audit, Event bus (local-only; never telemetry) |
| `ResourceRollbackFailed` | `project_id`, `resource_id`, `rollback_run_id`, error | Audit, Event bus (local-only) |
| `RollbackBatchCompleted` | `project_id`, `rollback_run_id`, counts | Audit, Event bus (local-only) |
| `RollbackBatchHalted` | `project_id`, `rollback_run_id`, failed resource | Audit, Event bus (local-only) |

## Subscribed Events

| Source event | Reaction | Reason |
| --- | --- | --- |
| `ProjectImported` | Initial resource scan | Populate inventory. |
| `SetupRunCompleted` | Rescan generated resources | Setup may create resources. |
| `GitOperationCompleted` | Refresh resource Git metadata | Resource versions can track Git. |
| `ConfigValidationFailed` | Mark resource health warning when applicable | Surface resource config risk. |

## Required Domain Ports

| Port | Purpose | Project scoping | Adapter target |
| --- | --- | --- | --- |
| `ResourceRepositoryPort` | Persist resources, versions, dependencies, state changes | Requires `project_id` on every method | `persistence` |
| `ResourceFilesystemPort` | Inspect and mutate resource directories | Requires project path allowlist and approved plan | `filesystem` |
| `ResourceGitPort` | Clone/pull resource sources where Git-backed | Requires `project_id`, resource/path refs | `git` |
| `ResourceProcessPort` | Restart/stop resource through server process where approved | Requires `project_id`, `resource_id` | `process` |
| `ResourceBackupPort` | Request snapshots before risky writes | Direct application call to Backup contract | `persistence`/application |
| `AuditPort` | Record resource operations | Includes `project_id` | `persistence` |

## API Surface

| Intent | Structural request | Structural response |
| --- | --- | --- |
| `GET /api/v1/projects/{project_id}/resources` | filters, pagination | resource list |
| `GET /api/v1/projects/{project_id}/resources/graph` | optional root | dependency graph |
| `GET /api/v1/projects/{project_id}/resources/graph/health` | — | graph health + findings |
| `GET /api/v1/projects/{project_id}/resources/graph/order` | — | topological start order |
| `GET /api/v1/projects/{project_id}/resources/{resource_id}/dependencies` | transitive flag | dependency list |
| `GET /api/v1/projects/{project_id}/resources/{resource_id}/dependents` | transitive flag | dependent list |
| `GET /api/v1/projects/{project_id}/resources/{resource_id}/health` | — | resource health summary |
| `POST /api/v1/projects/{project_id}/resources/scan` | path filters | scan result |
| `POST /api/v1/projects/{project_id}/resources/install-plan` | source/target | command plan |
| `POST /api/v1/projects/{project_id}/resources/install` | approved plan | resource/operation refs |
| `POST /api/v1/projects/{project_id}/resources/{resource_id}/update-plan` | target version | command plan |
| `POST /api/v1/projects/{project_id}/resources/{resource_id}/enabled-state` | desired state | change summary |
| `POST /api/v1/projects/{project_id}/resources/{resource_id}/delete-plan` | — | command plan |
| `POST /api/v1/projects/{project_id}/resources/{resource_id}/delete` | — | deletion summary |
| `POST /api/v1/projects/{project_id}/resources/rollback-plan` | resource or execution ids | ordered rollback plan |
| `POST /api/v1/projects/{project_id}/resources/rollback` | resource or execution ids | rollback run result |
| `GET /api/v1/projects/{project_id}/resources/rollback-runs/{rollback_run_id}` | — | persisted rollback run |

## Open Questions

- Whether resource process control should route through Resource or Automation for all non-manual runs.

## Deviations

None.
