from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from backend.adapters.persistence.schema import bootstrap_schema
from backend.domain.shared_kernel import ProjectId
from backend.infrastructure.di.container import create_application_container

LEGACY_METRIC_SOURCES_DDL = """
    CREATE TABLE metric_sources (
        metric_source_id VARCHAR NOT NULL,
        project_id VARCHAR NOT NULL,
        environment_id VARCHAR,
        source_type VARCHAR NOT NULL,
        source_ref VARCHAR,
        display_name VARCHAR NOT NULL,
        is_enabled INTEGER NOT NULL,
        metadata_json JSON,
        PRIMARY KEY (metric_source_id),
        CONSTRAINT ck_metric_sources_type CHECK (
            source_type in (
                'process', 'resource', 'database', 'network', 'disk', 'plugin', 'system', 'deferred'
            )
        ),
        CONSTRAINT uq_metric_sources_project_type_ref UNIQUE (project_id, source_type, source_ref)
    )
"""


def _create_legacy_metric_sources_table(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(LEGACY_METRIC_SOURCES_DDL))
        conn.execute(
            text(
                """
                INSERT INTO metric_sources (
                    metric_source_id, project_id, environment_id, source_type, source_ref,
                    display_name, is_enabled, metadata_json
                ) VALUES (
                    'src_network', 'proj_1', NULL, 'network', NULL,
                    'legacy-network', 1, '{}'
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO metric_sources (
                    metric_source_id, project_id, environment_id, source_type, source_ref,
                    display_name, is_enabled, metadata_json
                ) VALUES (
                    'src_process', 'proj_1', NULL, 'process', NULL,
                    'legacy-process', 1, '{}'
                )
                """
            )
        )


def test_upgrade_path_for_metric_sources(tmp_path: Path) -> None:
    db_path = tmp_path / "app-data" / "atlas.sqlite3"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}")

    _create_legacy_metric_sources_table(engine)

    container = create_application_container(tmp_path / "app-data")
    project_id = ProjectId(
        container.create_project_service().execute_import_project(root_path=tmp_path).result["project_id"]
    )

    try:
        service = container.create_monitoring_service()
        service.collect_once(project_id)

        with engine.connect() as conn:
            fivem_rows = conn.execute(
                text("SELECT source_type FROM metric_sources WHERE source_type='fivem'")
            ).fetchall()
            assert len(fivem_rows) == 1

            retired_rows = conn.execute(
                text("SELECT source_type FROM metric_sources WHERE source_type IN ('network', 'database')")
            ).fetchall()
            assert retired_rows == []

            kept_legacy = conn.execute(
                text("SELECT source_type FROM metric_sources WHERE metric_source_id='src_process'")
            ).fetchall()
            assert kept_legacy == [("process",)]

            ddl = conn.execute(
                text("SELECT sql FROM sqlite_master WHERE type='table' AND name='metric_sources'")
            ).scalar_one()
            assert "ck_metric_sources_type" in ddl
            assert "'fivem'" in ddl
            assert "'network'" not in ddl
            assert "'database'" not in ddl

            with pytest.raises(IntegrityError):
                with engine.begin() as insert_conn:
                    insert_conn.execute(
                        text(
                            """
                            INSERT INTO metric_sources (
                                metric_source_id, project_id, environment_id, source_type, source_ref,
                                display_name, is_enabled, metadata_json
                            ) VALUES (
                                'src_invalid', 'proj_1', NULL, 'network', NULL,
                                'should-fail', 1, '{}'
                            )
                            """
                        )
                    )
    finally:
        container.close()


def test_bootstrap_metric_sources_migration_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "app-data" / "atlas.sqlite3"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}")

    _create_legacy_metric_sources_table(engine)

    bootstrap_schema(engine)
    bootstrap_schema(engine)

    with engine.connect() as conn:
        row_count = conn.execute(text("SELECT COUNT(*) FROM metric_sources")).scalar_one()
        assert row_count == 1
        assert conn.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='metric_sources_old'"
            )
        ).fetchone() is None
