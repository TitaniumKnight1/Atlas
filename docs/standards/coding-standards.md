# Coding Standards

Atlas is designed for long-term maintainability across a large modular codebase. These standards apply once implementation begins in Phase 5+.

## Core Rules

- Prefer strict typing in Python and TypeScript.
- Keep files small and single-purpose; split before files become hard to navigate.
- Avoid global mutable state unless justified and documented.
- Avoid magic numbers; use named constants.
- Comments explain non-obvious business logic or security boundaries, not obvious code.
- Every mutating workflow must support dry-run, preview, and audit recording per the developer-first principle.

## Layering And Dependencies

Enforce hexagonal boundaries from [docs/architecture/module-boundaries.md](../architecture/module-boundaries.md):

```
api → application → domain ← adapters
application → infrastructure
frontend → api schemas only
src-tauri → process orchestration only
```

Forbidden dependencies:

- Domain importing FastAPI, SQLAlchemy, Tauri, GitPython, APScheduler, or Sentry.
- Application importing concrete adapters directly (use ports).
- Frontend importing domain models or touching filesystem/Git/SQLite.
- Plugins receiving raw adapter access.

Modules communicate through application services or domain events, not by reaching into another module's persistence tables or filesystem paths.

## Python Backend

- Use Pydantic models at API boundaries.
- Keep ORM models in adapter/persistence layers, not domain layers.
- Application services own transaction boundaries via Unit of Work.
- Use lifespan hooks for startup/shutdown, not deprecated FastAPI event handlers.
- Use `BackgroundTasks` only for lightweight, disposable post-response work.
- Durable automation and incident processing belong in the Automation Engine or task supervisor.

## TypeScript Frontend

- Keep durable state in the backend; frontend holds transient UI state only.
- Route all mutations through the typed API client in `frontend/src/api/`.
- Plugin UI must respect capability and project-trust boundaries.
- Do not use React Server Components as the default Atlas desktop pattern.

## Security And Privacy

- Treat the backend as the only component with broad project access.
- Enforce path allowlists before filesystem writes.
- Sanitize Atlas telemetry before any Sentry upload; never send FiveM project data.
- Incident exports are manual and must warn when sensitive data may be included.

## Testing Expectations

- Domain policies: unit tests without I/O.
- Application services: unit tests with mocked ports.
- Adapters: integration tests against real tools where practical.
- API: contract tests for schemas and routes.
- Frontend: component tests and Playwright E2E for critical workflows.

## Open Questions

- Whether to adopt a formal linter/formatter stack before the first implementation PR.
- Whether domain events should be synchronous in-process only or support an outbox pattern later.
