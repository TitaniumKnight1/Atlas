# Project API Contract

Responsibility: project import, discovery, paths, environment profiles, settings, templates, and workspace trust. All project-owned operations include `project_id`; template listing is global unless creating a project from a template.

## Commands

| Name | Inputs | Outputs | Errors | Behavior | PRD trace |
| --- | --- | --- | --- | --- | --- |
| `ImportProject` | `root_path`, optional `template_id`, `idempotency_key` | `project_id`, detected paths, warnings | `ValidationFailed`, `Conflict`, `ExternalAdapterFailed` | Long-running; creates project record after filesystem inspection. | Project import/discovery |
| `CreateProjectFromTemplate` | `template_id`, destination path, display name, `idempotency_key` | `command_plan_id` or `project_id` | `ValidationFailed`, `Conflict`, `PermissionDenied` | Preview-first when files will be created. | Project templates |
| `UpdateProjectSettings` | `project_id`, settings patch, expected version | updated settings summary | `ProjectScopeViolation`, `ValidationFailed`, `Conflict` | Audited write. | Per-project settings |
| `CreateEnvironmentProfile` | `project_id`, name, profile settings | `environment_id` | `ProjectScopeViolation`, `ValidationFailed`, `Conflict` | Adds local/staging/production profile. | Environment profiles |
| `UpdateEnvironmentProfile` | `project_id`, `environment_id`, settings patch | updated profile | `NotFound`, `ProjectScopeViolation`, `Conflict` | Audited write. | Environment profiles |
| `RecordWorkspaceTrustDecision` | `project_id`, scope, scope ref, trust state, reason | trust decision id | `ProjectScopeViolation`, `ValidationFailed` | Audited security decision. | Workspace trust |
| `ArchiveProject` | `project_id`, reason | archived project summary | `ProjectScopeViolation`, `Conflict` | Soft-delete; does not delete user files. | Workspace management |

## Queries

| Name | Inputs | Outputs | Errors | PRD trace |
| --- | --- | --- | --- | --- |
| `ListProjects` | global filters, pagination | project summaries | none | Multiple projects |
| `GetProject` | `project_id` | project detail, paths, default environment | `NotFound`, `ProjectScopeViolation` | Workspace management |
| `ListProjectPaths` | `project_id`, optional role | project path refs | `ProjectScopeViolation` | Project import/discovery |
| `ListEnvironmentProfiles` | `project_id` | profiles | `ProjectScopeViolation` | Environment profiles |
| `GetProjectSettings` | `project_id`, keys | settings map | `ProjectScopeViolation` | Per-project settings |
| `ListProjectTemplates` | source filters | template summaries | none | Project templates |
| `GetWorkspaceTrustState` | `project_id`, optional scope | trust decisions | `ProjectScopeViolation` | Workspace trust |

## Published Events

| Event | Payload summary | Consumers |
| --- | --- | --- |
| `ProjectImported` | `project_id`, paths, detected features | Setup, Resources, Git, Config, Audit |
| `ProjectSettingsUpdated` | `project_id`, changed keys | Automation, Audit |
| `EnvironmentProfileCreated` | `project_id`, `environment_id`, name | Setup, Backup, Automation |
| `WorkspaceTrustChanged` | `project_id`, scope, trust state | Plugin, Automation, Audit |
| `ProjectArchived` | `project_id`, reason | Automation, Monitoring, Audit |

## Subscribed Events

| Source event | Reaction | Reason |
| --- | --- | --- |
| `PluginCapabilityDenied` | Add trust warning to project summary | Show security posture without plugin reach-through. |
| `TelemetryRejected` | Surface privacy warning if project-scoped | Keep user aware of privacy protections. |

## Required Domain Ports

| Port | Purpose | Project scoping | Adapter target |
| --- | --- | --- | --- |
| `ProjectRepositoryPort` | Persist projects, paths, profiles, settings, trust | Requires `project_id` for project rows; global templates explicit | `persistence` |
| `ProjectFilesystemInspectionPort` | Inspect root, server-data, resources, txData paths | Reads only paths selected for import | `filesystem` |
| `AuditPort` | Record trust/settings/import audit events | Includes `project_id` when present | `persistence` |

## API Surface

| Intent | Structural request | Structural response |
| --- | --- | --- |
| `GET /api/v1/projects` | filters, pagination | project summaries |
| `POST /api/v1/projects/import-plan` | root path, template hint | plan, warnings, detected paths |
| `POST /api/v1/projects/import` | approved plan, idempotency key | project id, command execution id |
| `GET /api/v1/projects/{project_id}` | path project id | project detail |
| `PATCH /api/v1/projects/{project_id}/settings` | settings patch, expected version | updated settings |
| `POST /api/v1/projects/{project_id}/environments` | profile request | environment id |
| `POST /api/v1/projects/{project_id}/trust-decisions` | trust decision | decision id |

## Open Questions

- Whether project templates become a separate global bounded context later.

## Deviations

None.
