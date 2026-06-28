from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.adapters.persistence.models import AuditEventRecord
from backend.domain.shared_kernel import ProjectId

_REDACTION_MARKERS = frozenset({"[stored locally]", "[redacted]", "[redacted-local]"})
_PATHWAY2_ENTITY_TYPES = frozenset(
    {
        "Pathway2Normalization",
        "Pathway2Substitution",
        "Pathway2DevSecret",
    }
)


def remediate_pathway2_audit_undo_secrets(*, engine: Engine, app_data_dir: Path) -> dict[str, int]:
    """Move inline undo prior_content out of audit rows into local snapshots (idempotent)."""
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    remediated = 0
    with session_factory() as session:
        for record in session.execute(select(AuditEventRecord)).scalars():
            details = record.details_json or {}
            undo = details.get("undo")
            if not isinstance(undo, dict):
                continue
            if record.entity_type not in _PATHWAY2_ENTITY_TYPES and not _undo_payload_has_inline_content(undo):
                continue
            project_id = record.project_id or undo.get("project_id")
            new_undo, changed = _remediate_undo_payload(
                undo,
                app_data_dir=app_data_dir,
                audit_event_id=record.audit_event_id,
                project_id=str(project_id) if project_id else None,
            )
            if not changed:
                continue
            updated = deepcopy(details)
            updated["undo"] = new_undo
            record.details_json = updated
            remediated += 1
        if remediated:
            session.commit()
    return {"remediated_audit_rows": remediated}


def assert_undo_storage_is_secret_free(payload: dict[str, Any]) -> None:
    """Fail fast if a pathway2 undo payload would persist raw config content in audit."""
    if payload.get("action_type") == "composite_compensation":
        for step in payload.get("steps", []):
            assert_undo_storage_is_secret_free(step)
        return
    if payload.get("action_type") == "restore_config_file" and payload.get("prior_content") not in (None, *_REDACTION_MARKERS):
        raise ValueError("Pathway2 undo must not store inline prior_content in audit rows")


def validate_undo_snapshots_available(payload: dict[str, Any]) -> str | None:
    """Return an honest block reason when file snapshots required for undo are missing."""
    if payload.get("action_type") == "composite_compensation":
        for step in payload.get("steps", []):
            reason = validate_undo_snapshots_available(step)
            if reason:
                return reason
        return None
    if payload.get("action_type") != "restore_path_from_snapshot":
        return None
    snapshot_path = payload.get("snapshot_path")
    if not snapshot_path or not Path(str(snapshot_path)).exists():
        return (
            "Undo snapshot is missing. This command was recorded before Atlas moved undo data "
            "out of the audit log, and no local snapshot was preserved. Restore from backup or re-apply the change."
        )
    return None


def _undo_payload_has_inline_content(payload: dict[str, Any]) -> bool:
    if payload.get("action_type") == "composite_compensation":
        return any(_undo_payload_has_inline_content(step) for step in payload.get("steps", []))
    return _step_has_inline_prior_content(payload)


def _step_has_inline_prior_content(step: dict[str, Any]) -> bool:
    if step.get("action_type") != "restore_config_file":
        return False
    prior = step.get("prior_content")
    return isinstance(prior, str) and bool(prior) and prior not in _REDACTION_MARKERS


def _remediate_undo_payload(
    payload: dict[str, Any],
    *,
    app_data_dir: Path,
    audit_event_id: str,
    project_id: str | None,
) -> tuple[dict[str, Any], bool]:
    if payload.get("action_type") == "composite_compensation":
        steps: list[dict[str, Any]] = []
        changed = False
        for step in payload.get("steps", []):
            new_step, step_changed = _remediate_undo_step(
                step,
                app_data_dir=app_data_dir,
                audit_event_id=audit_event_id,
                project_id=project_id,
            )
            steps.append(new_step)
            changed = changed or step_changed
        return {**payload, "steps": steps}, changed
    return _remediate_undo_step(
        payload,
        app_data_dir=app_data_dir,
        audit_event_id=audit_event_id,
        project_id=project_id,
    )


def _remediate_undo_step(
    step: dict[str, Any],
    *,
    app_data_dir: Path,
    audit_event_id: str,
    project_id: str | None,
) -> tuple[dict[str, Any], bool]:
    if not _step_has_inline_prior_content(step):
        return step, False
    prior_content = str(step["prior_content"])
    target_path = Path(str(step["absolute_path"]))
    snapshot_path = _migrated_snapshot_path(
        app_data_dir=app_data_dir,
        project_id=project_id,
        audit_event_id=audit_event_id,
        target_path=target_path,
    )
    if not snapshot_path.exists():
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(prior_content, encoding="utf-8")
    return {
        "action_type": "restore_path_from_snapshot",
        "snapshot_path": str(snapshot_path),
        "target_path": str(step["absolute_path"]),
    }, True


def _migrated_snapshot_path(
    *,
    app_data_dir: Path,
    project_id: str | None,
    audit_event_id: str,
    target_path: Path,
) -> Path:
    owner = project_id or "unknown"
    return app_data_dir / "pathway2-undo" / owner / "migrated" / audit_event_id / f"{target_path.name}.snapshot"


def seed_leaked_audit_row_for_tests(session: Session, *, audit_event_id: str, project_id: str, secret: str) -> None:
    """Test helper: simulate old P2-1 inline prior_content in audit."""
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
                    "action_type": "composite_compensation",
                    "project_id": project_id,
                    "steps": [
                        {
                            "action_type": "restore_config_file",
                            "absolute_path": "C:\\server\\server.cfg",
                            "prior_content": f'sv_licenseKey "{secret}"\n',
                        }
                    ],
                },
            },
        )
    )
    session.commit()
