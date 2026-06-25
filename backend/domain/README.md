# backend\domain

## Responsibility

Pure domain models, policies, events, and port interfaces for all bounded contexts.

## Belongs here

- Domain entities and value objects
- Policies and invariants
- Port interfaces (abstract)
- Domain events

## Does not belong here

- FastAPI, SQLAlchemy, Tauri, GitPython, APScheduler, or Sentry imports
- Adapter implementations

## See also

[docs/architecture/module-boundaries.md](../docs/architecture/module-boundaries.md)
