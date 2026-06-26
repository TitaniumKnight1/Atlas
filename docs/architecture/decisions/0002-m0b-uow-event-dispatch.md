# ADR-0002: M0b Unit Of Work And Event Dispatch Semantics

## Status

Accepted

## Context

Atlas uses one app-global SQLite database with WAL enabled. WAL allows readers to continue while a writer appends, but SQLite still has one writer at a time. M0b adds the backend plumbing that later modules will use: the SQLAlchemy Unit of Work, shared kernel primitives, in-process event bus, and explicit dependency injection container.

Domain events are completed facts. They must not be visible to subscribers if the write transaction rolls back.

## Decision

The SQLAlchemy Unit of Work is the only application write path. It creates one session per Unit of Work, requires explicit `begin()`, `commit()`, or `rollback()`, and holds a process-local writer lock from `begin()` until commit/rollback cleanup finishes.

Domain events collected by a Unit of Work are dispatched synchronously and in process after the SQLAlchemy transaction commits. Events collected by a rolled-back Unit of Work are discarded. Event ordering is the order collected within a Unit of Work, and Unit of Work commit ordering is serialized by the writer lock.

Event handler failures are isolated from each other. The bus attempts every registered handler for each event, then raises an aggregate dispatch error if any handler failed. Because dispatch is post-commit, handler failure does not roll back the committed transaction.

## Consequences

- Subscribers only see committed facts.
- Later durable outbox/replay support can be added behind the same event envelope without changing domain event producers.
- Long-running handlers would hold the single writer path longer, so M0b handlers must stay lightweight; durable work belongs to later scheduler/task infrastructure.
- Tests use infrastructure-only tables to prove the UoW boundary without introducing domain modules or migrations.
