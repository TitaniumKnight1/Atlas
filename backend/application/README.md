# backend\application

## Responsibility

Application services orchestrating commands, queries, and domain events per bounded context.

## Belongs here

- Use-case orchestration
- Command and query handlers
- Transaction boundaries via Unit of Work

## Does not belong here

- FastAPI routers
- SQLAlchemy implementations
- Direct filesystem access

## See also

[docs/architecture/module-boundaries.md](../docs/architecture/module-boundaries.md)
