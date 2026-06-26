from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


SQLITE_BUSY_TIMEOUT_MS = 5000
SQLITE_DATABASE_NAME = "atlas.sqlite3"


def sqlite_database_path(app_data_dir: Path) -> Path:
    return app_data_dir / SQLITE_DATABASE_NAME


def create_sqlite_engine(app_data_dir: Path) -> Engine:
    app_data_dir.mkdir(parents=True, exist_ok=True)
    database_path = sqlite_database_path(app_data_dir)
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _configure_sqlite_connection(dbapi_connection: object, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
            cursor.execute("PRAGMA journal_mode = WAL")
        finally:
            cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
