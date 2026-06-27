from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.adapters.persistence.models import Base

METRIC_SOURCE_COLUMNS: tuple[str, ...] = (
    "metric_source_id",
    "project_id",
    "environment_id",
    "source_type",
    "source_ref",
    "display_name",
    "is_enabled",
    "metadata_json",
)
RETIRED_METRIC_SOURCE_TYPES: tuple[str, ...] = ("network", "database")
METRIC_SOURCE_TYPE_CHECK_MARKER = "'fivem'"


def _metric_sources_table_ddl(engine: Engine) -> str | None:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='metric_sources'")
        ).scalar_one_or_none()


def _metric_sources_needs_migration(ddl: str | None) -> bool:
    if ddl is None:
        return False
    if "ck_metric_sources_type" not in ddl:
        return True
    if METRIC_SOURCE_TYPE_CHECK_MARKER not in ddl:
        return True
    return any(retired in ddl for retired in RETIRED_METRIC_SOURCE_TYPES)


def bootstrap_schema(engine: Engine) -> None:
    """Create M1a tables idempotently until real migrations are introduced."""
    needs_migration = _metric_sources_needs_migration(_metric_sources_table_ddl(engine))

    if needs_migration:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text("PRAGMA foreign_keys=OFF"))
            try:
                conn.execute(text("ALTER TABLE metric_sources RENAME TO metric_sources_old"))
            except Exception:
                conn.execute(text("PRAGMA foreign_keys=ON"))
                raise

    Base.metadata.create_all(engine)

    if needs_migration:
        column_list = ", ".join(METRIC_SOURCE_COLUMNS)
        retired_values = ", ".join(f"'{value}'" for value in RETIRED_METRIC_SOURCE_TYPES)
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            try:
                conn.execute(
                    text(f"DELETE FROM metric_sources_old WHERE source_type IN ({retired_values})")
                )
                conn.execute(
                    text(
                        f"INSERT INTO metric_sources ({column_list}) "
                        f"SELECT {column_list} FROM metric_sources_old"
                    )
                )
                conn.execute(text("DROP TABLE metric_sources_old"))
            finally:
                conn.execute(text("PRAGMA foreign_keys=ON"))
