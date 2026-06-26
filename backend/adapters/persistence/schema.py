from __future__ import annotations

from sqlalchemy.engine import Engine

from backend.adapters.persistence.models import Base


def bootstrap_schema(engine: Engine) -> None:
    """Create M1a tables idempotently until real migrations are introduced."""

    Base.metadata.create_all(engine)
