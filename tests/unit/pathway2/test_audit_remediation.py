from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from backend.adapters.persistence.models import AuditEventRecord
from backend.application.pathway2.audit_remediation import (
    remediate_pathway2_audit_undo_secrets,
    seed_leaked_audit_row_for_tests,
    validate_undo_snapshots_available,
)
from backend.infrastructure.di import create_application_container


LEAKED_SECRET = "cfxk_test_production_key_value_123456"


def test_remediate_leaked_prior_content_is_idempotent(tmp_path: Path) -> None:
    app_data = tmp_path / "app-data"
    container = create_application_container(app_data)
    project_id = "project-leak-test"
    audit_event_id = "audit-leak-001"
    try:
        with container.session_factory() as session:
            seed_leaked_audit_row_for_tests(
                session,
                audit_event_id=audit_event_id,
                project_id=project_id,
                secret=LEAKED_SECRET,
            )

        first = remediate_pathway2_audit_undo_secrets(engine=container.engine, app_data_dir=app_data)
        second = remediate_pathway2_audit_undo_secrets(engine=container.engine, app_data_dir=app_data)
        assert first["remediated_audit_rows"] == 1
        assert second["remediated_audit_rows"] == 0

        with container.session_factory() as session:
            record = session.execute(
                select(AuditEventRecord).where(AuditEventRecord.audit_event_id == audit_event_id)
            ).scalar_one()
            blob = json.dumps(record.details_json or {})
            assert LEAKED_SECRET not in blob
            step = record.details_json["undo"]["steps"][0]
            assert step["action_type"] == "restore_path_from_snapshot"
            assert Path(step["snapshot_path"]).exists()
            assert LEAKED_SECRET in Path(step["snapshot_path"]).read_text(encoding="utf-8")
    finally:
        container.close()


def test_migrated_leaked_row_undo_uses_snapshot(tmp_path: Path) -> None:
    app_data = tmp_path / "app-data"
    container = create_application_container(app_data)
    project_id = "project-undo-migrate"
    audit_event_id = "audit-undo-migrate"
    target = tmp_path / "server.cfg"
    target.write_text('sv_licenseKey "after"\n', encoding="utf-8")
    try:
        with container.session_factory() as session:
            session.add(
                AuditEventRecord(
                    audit_event_id=audit_event_id,
                    project_id=None,
                    event_type="PlanRepoNormalization",
                    entity_type="Pathway2Normalization",
                    entity_id=project_id,
                    actor_type="system",
                    actor_id=None,
                    occurred_at="2020-01-01T00:00:00+00:00",
                    summary="legacy normalization",
                    details_json={
                        "result": {"diff": "[REDACTED]"},
                        "undo": {
                            "action_type": "restore_config_file",
                            "project_id": project_id,
                            "absolute_path": str(target),
                            "prior_content": f'sv_licenseKey "{LEAKED_SECRET}"\n',
                        },
                    },
                )
            )
            session.commit()

        remediate_pathway2_audit_undo_secrets(engine=container.engine, app_data_dir=app_data)
        with container.session_factory() as session:
            record = session.execute(
                select(AuditEventRecord).where(AuditEventRecord.audit_event_id == audit_event_id)
            ).scalar_one()
            undo_payload = record.details_json["undo"]
            from backend.application.commands.serialization import compensation_from_storage
            from backend.application.commands import CommandContext
            from backend.adapters.filesystem import LocalSetupFilesystem

            action = compensation_from_storage(undo_payload, filesystem=LocalSetupFilesystem())
            action.apply(CommandContext(uow=None))
            assert target.read_text(encoding="utf-8") == f'sv_licenseKey "{LEAKED_SECRET}"\n'
    finally:
        container.close()


def test_bootstrap_runs_remediation_on_startup(tmp_path: Path) -> None:
    app_data = tmp_path / "app-data"
    engine_container = create_application_container(app_data)
    project_id = "project-bootstrap"
    audit_event_id = "audit-bootstrap-001"
    try:
        with engine_container.session_factory() as session:
            seed_leaked_audit_row_for_tests(
                session,
                audit_event_id=audit_event_id,
                project_id=project_id,
                secret=LEAKED_SECRET,
            )

        restarted = create_application_container(app_data)
        with restarted.session_factory() as session:
            record = session.execute(
                select(AuditEventRecord).where(AuditEventRecord.audit_event_id == audit_event_id)
            ).scalar_one()
            blob = json.dumps(record.details_json or {})
            assert LEAKED_SECRET not in blob
        restarted.close()
    finally:
        engine_container.close()


def test_missing_snapshot_reports_honest_undo_block_reason() -> None:
    reason = validate_undo_snapshots_available(
        {
            "action_type": "restore_path_from_snapshot",
            "snapshot_path": "C:/missing/pathway2-undo/snapshot.cfg.snapshot",
            "target_path": "C:/server/server.cfg",
        }
    )
    assert reason is not None
    assert "Undo snapshot is missing" in reason
