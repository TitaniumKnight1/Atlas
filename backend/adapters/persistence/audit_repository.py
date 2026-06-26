from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select

from backend.adapters.persistence.models import AuditEventRecord, CommandExecutionRecord, CommandPlanRecord, DomainEventRecord
from backend.application.commands import CommandPreview
from backend.domain.shared_kernel import ActorType, AuditRef, DomainEventEnvelope, ProjectId, StableIdentifier
from backend.infrastructure.unit_of_work import RepositoryContext


class AuditRepository:
    def __init__(self, context: RepositoryContext) -> None:
        self._session = context.session
        self._project_id = context.project_id

    def record_plan(
        self,
        *,
        command_plan_id: StableIdentifier,
        preview: CommandPreview,
        status: str,
        project_id: ProjectId | None,
        created_at: datetime,
    ) -> None:
        self._session.add(
            CommandPlanRecord(
                command_plan_id=str(command_plan_id),
                project_id=str(project_id) if project_id else None,
                command_type=preview.command_type,
                status=status,
                risk_level=preview.risk_level.value,
                dry_run_plan_json={"summary": preview.summary, "preview": preview.preview, "warnings": preview.warnings},
                created_at=created_at.isoformat(),
                expires_at=None,
            )
        )

    def record_execution(
        self,
        *,
        command_execution_id: StableIdentifier,
        command_plan_id: StableIdentifier,
        command_type: str,
        status: str,
        project_id: ProjectId | None,
        started_at: datetime,
        finished_at: datetime,
        result: dict[str, Any],
        audit_event_id: StableIdentifier,
        idempotency_key: str | None = None,
    ) -> None:
        self._session.add(
            CommandExecutionRecord(
                command_execution_id=str(command_execution_id),
                command_plan_id=str(command_plan_id),
                project_id=str(project_id) if project_id else None,
                status=status,
                started_at=started_at.isoformat(),
                finished_at=finished_at.isoformat(),
                idempotency_key=idempotency_key,
                result_json={"command_type": command_type, **result},
                audit_event_id=str(audit_event_id),
            )
        )

    def record_audit_event(
        self,
        *,
        audit_event_id: StableIdentifier,
        event_type: str,
        entity_type: str,
        entity_id: str | None,
        summary: str,
        occurred_at: datetime,
        project_id: ProjectId | None,
        details: dict[str, Any] | None = None,
        actor_type: ActorType = ActorType.SYSTEM,
        actor_id: str | None = None,
    ) -> AuditRef:
        self._session.add(
            AuditEventRecord(
                audit_event_id=str(audit_event_id),
                project_id=str(project_id) if project_id else None,
                event_type=event_type,
                entity_type=entity_type,
                entity_id=entity_id,
                actor_type=actor_type.value,
                actor_id=actor_id,
                occurred_at=occurred_at.isoformat(),
                summary=summary,
                details_json=details or {},
            )
        )
        return AuditRef("audit_event", str(audit_event_id))

    def record_domain_event(self, event: DomainEventEnvelope, *, published_at: datetime | None = None) -> None:
        self._session.add(
            DomainEventRecord(
                domain_event_id=str(event.event_id),
                project_id=str(event.project_id) if event.project_id else None,
                event_type=event.event_type,
                aggregate_type=event.aggregate_ref.aggregate_type,
                aggregate_id=event.aggregate_ref.aggregate_id,
                occurred_at=event.occurred_at.isoformat(),
                payload_json=event.payload,
                published_at=published_at.isoformat() if published_at else None,
            )
        )

    def list_audit_events(self, project_id: ProjectId | None = None) -> list[AuditEventRecord]:
        query = select(AuditEventRecord)
        if project_id is not None:
            query = query.where(AuditEventRecord.project_id == str(project_id))
        return list(self._session.execute(query.order_by(AuditEventRecord.occurred_at)).scalars())

    def get_command_execution(self, command_execution_id: str) -> CommandExecutionRecord | None:
        return self._session.get(CommandExecutionRecord, command_execution_id)

    def get_audit_event(self, audit_event_id: str) -> AuditEventRecord | None:
        return self._session.get(AuditEventRecord, audit_event_id)

    def has_undo_execution_since(self, *, project_id: str, since_started_at: str, undo_command_type: str) -> bool:
        query = select(CommandExecutionRecord).where(
            CommandExecutionRecord.project_id == project_id,
            CommandExecutionRecord.started_at >= since_started_at,
            CommandExecutionRecord.status == "succeeded",
        )
        for record in self._session.execute(query).scalars():
            result = record.result_json or {}
            if result.get("command_type") == undo_command_type:
                return True
        return False
