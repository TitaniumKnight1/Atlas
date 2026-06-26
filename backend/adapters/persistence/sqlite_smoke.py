from __future__ import annotations

import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class SqliteSmokeResult:
    database_path: str
    journal_mode: str
    inserted_key: str
    round_tripped_value: str


class SqliteSmokeStore:
    """Minimal persistence proof for M0a; not the future Unit of Work."""

    def __init__(self, app_data_dir: Path) -> None:
        self._app_data_dir = app_data_dir
        self._db_path = app_data_dir / "atlas.sqlite3"
        self._connection: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        self._journal_mode = "unknown"

    @property
    def database_path(self) -> Path:
        return self._db_path

    @property
    def journal_mode(self) -> str:
        return self._journal_mode

    def open(self) -> None:
        self._app_data_dir.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._db_path, check_same_thread=False)
        connection.execute("PRAGMA busy_timeout = 5000")
        self._journal_mode = str(connection.execute("PRAGMA journal_mode = WAL").fetchone()[0])
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS debug_sqlite_smoke (
                smoke_key TEXT PRIMARY KEY,
                smoke_value TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.commit()
        self._connection = connection

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def round_trip(self) -> SqliteSmokeResult:
        connection = self._require_connection()
        smoke_key = str(uuid.uuid4())
        smoke_value = f"atlas-smoke:{smoke_key}"
        created_at = datetime.now(UTC).isoformat()

        with self._lock:
            connection.execute(
                "INSERT INTO debug_sqlite_smoke (smoke_key, smoke_value, created_at) VALUES (?, ?, ?)",
                (smoke_key, smoke_value, created_at),
            )
            connection.commit()
            row = connection.execute(
                "SELECT smoke_value FROM debug_sqlite_smoke WHERE smoke_key = ?",
                (smoke_key,),
            ).fetchone()

        if row is None:
            raise RuntimeError("SQLite smoke row was not found after insert")

        return SqliteSmokeResult(
            database_path=str(self._db_path),
            journal_mode=self._journal_mode,
            inserted_key=smoke_key,
            round_tripped_value=str(row[0]),
        )

    def _require_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("SQLite smoke store is not open")
        return self._connection
