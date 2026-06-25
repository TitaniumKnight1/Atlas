# Setup API Contract

Responsibility: artifact discovery/pinning, setup recipes, setup dry-runs/runs, dependency checks, and txAdmin instance detection.

## Commands

| Name | Inputs | Outputs | Errors | Behavior | PRD trace |
| --- | --- | --- | --- | --- | --- |
| `RefreshArtifactCatalog` | platform, channel filters | discovered artifact count | `ExternalAdapterFailed` | Global read/write cache update. | Artifact download/update |
| `PinArtifactVersion` | `project_id`, optional `environment_id`, artifact id or channel preference | artifact pin summary | `ProjectScopeViolation`, `NotFound`, `ValidationFailed` | Audited project write. | Environment-specific setup |
| `PlanServerSetup` | `project_id`, `environment_id`, recipe id, options | `command_plan_id`, setup steps, risks | `ProjectScopeViolation`, `ValidationFailed`, `PreconditionFailed` | Dry-run only; no file changes. | Wizard-driven setup |
| `RunServerSetup` | `project_id`, approved `command_plan_id`, `idempotency_key` | `setup_run_id`, `operation_id` | `Conflict`, `PermissionDenied`, `ExternalAdapterFailed` | Long-running; streams setup progress. | Initial server setup |
| `RunDependencyChecks` | `project_id`, `environment_id`, check categories | check run summary | `ProjectScopeViolation`, `ExternalAdapterFailed` | May be read-only; can create findings. | Preflight validation |
| `DetectTxAdminInstance` | `project_id`, path refs | txAdmin instance summary | `ProjectScopeViolation`, `ExternalAdapterFailed` | Reads local files/processes only. | txAdmin guidance |

## Queries

| Name | Inputs | Outputs | Errors | PRD trace |
| --- | --- | --- | --- | --- |
| `ListArtifactVersions` | platform, channel, pagination | artifact summaries | none | Artifact selection |
| `GetProjectArtifactPin` | `project_id`, optional `environment_id` | pin detail | `ProjectScopeViolation` | Artifact pinning |
| `ListSetupRecipes` | source filters | recipe summaries | none | Setup recipes |
| `GetSetupRun` | `project_id`, `setup_run_id` | run and steps | `ProjectScopeViolation`, `NotFound` | Setup transparency |
| `ListDependencyChecks` | `project_id`, filters | check findings | `ProjectScopeViolation` | Preflight validation |
| `GetTxAdminInstance` | `project_id` | txAdmin metadata | `ProjectScopeViolation` | txAdmin integration |

## Published Events

| Event | Payload summary | Consumers |
| --- | --- | --- |
| `ArtifactCatalogRefreshed` | platform, channels, count | Audit |
| `ArtifactVersionPinned` | `project_id`, environment, artifact/channel | Incident, Automation, Audit |
| `SetupRunPlanned` | `project_id`, setup_run/plan refs | Audit |
| `SetupRunStarted` | `project_id`, setup_run_id | Automation, Monitoring |
| `SetupRunCompleted` | `project_id`, status, summary | Resources, Config, Backup, Incident, Audit |
| `DependencyCheckFailed` | `project_id`, check key, severity | Incident, Automation |
| `TxAdminInstanceDetected` | `project_id`, txData path, port | Monitoring, Audit |

## Subscribed Events

| Source event | Reaction | Reason |
| --- | --- | --- |
| `ProjectImported` | Detect initial artifact/txAdmin/setup state | Setup follows project import. |
| `EnvironmentProfileCreated` | Initialize artifact pin defaults | Environment profiles own setup policy. |
| `WorkspaceTrustChanged` | Re-evaluate whether setup actions can execute | Setup may write files or start processes. |

## Required Domain Ports

| Port | Purpose | Project scoping | Adapter target |
| --- | --- | --- | --- |
| `SetupRepositoryPort` | Persist artifact pins, recipes, setup runs, checks, txAdmin refs | All project rows require `project_id` | `persistence` |
| `FiveMArtifactPort` | Discover/download/verify FXServer artifacts | Global catalog; project pin writes include `project_id` | `fivem` |
| `TxAdminPort` | Detect txAdmin state and local metadata | Requires `project_id` and path refs | `txadmin` |
| `SetupFilesystemPort` | Inspect/create project files during approved setup | Requires project path allowlist | `filesystem` |
| `ProcessPort` | Start/observe setup-related processes when approved | Requires `project_id` and command plan | `process` |
| `AuditPort` | Record setup decisions and run outcomes | Includes `project_id` | `persistence` |

## API Surface

| Intent | Structural request | Structural response |
| --- | --- | --- |
| `GET /api/v1/artifacts` | platform/channel filters | artifact list |
| `PUT /api/v1/projects/{project_id}/artifact-pin` | environment, artifact/channel | pin summary |
| `GET /api/v1/setup-recipes` | source filters | recipe list |
| `POST /api/v1/projects/{project_id}/setup/plan` | recipe/options | command plan |
| `POST /api/v1/projects/{project_id}/setup/run` | approved plan, idempotency key | setup run, operation id |
| `GET /api/v1/projects/{project_id}/setup-runs/{setup_run_id}` | ids | setup run detail |
| `POST /api/v1/projects/{project_id}/dependency-checks/run` | categories | findings summary |

## Open Questions

- How much txAdmin API integration is stable enough for MVP contracts.

## Deviations

None.
