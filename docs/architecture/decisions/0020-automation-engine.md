# ADR-0020: Automation engine foundation (M8a)

## Status

Accepted (M8a)

## Context

M8 requires a trigger→action automation engine with scheduled and event-driven execution. APScheduler was listed as an intended dependency but is not yet approved in `requirements.txt`. M0b mandates a single-writer Unit of Work (`writer_lock`) for all writes. APScheduler persistent jobstores can double-fire jobs after restarts.

## Decision

1. **Trigger→action model**: An automation workflow version binds one trigger, optional conditions, and ordered actions. Event triggers subscribe to the M0b post-commit bus (`AlertFired`, `ServerCrashed`). Time triggers use a DB-backed schedule row (`next_run_at`, `interval_seconds`).

2. **Scheduler ownership**: Use an **in-process DB-backed scheduler** (M6 retention pattern) — a daemon thread polls `automation_schedules` and invokes `AutomationEngine.trigger_schedule()`. **No APScheduler** until explicitly added to `requirements.txt` and reviewed.

3. **Single-writer integration**: Every scheduled or event-triggered run that mutates state calls `container.create_unit_of_work(project_id)` and `uow.begin()`, acquiring the shared `writer_lock`. The scheduler thread never opens a second write path.

4. **Duplicate execution safety**:
   - Idempotency keys on `automation_runs` (unique) plus `automation_idempotency_keys` audit table
   - Schedule keys: `schedule:{schedule_id}:{due_at}` — coalesce missed intervals by advancing `next_run_at` past `now` after one run
   - Event keys: `event:{type}:{project_id}:{alert_event_id|occurrence_id}`
   - Single scheduler thread + writer lock prevents concurrent duplicate claims

5. **Global kill switch**: `automation_settings.global_enabled` — when false, event handlers and scheduler return immediately without firing.

6. **Destructive automated actions**: Execute through M1 `CommandAuditRecorder` with `UndoPlan` stored on `automation_run_steps.undo_plan_json`; `POST .../run-steps/{id}/undo` applies compensation inside UoW.

7. **Privacy**: Automation runs, triggers, and outcomes are local-only — never telemetry.

## Consequences

- M8b recipe catalog composes on this engine without scheduler changes.
- Clean teardown: `AutomationSchedulerService.stop()` joins the poll thread on app shutdown.
- APScheduler may be reconsidered in a future ADR if approved; any adoption must preserve single-writer and idempotency guarantees.
