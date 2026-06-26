from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select

from backend.adapters.persistence.models import (
    AutomationActionRecord,
    AutomationConditionRecord,
    AutomationIdempotencyKeyRecord,
    AutomationRunRecord,
    AutomationRunStepRecord,
    AutomationScheduleRecord,
    AutomationSettingRecord,
    AutomationTriggerRecord,
    AutomationWorkflowRecord,
    AutomationWorkflowVersionRecord,
)
from backend.domain.automation.types import AutomationSettingKey, RunStatus
from backend.domain.shared_kernel import ProjectId, StableIdentifier
from backend.infrastructure.unit_of_work import ProjectScopeRequired, RepositoryContext


class AutomationRepository:
    def __init__(self, context: RepositoryContext) -> None:
        self._session = context.session
        self._project_id = context.project_id

    def get_global_enabled(self) -> bool:
        record = self._session.get(AutomationSettingRecord, AutomationSettingKey.GLOBAL_ENABLED.value)
        if record is None:
            return True
        return bool(record.setting_value_json.get("enabled", True))

    def set_global_enabled(self, *, enabled: bool, updated_at: datetime) -> dict[str, Any]:
        record = self._session.get(AutomationSettingRecord, AutomationSettingKey.GLOBAL_ENABLED.value)
        payload = {"enabled": enabled}
        if record is None:
            self._session.add(
                AutomationSettingRecord(
                    setting_key=AutomationSettingKey.GLOBAL_ENABLED.value,
                    setting_value_json=payload,
                    updated_at=updated_at.isoformat(),
                )
            )
        else:
            record.setting_value_json = payload
            record.updated_at = updated_at.isoformat()
        return payload

    def create_workflow(
        self,
        *,
        workflow_id: StableIdentifier,
        project_id: ProjectId,
        name: str,
        description: str | None,
        is_enabled: bool,
        created_at: datetime,
    ) -> AutomationWorkflowRecord:
        self._ensure_project_scope(project_id)
        record = AutomationWorkflowRecord(
            automation_workflow_id=str(workflow_id),
            project_id=str(project_id),
            name=name,
            description=description,
            is_enabled=1 if is_enabled else 0,
            created_at=created_at.isoformat(),
            updated_at=created_at.isoformat(),
        )
        self._session.add(record)
        return record

    def get_workflow(self, project_id: ProjectId, workflow_id: str) -> AutomationWorkflowRecord | None:
        self._ensure_project_scope(project_id)
        return self._session.execute(
            select(AutomationWorkflowRecord).where(
                AutomationWorkflowRecord.project_id == str(project_id),
                AutomationWorkflowRecord.automation_workflow_id == workflow_id,
            )
        ).scalar_one_or_none()

    def list_workflows(self, project_id: ProjectId) -> list[AutomationWorkflowRecord]:
        self._ensure_project_scope(project_id)
        return list(
            self._session.execute(
                select(AutomationWorkflowRecord)
                .where(AutomationWorkflowRecord.project_id == str(project_id))
                .order_by(AutomationWorkflowRecord.name)
            ).scalars()
        )

    def set_workflow_enabled(self, workflow: AutomationWorkflowRecord, *, is_enabled: bool, updated_at: datetime) -> None:
        workflow.is_enabled = 1 if is_enabled else 0
        workflow.updated_at = updated_at.isoformat()

    def set_workflow_current_version(self, workflow: AutomationWorkflowRecord, version_id: str) -> None:
        workflow.current_version_id = version_id

    def create_version(
        self,
        *,
        version_id: StableIdentifier,
        workflow_id: str,
        project_id: ProjectId,
        version_number: int,
        created_at: datetime,
    ) -> AutomationWorkflowVersionRecord:
        self._ensure_project_scope(project_id)
        record = AutomationWorkflowVersionRecord(
            automation_workflow_version_id=str(version_id),
            automation_workflow_id=workflow_id,
            project_id=str(project_id),
            version_number=version_number,
            created_at=created_at.isoformat(),
        )
        self._session.add(record)
        return record

    def get_version(self, project_id: ProjectId, version_id: str) -> AutomationWorkflowVersionRecord | None:
        self._ensure_project_scope(project_id)
        return self._session.execute(
            select(AutomationWorkflowVersionRecord).where(
                AutomationWorkflowVersionRecord.project_id == str(project_id),
                AutomationWorkflowVersionRecord.automation_workflow_version_id == version_id,
            )
        ).scalar_one_or_none()

    def create_trigger(
        self,
        *,
        trigger_id: StableIdentifier,
        version_id: str,
        project_id: ProjectId,
        trigger_type: str,
        config_json: dict[str, Any] | None,
    ) -> AutomationTriggerRecord:
        self._ensure_project_scope(project_id)
        record = AutomationTriggerRecord(
            automation_trigger_id=str(trigger_id),
            automation_workflow_version_id=version_id,
            project_id=str(project_id),
            trigger_type=trigger_type,
            config_json=config_json or {},
        )
        self._session.add(record)
        return record

    def create_condition(
        self,
        *,
        condition_id: StableIdentifier,
        version_id: str,
        project_id: ProjectId,
        condition_type: str,
        config_json: dict[str, Any] | None,
        position: int,
    ) -> AutomationConditionRecord:
        self._ensure_project_scope(project_id)
        record = AutomationConditionRecord(
            automation_condition_id=str(condition_id),
            automation_workflow_version_id=version_id,
            project_id=str(project_id),
            condition_type=condition_type,
            config_json=config_json or {},
            position=position,
        )
        self._session.add(record)
        return record

    def create_action(
        self,
        *,
        action_id: StableIdentifier,
        version_id: str,
        project_id: ProjectId,
        action_type: str,
        safety_class: str,
        config_json: dict[str, Any] | None,
        position: int,
    ) -> AutomationActionRecord:
        self._ensure_project_scope(project_id)
        record = AutomationActionRecord(
            automation_action_id=str(action_id),
            automation_workflow_version_id=version_id,
            project_id=str(project_id),
            action_type=action_type,
            safety_class=safety_class,
            config_json=config_json or {},
            position=position,
        )
        self._session.add(record)
        return record

    def create_schedule(
        self,
        *,
        schedule_id: StableIdentifier,
        workflow_id: str,
        project_id: ProjectId,
        schedule_json: dict[str, Any],
        next_run_at: datetime,
        is_enabled: bool,
    ) -> AutomationScheduleRecord:
        self._ensure_project_scope(project_id)
        record = AutomationScheduleRecord(
            automation_schedule_id=str(schedule_id),
            automation_workflow_id=workflow_id,
            project_id=str(project_id),
            schedule_json=schedule_json,
            next_run_at=next_run_at.isoformat(),
            is_enabled=1 if is_enabled else 0,
        )
        self._session.add(record)
        return record

    def get_schedule(self, project_id: ProjectId, schedule_id: str) -> AutomationScheduleRecord | None:
        self._ensure_project_scope(project_id)
        return self._session.execute(
            select(AutomationScheduleRecord).where(
                AutomationScheduleRecord.project_id == str(project_id),
                AutomationScheduleRecord.automation_schedule_id == schedule_id,
            )
        ).scalar_one_or_none()

    def list_due_schedules(self, *, before: datetime) -> list[AutomationScheduleRecord]:
        return list(
            self._session.execute(
                select(AutomationScheduleRecord)
                .where(
                    AutomationScheduleRecord.is_enabled == 1,
                    AutomationScheduleRecord.next_run_at <= before.isoformat(),
                )
                .order_by(AutomationScheduleRecord.next_run_at)
            ).scalars()
        )

    def advance_schedule(self, schedule: AutomationScheduleRecord, *, next_run_at: datetime, last_run_at: datetime) -> None:
        schedule.next_run_at = next_run_at.isoformat()
        schedule.last_run_at = last_run_at.isoformat()

    def list_enabled_event_workflows(self, project_id: ProjectId, trigger_type: str) -> list[tuple[AutomationWorkflowRecord, AutomationWorkflowVersionRecord]]:
        self._ensure_project_scope(project_id)
        rows = self._session.execute(
            select(AutomationWorkflowRecord, AutomationWorkflowVersionRecord, AutomationTriggerRecord)
            .join(
                AutomationWorkflowVersionRecord,
                AutomationWorkflowVersionRecord.automation_workflow_version_id == AutomationWorkflowRecord.current_version_id,
            )
            .join(
                AutomationTriggerRecord,
                AutomationTriggerRecord.automation_workflow_version_id == AutomationWorkflowVersionRecord.automation_workflow_version_id,
            )
            .where(
                AutomationWorkflowRecord.project_id == str(project_id),
                AutomationWorkflowRecord.is_enabled == 1,
                AutomationTriggerRecord.trigger_type == trigger_type,
            )
        ).all()
        return [(workflow, version) for workflow, version, _trigger in rows]

    def list_conditions(self, version_id: str) -> list[AutomationConditionRecord]:
        return list(
            self._session.execute(
                select(AutomationConditionRecord)
                .where(AutomationConditionRecord.automation_workflow_version_id == version_id)
                .order_by(AutomationConditionRecord.position)
            ).scalars()
        )

    def list_actions(self, version_id: str) -> list[AutomationActionRecord]:
        return list(
            self._session.execute(
                select(AutomationActionRecord)
                .where(AutomationActionRecord.automation_workflow_version_id == version_id)
                .order_by(AutomationActionRecord.position)
            ).scalars()
        )

    def record_idempotency_key(
        self,
        *,
        claim_id: StableIdentifier,
        project_id: ProjectId,
        idempotency_key: str,
        automation_run_id: str,
        created_at: datetime,
    ) -> None:
        self._ensure_project_scope(project_id)
        self._session.add(
            AutomationIdempotencyKeyRecord(
                automation_idempotency_key_id=str(claim_id),
                project_id=str(project_id),
                idempotency_key=idempotency_key,
                automation_run_id=automation_run_id,
                created_at=created_at.isoformat(),
            )
        )

    def get_run_by_idempotency_key(self, idempotency_key: str) -> AutomationRunRecord | None:
        return self._session.execute(
            select(AutomationRunRecord).where(AutomationRunRecord.idempotency_key == idempotency_key)
        ).scalar_one_or_none()

    def create_run(
        self,
        *,
        run_id: StableIdentifier,
        project_id: ProjectId,
        workflow_id: str,
        version_id: str,
        trigger_type: str,
        status: str,
        idempotency_key: str,
        trigger_payload: dict[str, Any] | None,
        started_at: datetime,
        summary: str | None = None,
    ) -> AutomationRunRecord:
        self._ensure_project_scope(project_id)
        record = AutomationRunRecord(
            automation_run_id=str(run_id),
            project_id=str(project_id),
            automation_workflow_id=workflow_id,
            automation_workflow_version_id=version_id,
            trigger_type=trigger_type,
            status=status,
            idempotency_key=idempotency_key,
            trigger_payload_json=trigger_payload or {},
            started_at=started_at.isoformat(),
            summary=summary,
        )
        self._session.add(record)
        return record

    def finish_run(self, run: AutomationRunRecord, *, status: str, finished_at: datetime, summary: str | None = None) -> None:
        run.status = status
        run.finished_at = finished_at.isoformat()
        if summary is not None:
            run.summary = summary

    def list_runs(self, project_id: ProjectId, *, limit: int = 50) -> list[AutomationRunRecord]:
        self._ensure_project_scope(project_id)
        return list(
            self._session.execute(
                select(AutomationRunRecord)
                .where(AutomationRunRecord.project_id == str(project_id))
                .order_by(AutomationRunRecord.started_at.desc())
                .limit(limit)
            ).scalars()
        )

    def get_run(self, project_id: ProjectId, run_id: str) -> AutomationRunRecord | None:
        self._ensure_project_scope(project_id)
        return self._session.execute(
            select(AutomationRunRecord).where(
                AutomationRunRecord.project_id == str(project_id),
                AutomationRunRecord.automation_run_id == run_id,
            )
        ).scalar_one_or_none()

    def create_run_step(
        self,
        *,
        step_id: StableIdentifier,
        run_id: str,
        project_id: ProjectId,
        action_id: str,
        position: int,
        status: str,
        result_json: dict[str, Any] | None = None,
        undo_plan_json: dict[str, Any] | None = None,
        command_execution_id: str | None = None,
    ) -> AutomationRunStepRecord:
        self._ensure_project_scope(project_id)
        record = AutomationRunStepRecord(
            automation_run_step_id=str(step_id),
            automation_run_id=run_id,
            project_id=str(project_id),
            automation_action_id=action_id,
            position=position,
            status=status,
            result_json=result_json or {},
            undo_plan_json=undo_plan_json,
            command_execution_id=command_execution_id,
        )
        self._session.add(record)
        return record

    def list_run_steps(self, run_id: str) -> list[AutomationRunStepRecord]:
        return list(
            self._session.execute(
                select(AutomationRunStepRecord)
                .where(AutomationRunStepRecord.automation_run_id == run_id)
                .order_by(AutomationRunStepRecord.position)
            ).scalars()
        )

    def get_run_step(self, project_id: ProjectId, step_id: str) -> AutomationRunStepRecord | None:
        self._ensure_project_scope(project_id)
        return self._session.execute(
            select(AutomationRunStepRecord).where(
                AutomationRunStepRecord.project_id == str(project_id),
                AutomationRunStepRecord.automation_run_step_id == step_id,
            )
        ).scalar_one_or_none()

    def _ensure_project_scope(self, project_id: ProjectId) -> None:
        if self._project_id is not None and self._project_id != project_id:
            raise ProjectScopeRequired("Repository project scope does not match requested project_id")
