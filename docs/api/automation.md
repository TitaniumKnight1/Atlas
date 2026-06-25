# Automation API Contract

Responsibility: workflow definitions, versions, triggers, conditions, actions, schedules, dry-run/run lifecycle, approvals, idempotency keys, progress streams, and automation failure incidents.

## Commands

| Name | Inputs | Outputs | Errors | Behavior | PRD trace |
| --- | --- | --- | --- | --- | --- |
| `CreateAutomationWorkflow` | `project_id`, name, definition | workflow id, version id | `ValidationFailed`, `ProjectScopeViolation` | Audited write. | Visual automation |
| `UpdateAutomationWorkflow` | `project_id`, workflow id, new definition | new version id | `NotFound`, `Conflict`, `ValidationFailed` | Immutable version creation. | Workflow versioning |
| `SetAutomationEnabledState` | `project_id`, workflow id, enabled state | workflow summary | `NotFound`, `PermissionDenied` | Audited write. | Enable/disable automation |
| `PlanAutomationRun` | `project_id`, workflow id/version id, trigger payload | command plan/run preview | `ValidationFailed`, `PreconditionFailed` | Dry-run only. | Dry run |
| `RunAutomationWorkflow` | `project_id`, workflow id/version id, trigger payload, `idempotency_key` | run id, operation id | `Conflict`, `PermissionDenied` | Long-running; may wait for approval. | Deployment pipelines |
| `ApproveAutomationRunAction` | `project_id`, run id, approval id, decision | approval result | `NotFound`, `PermissionDenied`, `Conflict` | Required for destructive/external actions. | Approval gates |
| `CancelAutomationRun` | `project_id`, run id, reason | cancellation summary | `NotFound`, `Conflict` | Best-effort cancellation. | Transparent automation |
| `RegisterAutomationSchedule` | `project_id`, workflow id, schedule definition | schedule id | `ValidationFailed`, `Conflict` | Stable scheduler key. | Nightly backup/scheduled workflows |
| `EvaluateAutomationTrigger` | `project_id`, domain event ref | matched workflow runs | `ProjectScopeViolation` | Internal event-driven command. | Event-triggered workflows |

## Queries

| Name | Inputs | Outputs | Errors | PRD trace |
| --- | --- | --- | --- | --- |
| `ListAutomationWorkflows` | `project_id`, enabled/status filters | workflows | `ProjectScopeViolation` | Visual automation |
| `GetAutomationWorkflow` | `project_id`, workflow id | workflow and current version | `NotFound` | Workflow detail |
| `ListAutomationRuns` | `project_id`, filters, pagination | run history | `ProjectScopeViolation` | Audit logs |
| `GetAutomationRun` | `project_id`, run id | run steps/approvals | `NotFound` | Progress and audit |
| `ListPendingApprovals` | `project_id`, actor/safety filters | approval list | `ProjectScopeViolation` | Approval gates |
| `ListAutomationSchedules` | `project_id`, due/enabled filters | schedules | `ProjectScopeViolation` | Scheduled automation |

## Published Events

| Event | Payload summary | Consumers |
| --- | --- | --- |
| `AutomationWorkflowCreated` | `project_id`, workflow id | Audit |
| `AutomationWorkflowUpdated` | `project_id`, workflow id, version id | Audit |
| `AutomationRunStarted` | `project_id`, run id, trigger | Backup, Incident, Audit |
| `AutomationApprovalRequested` | `project_id`, run id, action safety | Plugin, Audit |
| `AutomationRunCompleted` | `project_id`, run id, status | Incident, Audit |
| `AutomationRunFailed` | `project_id`, run id, failure summary | Incident, Monitoring, Audit |
| `AutomationScheduleDue` | `project_id`, schedule id | Automation runner |

## Subscribed Events

| Source event | Reaction | Reason |
| --- | --- | --- |
| `GitOperationCompleted` | Match Git pull workflows | PRD trigger. |
| `ServerProcessCrashed` | Match restart/incident workflows | PRD trigger. |
| `ResourceUpdated` | Match validation/restart workflows | Resource automation. |
| `ConfigChanged` | Match validation/restart workflows | Config automation. |
| `BackupCreated` | Match backup-completed workflows | PRD trigger. |
| `IncidentCreated` | Match incident response workflows | Incident automation. |
| `MonitoringAlertTriggered` | Match alert workflows | Monitoring automation. |
| `WorkspaceTrustChanged` | Disable/limit risky workflows | Safety. |

## Required Domain Ports

| Port | Purpose | Project scoping | Adapter target |
| --- | --- | --- | --- |
| `AutomationRepositoryPort` | Persist workflows, versions, schedules, runs, approvals, idempotency | Requires `project_id` | `persistence` |
| `SchedulerPort` | Register/due schedules with stable ids | Requires `project_id` and schedule key | infrastructure scheduler |
| `CommandPlannerPort` | Build dry-run plans for actions | Requires `project_id` | application contracts |
| `ActionExecutionPort` | Execute approved action via owning modules/adapters | Requires `project_id`, approval state | application/ports |
| `PluginAutomationPort` | Load plugin triggers/actions with capability checks | Requires plugin grant and `project_id` | `plugin` |
| `AuditPort` | Record workflow/run decisions | Includes `project_id` | `persistence` |

## API Surface

| Intent | Structural request | Structural response |
| --- | --- | --- |
| `GET /api/v1/projects/{project_id}/automations` | filters | workflows |
| `POST /api/v1/projects/{project_id}/automations` | definition | workflow/version ids |
| `PATCH /api/v1/projects/{project_id}/automations/{workflow_id}` | definition patch | new version id |
| `POST /api/v1/projects/{project_id}/automations/{workflow_id}/run-plan` | trigger payload | command plan |
| `POST /api/v1/projects/{project_id}/automations/{workflow_id}/runs` | trigger payload, idempotency | run/operation refs |
| `POST /api/v1/projects/{project_id}/automations/runs/{run_id}/approvals/{approval_id}` | decision | approval result |
| `GET /api/v1/projects/{project_id}/streams/automation-runs` | filters | run progress topic |

## Open Questions

- Whether workflow definitions should be optionally stored as project-local files for Git review.

## Deviations

None.
