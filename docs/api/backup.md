# Backup API Contract

Responsibility: backup plan management, backup dry-run/run, restore dry-run/run, backup item catalog, verification, and retention evaluation.

## Commands

| Name | Inputs | Outputs | Errors | Behavior | PRD trace |
| --- | --- | --- | --- | --- | --- |
| `CreateBackupPlan` | `project_id`, environment, scope, retention policy, optional schedule | backup plan id | `ProjectScopeViolation`, `ValidationFailed` | Audited write. | Scheduled backups |
| `UpdateBackupPlan` | `project_id`, plan id, patch | updated plan | `NotFound`, `Conflict` | May update automation schedule. | Retention policies |
| `PlanBackupRun` | `project_id`, plan/scope, trigger type | `command_plan_id`, estimated items | `PreconditionFailed`, `ProjectScopeViolation` | Preview-first for large/risky scopes. | One-click backup |
| `RunBackup` | `project_id`, approved plan or plan id, `idempotency_key` | backup run id, operation id | `Conflict`, `ExternalAdapterFailed` | Long-running; streams progress. | Manual/scheduled backups |
| `PlanRestoreBackup` | `project_id`, backup run id, target scope | `command_plan_id`, restore plan | `NotFound`, `PreconditionFailed` | Always preview-first. | One-click restore |
| `RunRestoreBackup` | `project_id`, approved plan, `idempotency_key` | restore run id, operation id | `PermissionDenied`, `ExternalAdapterFailed` | Destructive/reversible write. | Restore |
| `EvaluateBackupRetention` | `project_id`, plan id | retention event summary | `NotFound`, `ValidationFailed` | May be scheduled by automation. | Retention policies |
| `VerifyBackup` | `project_id`, backup run id | verification summary | `NotFound`, `ExternalAdapterFailed` | Read/metadata update. | Backup verification |

## Queries

| Name | Inputs | Outputs | Errors | PRD trace |
| --- | --- | --- | --- | --- |
| `ListBackupPlans` | `project_id`, filters | plan list | `ProjectScopeViolation` | Scheduled backups |
| `GetBackupPlan` | `project_id`, plan id | plan detail | `NotFound` | Backup planning |
| `ListBackupRuns` | `project_id`, filters, pagination | backup history | `ProjectScopeViolation` | Backup history |
| `GetBackupRun` | `project_id`, backup run id | run detail and items | `NotFound` | Restore preview |
| `ListBackupItems` | `project_id`, backup run id | item catalog | `NotFound` | Backup verification |
| `ListRestoreRuns` | `project_id`, filters | restore history | `ProjectScopeViolation` | Restore audit |

## Published Events

| Event | Payload summary | Consumers |
| --- | --- | --- |
| `BackupPlanCreated` | `project_id`, plan id, schedule refs | Automation, Audit |
| `BackupRunPlanned` | `project_id`, scope, estimated items | Audit |
| `BackupStarted` | `project_id`, backup run id | Monitoring, Automation |
| `BackupCreated` | `project_id`, backup run id, items/hash | Incident, Audit |
| `BackupFailed` | `project_id`, backup run id, reason | Incident, Automation |
| `BackupRestoreCompleted` | `project_id`, restore run id, status | Incident, Config, Resources, Audit |
| `BackupRetentionEvaluated` | `project_id`, plan id, prune summary | Audit |

## Subscribed Events

| Source event | Reaction | Reason |
| --- | --- | --- |
| `ConfigChangePlanned` | Offer pre-change backup | Safe config workflows. |
| `ResourceUpdatePlanned` | Offer resource snapshot | Safe resource workflows. |
| `AutomationRunStarted` | Correlate scheduled backups | Workflow audit. |
| `ProjectArchived` | Disable scheduled backup plans | Avoid hidden automation. |

## Required Domain Ports

| Port | Purpose | Project scoping | Adapter target |
| --- | --- | --- | --- |
| `BackupRepositoryPort` | Persist plans, runs, items, restores, retention events | Requires `project_id` | `persistence` |
| `BackupFilesystemPort` | Read source paths and write backup artifacts | Requires project path allowlist | `filesystem` |
| `CompressionPort` | Create/read compressed archives | Requires approved backup plan | `filesystem` |
| `GitContextPort` | Capture Git status before backup | Direct app call to Git contract | application |
| `AuditPort` | Record backup/restore actions | Includes `project_id` | `persistence` |

## API Surface

| Intent | Structural request | Structural response |
| --- | --- | --- |
| `GET /api/v1/projects/{project_id}/backups/plans` | filters | plans |
| `POST /api/v1/projects/{project_id}/backups/plans` | plan definition | plan id |
| `POST /api/v1/projects/{project_id}/backups/run-plan` | scope/options | command plan |
| `POST /api/v1/projects/{project_id}/backups/runs` | approved plan | run/operation refs |
| `GET /api/v1/projects/{project_id}/backups/runs/{backup_run_id}` | ids | run detail |
| `POST /api/v1/projects/{project_id}/backups/restores/plan` | backup run/scope | restore plan |
| `POST /api/v1/projects/{project_id}/backups/restores` | approved plan | restore operation refs |

## Open Questions

- Whether backup plan schedules are owned here or always delegated to Automation.

## Deviations

None.
