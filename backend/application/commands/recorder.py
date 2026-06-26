from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from backend.adapters.persistence import AuditRepository
from backend.application.commands import CommandExecutionResult, CommandPreview, UndoPlan
from backend.domain.shared_kernel import ActorType, AuditRef, DomainEventEnvelope, ProjectId, StableIdentifier
from backend.infrastructure.unit_of_work import SingleWriterSQLiteUnitOfWork


class CommandAuditRecorder:
    """Records command plan/execution/audit rows inside the caller's Unit of Work."""

    def record_success(
        self,
        *,
        uow: SingleWriterSQLiteUnitOfWork,
        preview: CommandPreview,
        project_id: ProjectId | None,
        entity_type: str,
        entity_id: str | None,
        summary: str,
        result: dict[str, Any],
        events: list[DomainEventEnvelope],
        undo_plan: UndoPlan | None = None,
        idempotency_key: str | None = None,
    ) -> CommandExecutionResult:
        now = datetime.now(UTC)
        uow.session.flush()
        plan_id = StableIdentifier.new()
        execution_id = StableIdentifier.new()
        audit_event_id = StableIdentifier.new()
        audit_repository = uow.repository(AuditRepository)
        audit_repository.record_plan(
            command_plan_id=plan_id,
            preview=preview,
            status="approved",
            project_id=project_id,
            created_at=now,
        )
        audit_ref = audit_repository.record_audit_event(
            audit_event_id=audit_event_id,
            event_type=preview.command_type,
            entity_type=entity_type,
            entity_id=entity_id,
            summary=summary,
            occurred_at=now,
            project_id=project_id,
            details={"result": result, "undo": undo_plan.payload if undo_plan else None},
            actor_type=ActorType.SYSTEM,
        )
        uow.session.flush()
        audit_repository.record_execution(
            command_execution_id=execution_id,
            command_plan_id=plan_id,
            command_type=preview.command_type,
            status="succeeded",
            project_id=project_id,
            started_at=now,
            finished_at=datetime.now(UTC),
            result=result,
            audit_event_id=audit_event_id,
            idempotency_key=idempotency_key,
        )
        for event in events:
            audit_repository.record_domain_event(event, published_at=datetime.now(UTC))
            uow.collect_event(event)
        return CommandExecutionResult(
            command_type=preview.command_type,
            command_plan_id=plan_id,
            command_execution_id=execution_id,
            audit_ref=AuditRef(audit_ref.ref_type, audit_ref.ref_id),
            result=result,
            undo_plan=undo_plan,
            project_id=project_id,
        )
