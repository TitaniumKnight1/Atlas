# ADR-0021: Automation recipes and approval gating (M8b)

## Status

Accepted (M8b)

## Context

M8a delivered the trigger→action engine with idempotency, kill switch, and auto-execute-with-undo for simple actions. Roadmap automations (restart-on-crash, post-pull validation, nightly maintenance) require composing existing M3b/M4/M5 commands with appropriate safety tiers. Destructive actions must not run without explicit approval.

## Decision

1. **Recipe catalog**: Named templates in `backend/domain/automation/recipes.py` instantiate per-project workflows. Recipes invoke existing application services only; no new capability modules.

2. **Safety tiers**:
   - **AUTO**: Low-stakes / reversible reads and validation — execute immediately, audited.
   - **APPROVAL_GATED**: High-stakes process control (restart server) — create `waiting_approval` run + pending approval with preview; execute only on approve.

3. **Approvals**: `automation_approvals` table links run, step, and preview. Reject marks step rejected and remaining steps `not_attempted`. Kill switch blocks approve.

4. **Multi-step stop-and-hold**: On action failure, halt run, mark subsequent steps `not_attempted`, emit `RecipeRunHalted`.

5. **Deferred capabilities**: `nightly_maintenance` backup step omitted until backup module exists; instance records `deferred_capabilities`. Recipes with zero resolvable actions cannot instantiate.

6. **Git trigger**: Consume `GitOperationCompleted` with `operation_type=pull` (emitter unchanged).

## Recipe tiering

| Recipe | AUTO | APPROVAL_GATED | Deferred |
| --- | --- | --- | --- |
| `restart_on_crash` | — | restart_server | — |
| `post_git_pull_validation` | validate, rescan | optional restart | — |
| `nightly_maintenance` | validate, git status | backup (when built) | backup today |
| `on_alert_remediation` | notify | restart (critical) | — |

## Consequences

- M8 complete for backend recipe + approval slice.
- Visual builder (later) composes on same workflow/recipe model.
- When backup module lands, flip capability registry and backup action resolves automatically.
