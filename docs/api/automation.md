# Automation API Contract

Responsibility: workflow definitions, recipe catalog, triggers, conditions, actions, schedules, run lifecycle, approvals, idempotency keys, and automation audit.

## Implementation status (M8a + M8b)

| Area | Status | Notes |
| --- | --- | --- |
| Trigger→action engine | **M8a** | Event + schedule triggers, conditions, idempotent runs |
| In-process DB scheduler | **M8a** | Polls `automation_schedules`; not APScheduler |
| Global kill switch | **M8a** | `PATCH /automation/settings` (`global_enabled`) |
| Simple actions | **M8a** | `record_local_notification`, `append_config_marker` |
| Recipe catalog + instantiation | **M8b** | Named templates composing existing M3b/M4/M5 commands |
| Approval gating | **M8b** | Pending runs for destructive/high-stakes actions |
| Multi-step stop-and-hold | **M8b** | Halt on failure; `not_attempted` for remaining steps |
| Workflow versioning API | **Deferred** | M8a creates version 1 only; no `PATCH` definition |
| Dry-run / run-plan | **Deferred** | Use approval preview on gated steps |
| Plugin triggers/actions | **M9** | Not implemented |
| Visual builder frontend | **Later** | Backend-only |

### Subscribed domain events (actual)

| Bus event | Recipe/workflow trigger | Notes |
| --- | --- | --- |
| `AlertFired` | `alert_fired` | M6c stream→bus |
| `ServerCrashed` | `server_crashed` | M7/M3b |
| `GitOperationCompleted` | `git_pull_completed` when `operation_type=pull` and `status=succeeded` | M4b emitter unchanged |
| Schedule poll | `schedule` | M8a in-process scheduler |

## Safety tiers (M8b)

| Tier | Behavior | Examples |
| --- | --- | --- |
| **AUTO** | Executes immediately; audited; reversible where M1 provides undo | Config validation, resource rescan, local notify |
| **APPROVAL_GATED** | Creates `waiting_approval` run + pending approval; executes only after explicit approve | Restart server, optional post-pull restart |

Destructive actions are never unguarded auto-actions.

## Recipe catalog (M8b)

| Recipe key | Trigger | Actions (tier) | Capability deps |
| --- | --- | --- | --- |
| `restart_on_crash` | `server_crashed` | `restart_server` (APPROVAL) | M3b process |
| `post_git_pull_validation` | `git_pull_completed` | `run_config_validation` (AUTO), `rescan_resources` (AUTO), optional `restart_server` (APPROVAL) | M4a, M5b, M3b |
| `nightly_maintenance` | `schedule` | `run_config_validation` (AUTO), `git_capture_status` (AUTO), `create_backup` (**DEFERRED** — no backup module) | M4a, M4b; backup missing |
| `on_alert_remediation` | `alert_fired` | `record_local_notification` (AUTO); `restart_server` (APPROVAL) when severity=critical | M6c, M3b |

Missing capabilities → recipe instance marked **deferred** (not faked).

## Commands

| Name | Inputs | Outputs | Errors | Behavior | Status |
| --- | --- | --- | --- | --- | --- |
| `CreateAutomationWorkflow` | `project_id`, name, definition | workflow id, version id | `ValidationFailed` | Audited write | M8a |
| `InstantiateAutomationRecipe` | `project_id`, recipe key, params | workflow id, instance id | `PreconditionFailed` if deferred | Creates workflow from template | M8b |
| `SetAutomationEnabledState` | `project_id`, workflow id, enabled | workflow summary | `NotFound` | Audited write | M8a |
| `RunAutomationWorkflow` | `project_id`, workflow id, `idempotency_key` | run id | `Conflict` | Manual/event/schedule trigger | M8a |
| `ApproveAutomationRun` | `project_id`, run id, approval id | approval result, continued run | `NotFound`, `Conflict` | Executes gated action; continues steps | M8b |
| `RejectAutomationRun` | `project_id`, run id, approval id, reason | rejection summary | `NotFound` | No action; remaining steps `not_attempted` | M8b |
| `SetGlobalAutomationEnabled` | `global_enabled` | settings | — | Kill switch | M8a |
| `UndoAutomationRunStep` | `project_id`, step id | undo result | `NotFound` | M1 compensation | M8a |

## Queries

| Name | Inputs | Outputs | Status |
| --- | --- | --- | --- |
| `ListAutomationWorkflows` | `project_id` | workflows | M8a |
| `ListAutomationRecipes` | — | recipe definitions + capability status | M8b |
| `ListAutomationRecipeInstances` | `project_id` | instances | M8b |
| `ListAutomationRuns` | `project_id`, limit | run history | M8a |
| `GetAutomationRun` | `project_id`, run id | run + steps + approvals | M8a/M8b |
| `ListPendingApprovals` | `project_id` | pending approvals | M8b |

## Published Events (local-only; never telemetry)

| Event | Payload summary | Status |
| --- | --- | --- |
| `AutomationTriggered` | `project_id`, run id, workflow id | M8a |
| `AutomationRunCompleted` | `project_id`, run id | M8a |
| `AutomationRunFailed` | `project_id`, run id, message | M8a |
| `AutomationApprovalRequested` | `project_id`, run id, approval id, preview | M8b |
| `AutomationApprovalGranted` | `project_id`, run id, approval id | M8b |
| `AutomationApprovalRejected` | `project_id`, run id, approval id | M8b |
| `RecipeRunHalted` | `project_id`, run id, failed step | M8b |

## API Surface (implemented)

| Intent | Route | Status |
| --- | --- | --- |
| Global settings | `GET/PATCH /api/v1/automation/settings` | M8a |
| List/create workflows | `GET/POST /api/v1/projects/{project_id}/automation/workflows` | M8a |
| Enable/disable workflow | `PATCH .../workflows/{workflow_id}` | M8a |
| List/get runs | `GET .../automation/runs`, `GET .../runs/{run_id}` | M8a |
| Manual run | `POST .../workflows/{workflow_id}/run` | M8a |
| Undo step | `POST .../run-steps/{step_id}/undo` | M8a |
| List recipes | `GET /api/v1/automation/recipes` | M8b |
| Instantiate recipe | `POST /api/v1/projects/{project_id}/automation/recipes/{recipe_key}` | M8b |
| List instances | `GET .../automation/recipe-instances` | M8b |
| Pending approvals | `GET .../automation/approvals/pending` | M8b |
| Approve/reject | `POST .../automation/runs/{run_id}/approvals/{approval_id}/approve` / `.../reject` | M8b |

## Open Questions

- Whether workflow definitions should be optionally stored as project-local files for Git review.
- When backup module lands, `nightly_maintenance` deferred backup step wires automatically.

## Deviations

- Contract event `GitPullCompleted` is consumed as `GitOperationCompleted` with `operation_type=pull` (emitter unchanged).
- Contract event `ServerProcessCrashed` is consumed as `ServerCrashed` (M7 name).
- Route prefix uses `/automation/` not `/automations/` (M8a path).
