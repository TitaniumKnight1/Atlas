from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from backend.adapters.filesystem.resource_scanner import LocalResourceScanner
from backend.adapters.persistence import AuditRepository, ProjectRepository, ResourceRepository
from backend.application.commands import (
    CommandContext,
    CommandExecutionResult,
    CommandPreview,
    DryRunResult,
    RiskLevel,
    UndoPlan,
)
from backend.application.commands.recorder import CommandAuditRecorder
from backend.application.commands.serialization import compensation_from_storage
from backend.application.resources.rollback_order import compute_rollback_order
from backend.application.resources.service import ResourceApplicationService
from backend.domain.resources.events import (
    resource_rollback_failed,
    resource_rolled_back,
    rollback_batch_completed,
    rollback_batch_halted,
)
from backend.domain.shared_kernel import ErrorCode, ProjectId, StableIdentifier
from backend.infrastructure.unit_of_work import RepositoryContext


class ResourceRollbackError(RuntimeError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class RollbackPlanItem:
    resource_id: str | None
    resource_name: str
    command_execution_id: str
    change_type: str
    reversible: bool
    reversal_summary: str
    warnings: tuple[str, ...] = ()


class ResourceRollbackService:
    """M5c dependency-ordered multi-resource rollback orchestrating M5b composite compensations."""

    def __init__(self, *, container: Any, filesystem: Any, stream_publisher: Any | None = None) -> None:
        self._container = container
        self._filesystem = filesystem
        self._scanner = LocalResourceScanner(filesystem)
        self._resources = ResourceApplicationService(container=container, filesystem=filesystem)
        self._stream_publisher = stream_publisher
        self._recorder = CommandAuditRecorder()

    def preview_rollback_batch(
        self,
        *,
        project_id: ProjectId,
        resource_ids: list[str] | None = None,
        command_execution_ids: list[str] | None = None,
    ) -> CommandPreview:
        plan = self._build_plan(project_id, resource_ids=resource_ids, command_execution_ids=command_execution_ids)
        warnings = list(plan.get("safety_warnings", []))
        for item in plan["items"]:
            warnings.extend(item.get("warnings", []))
            if not item.get("reversible", True):
                warnings.append(f"Resource '{item['resource_name']}' may not be cleanly reversible.")
        if plan.get("order_error"):
            warnings.append(plan["order_error"])
        return CommandPreview(
            "RollbackResourceBatch",
            "Preview dependency-ordered resource rollback batch",
            plan,
            warnings=warnings,
            risk_level=RiskLevel.DESTRUCTIVE,
        )

    def dry_run_rollback_batch(
        self,
        *,
        project_id: ProjectId,
        resource_ids: list[str] | None = None,
        command_execution_ids: list[str] | None = None,
    ) -> DryRunResult:
        preview = self.preview_rollback_batch(
            project_id=project_id,
            resource_ids=resource_ids,
            command_execution_ids=command_execution_ids,
        )
        valid = preview.preview.get("ok", False) and not any(
            "cannot safely roll back" in warning.lower() for warning in preview.warnings
        )
        return DryRunResult(preview.command_type, valid, preview.preview, preview.warnings)

    def execute_rollback_batch(
        self,
        *,
        project_id: ProjectId,
        resource_ids: list[str] | None = None,
        command_execution_ids: list[str] | None = None,
        idempotency_key: str | None = None,
    ) -> CommandExecutionResult:
        dry_run = self.dry_run_rollback_batch(
            project_id=project_id,
            resource_ids=resource_ids,
            command_execution_ids=command_execution_ids,
        )
        if not dry_run.valid:
            raise ResourceRollbackError(ErrorCode.PRECONDITION_FAILED, "Rollback batch dry-run failed validation")
        preview = self.preview_rollback_batch(
            project_id=project_id,
            resource_ids=resource_ids,
            command_execution_ids=command_execution_ids,
        )
        plan = preview.preview
        rollback_run_id = StableIdentifier.new()
        operation_id = StableIdentifier.new()
        now = datetime.now(UTC)
        ordered_items = [
            RollbackPlanItem(
                resource_id=item.get("resource_id"),
                resource_name=item["resource_name"],
                command_execution_id=item["command_execution_id"],
                change_type=item.get("change_type", "unknown"),
                reversible=item.get("reversible", True),
                reversal_summary=item.get("reversal_summary", ""),
                warnings=tuple(item.get("warnings", [])),
            )
            for item in plan["ordered_items"]
        ]
        outcomes: list[dict[str, Any]] = [
            {
                "resource_id": item.resource_id,
                "resource_name": item.resource_name,
                "command_execution_id": item.command_execution_id,
                "status": "pending",
                "position": index,
            }
            for index, item in enumerate(ordered_items)
        ]
        succeeded: list[str] = []
        failed: dict[str, str] | None = None
        events: list[Any] = []

        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(ResourceRepository)
            repository.create_rollback_run(
                rollback_run_id=rollback_run_id,
                project_id=project_id,
                status="running",
                plan_json=plan,
                started_at=now,
            )
            uow.session.flush()
            for index, item in enumerate(ordered_items):
                repository.add_rollback_outcome(
                    outcome_id=StableIdentifier.new(),
                    rollback_run_id=str(rollback_run_id),
                    project_id=project_id,
                    resource_id=item.resource_id,
                    resource_name=item.resource_name,
                    command_execution_id=item.command_execution_id,
                    position=index,
                    status="pending",
                )
            uow.session.flush()

            for index, item in enumerate(ordered_items):
                self._publish_progress(
                    project_id,
                    str(operation_id),
                    f"Rolling back {item.resource_name}",
                    index,
                    len(ordered_items),
                )
                try:
                    undo_plan = self._resolve_undo_plan(uow.repository(AuditRepository), item.command_execution_id)
                    action_result = undo_plan.action.apply(CommandContext(uow=uow))
                    outcomes[index]["status"] = "succeeded"
                    outcomes[index]["result"] = action_result
                    succeeded.append(item.resource_name)
                    if item.resource_id:
                        repository.add_state_change(
                            state_change_id=StableIdentifier.new(),
                            resource_id=item.resource_id,
                            change_type="rollback",
                            from_state=item.change_type,
                            to_state="rolled_back",
                            command_execution_id=item.command_execution_id,
                            changed_at=datetime.now(UTC),
                            details={"rollback_run_id": str(rollback_run_id)},
                        )
                    events.append(resource_rolled_back(project_id, item.resource_id or "", item.resource_name, str(rollback_run_id)))
                except Exception as error:  # noqa: BLE001 - stop-and-hold policy captures error and halts batch
                    error_message = str(error)
                    outcomes[index]["status"] = "failed"
                    outcomes[index]["error"] = error_message
                    failed = {"resource_name": item.resource_name, "error": error_message}
                    for pending_index in range(index + 1, len(ordered_items)):
                        outcomes[pending_index]["status"] = "not_attempted"
                    events.append(
                        resource_rollback_failed(
                            project_id,
                            item.resource_id or "",
                            item.resource_name,
                            str(rollback_run_id),
                            error_message,
                        )
                    )
                    events.append(rollback_batch_halted(project_id, str(rollback_run_id), item.resource_name))
                    break
            else:
                events.append(rollback_batch_completed(project_id, str(rollback_run_id), len(succeeded)))

            final_status = "halted" if failed else "completed"
            result_payload = {
                "project_id": str(project_id),
                "rollback_run_id": str(rollback_run_id),
                "operation_id": str(operation_id),
                "status": final_status,
                "order": [item.resource_name for item in ordered_items],
                "succeeded": succeeded,
                "failed": failed,
                "not_attempted": [item["resource_name"] for item in outcomes if item["status"] == "not_attempted"],
                "outcomes": outcomes,
            }
            for index, outcome in enumerate(outcomes):
                outcome_records = repository.list_rollback_outcomes(str(rollback_run_id))
                if index < len(outcome_records):
                    record = outcome_records[index]
                    record.status = outcome["status"]
                    record.error_message = outcome.get("error")
                    record.outcome_json = {key: value for key, value in outcome.items() if key not in {"status", "error"}}
            execution = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="ResourceRollbackRun",
                entity_id=str(rollback_run_id),
                summary=f"Rollback batch {final_status}",
                result=result_payload,
                events=events,
                undo_plan=None,
                idempotency_key=idempotency_key,
            )
            repository.finish_rollback_run(
                rollback_run_id=str(rollback_run_id),
                status=final_status,
                result_json=result_payload,
                command_execution_id=str(execution.command_execution_id),
                finished_at=datetime.now(UTC),
            )
            uow.commit()
        return execution

    def get_rollback_run(self, project_id: ProjectId, rollback_run_id: str) -> dict[str, Any]:
        with self._container.session_factory() as session:
            repository = ResourceRepository(RepositoryContext(session=session, project_id=project_id))
            run = repository.get_rollback_run(project_id, rollback_run_id)
            if run is None:
                raise ResourceRollbackError(ErrorCode.NOT_FOUND, f"Rollback run not found: {rollback_run_id}")
            outcomes = repository.list_rollback_outcomes(rollback_run_id)
            return {
                "rollback_run_id": run.resource_rollback_run_id,
                "project_id": run.project_id,
                "status": run.status,
                "plan": run.plan_json,
                "result": run.result_json,
                "started_at": run.started_at,
                "finished_at": run.finished_at,
                "outcomes": [_outcome_data(item) for item in outcomes],
            }

    def _build_plan(
        self,
        project_id: ProjectId,
        *,
        resource_ids: list[str] | None,
        command_execution_ids: list[str] | None,
    ) -> dict[str, Any]:
        items = self._resolve_plan_items(project_id, resource_ids=resource_ids, command_execution_ids=command_execution_ids)
        if not items:
            return {"ok": False, "reason": "no undoable resources resolved", "items": [], "ordered_items": []}

        batch_names = [item.resource_name for item in items]
        order_result = self._resources.get_safe_start_order(project_id)
        dep_map = self._dependency_map(project_id)
        rollback_order, order_error = compute_rollback_order(
            batch_names,
            full_start_order=order_result.get("order"),
            dep_map=dep_map,
        )
        if rollback_order is None:
            return {
                "ok": False,
                "order_error": order_error,
                "items": [_plan_item_data(item) for item in items],
                "ordered_items": [],
                "findings": order_result.get("findings", []),
            }

        item_by_name = {item.resource_name: item for item in items}
        ordered_items = [item_by_name[name] for name in rollback_order if name in item_by_name]
        safety_warnings = self._outside_batch_dependent_warnings(project_id, batch_names)
        return {
            "ok": True,
            "project_id": str(project_id),
            "order": rollback_order,
            "ordered_items": [_plan_item_data(item_by_name[name]) for name in rollback_order if name in item_by_name],
            "items": [_plan_item_data(item) for item in items],
            "safety_warnings": safety_warnings,
            "order_error": order_error,
            "findings": order_result.get("findings", []),
        }

    def _resolve_plan_items(
        self,
        project_id: ProjectId,
        *,
        resource_ids: list[str] | None,
        command_execution_ids: list[str] | None,
    ) -> list[RollbackPlanItem]:
        if not resource_ids and not command_execution_ids:
            raise ResourceRollbackError(ErrorCode.VALIDATION_FAILED, "resource_ids or command_execution_ids required")
        items: list[RollbackPlanItem] = []
        seen_executions: set[str] = set()
        with self._container.session_factory() as session:
            audit = AuditRepository(RepositoryContext(session=session, project_id=project_id))
            repository = ResourceRepository(RepositoryContext(session=session, project_id=project_id))
            if command_execution_ids:
                for command_execution_id in command_execution_ids:
                    if command_execution_id in seen_executions:
                        continue
                    seen_executions.add(command_execution_id)
                    items.append(self._plan_item_from_execution(audit, repository, project_id, command_execution_id))
            if resource_ids:
                for resource_id in resource_ids:
                    record = repository.get_resource(project_id, StableIdentifier(resource_id))
                    if record is None:
                        raise ResourceRollbackError(ErrorCode.NOT_FOUND, f"Resource not found: {resource_id}")
                    state = repository.get_latest_undoable_state_change(project_id, resource_id)
                    if state is None or not state.command_execution_id:
                        raise ResourceRollbackError(
                            ErrorCode.PRECONDITION_FAILED,
                            f"No undoable operation found for resource: {record.resource_name}",
                        )
                    if state.command_execution_id in seen_executions:
                        continue
                    seen_executions.add(state.command_execution_id)
                    items.append(self._plan_item_from_execution(audit, repository, project_id, state.command_execution_id))
        return items

    def _plan_item_from_execution(
        self,
        audit: AuditRepository,
        repository: ResourceRepository,
        project_id: ProjectId,
        command_execution_id: str,
    ) -> RollbackPlanItem:
        execution = audit.get_command_execution(command_execution_id)
        if execution is None or execution.project_id != str(project_id):
            raise ResourceRollbackError(ErrorCode.NOT_FOUND, f"Command execution not found: {command_execution_id}")
        if execution.status != "succeeded":
            raise ResourceRollbackError(ErrorCode.PRECONDITION_FAILED, f"Command execution {command_execution_id} is not undoable")
        audit_event = audit.get_audit_event(execution.audit_event_id) if execution.audit_event_id else None
        undo_payload = (audit_event.details_json or {}).get("undo") if audit_event else None
        if not undo_payload:
            raise ResourceRollbackError(ErrorCode.PRECONDITION_FAILED, f"Command execution {command_execution_id} has no undo payload")
        result = execution.result_json or {}
        resource_id = result.get("resource_id")
        resource_name = result.get("resource_name") or "unknown"
        if resource_id:
            record = repository.get_resource(project_id, StableIdentifier(str(resource_id)))
            if record is not None:
                resource_name = record.resource_name
        reversible = True
        warnings: list[str] = []
        if undo_payload.get("action_type") == "composite_compensation":
            for step in undo_payload.get("steps", []):
                if step.get("action_type") == "restore_path_from_snapshot":
                    reversible = True
        try:
            compensation_from_storage(undo_payload, filesystem=self._filesystem)
        except Exception as error:  # noqa: BLE001
            reversible = False
            warnings.append(f"Stored undo payload is not restorable: {error}")
        return RollbackPlanItem(
            resource_id=str(resource_id) if resource_id else None,
            resource_name=str(resource_name),
            command_execution_id=command_execution_id,
            change_type=str((audit_event.details_json or {}).get("result", {}).get("command_type", "unknown")),
            reversible=reversible,
            reversal_summary=str(audit_event.summary if audit_event else "Reverse resource operation"),
            warnings=tuple(warnings),
        )

    def _resolve_undo_plan(self, audit: AuditRepository, command_execution_id: str) -> UndoPlan:
        execution = audit.get_command_execution(command_execution_id)
        if execution is None:
            raise ResourceRollbackError(ErrorCode.NOT_FOUND, f"Command execution not found: {command_execution_id}")
        audit_event = audit.get_audit_event(execution.audit_event_id) if execution.audit_event_id else None
        if audit_event is None:
            raise ResourceRollbackError(ErrorCode.PRECONDITION_FAILED, "Missing audit record for undo")
        undo_payload = (audit_event.details_json or {}).get("undo")
        if not undo_payload:
            raise ResourceRollbackError(ErrorCode.PRECONDITION_FAILED, "Command execution is not undoable")
        action = compensation_from_storage(undo_payload, filesystem=self._filesystem)
        return UndoPlan(
            command_type="RollbackResourceStep",
            summary=f"Reverse command execution {command_execution_id}",
            action=action,
            payload=undo_payload,
        )

    def _dependency_map(self, project_id: ProjectId) -> dict[str, list[str]]:
        with self._container.session_factory() as session:
            repository = ResourceRepository(RepositoryContext(session=session, project_id=project_id))
            records = repository.list_resources(project_id)
            dependencies = repository.list_dependencies(project_id)
        id_to_name = {record.resource_id: record.resource_name for record in records}
        dep_map: dict[str, list[str]] = {record.resource_name: [] for record in records}
        for dep in dependencies:
            source = id_to_name.get(dep.source_resource_id)
            if source is None:
                continue
            dep_map.setdefault(source, []).append(dep.target_name)
        return dep_map

    def _outside_batch_dependent_warnings(self, project_id: ProjectId, batch_names: list[str]) -> list[str]:
        batch_set = set(batch_names)
        server_cfg_content = self._server_cfg_binding(project_id)
        enabled_map = self._scanner.parse_server_cfg_enabled(server_cfg_content)
        warnings: list[str] = []
        with self._container.session_factory() as session:
            repository = ResourceRepository(RepositoryContext(session=session, project_id=project_id))
            for name in batch_names:
                record = repository.get_resource_by_name(project_id, name)
                if record is None:
                    continue
                dependents = self._resources.get_resource_dependents(project_id, record.resource_id, transitive=False)
                outside = [dependent for dependent in dependents if dependent not in batch_set and enabled_map.get(dependent)]
                if outside:
                    warnings.append(
                        f"Cannot safely roll back '{name}': enabled dependents outside batch rely on it: {', '.join(outside)}"
                    )
        return warnings

    def _server_cfg_binding(self, project_id: ProjectId) -> str:
        view = self._container.create_config_service().list_config_files(project_id)
        server_cfg = next((item for item in view if item["path"].endswith("server.cfg")), None)
        if server_cfg is None:
            return ""
        content = self._container.create_config_service().get_config_file_view(project_id, server_cfg["config_file_id"]).get("content")
        return content or ""

    def _publish_progress(
        self,
        project_id: ProjectId,
        operation_id: str,
        message: str,
        index: int,
        total: int,
    ) -> None:
        if self._stream_publisher is None:
            return
        self._stream_publisher.publish_operation_progress(
            project_id=project_id,
            operation_id=operation_id,
            message=message,
            bytes_received=index + 1,
            total_bytes=total,
            step_key=f"rollback_{index}",
        )

    def _item_from_plan(self, item: dict[str, Any]) -> dict[str, Any]:
        return item


def _plan_item_data(item: RollbackPlanItem) -> dict[str, Any]:
    return {
        "resource_id": item.resource_id,
        "resource_name": item.resource_name,
        "command_execution_id": item.command_execution_id,
        "change_type": item.change_type,
        "reversible": item.reversible,
        "reversal_summary": item.reversal_summary,
        "warnings": list(item.warnings),
    }


def _outcome_data(record: Any) -> dict[str, Any]:
    return {
        "resource_rollback_outcome_id": record.resource_rollback_outcome_id,
        "resource_id": record.resource_id,
        "resource_name": record.resource_name,
        "command_execution_id": record.command_execution_id,
        "position": record.position,
        "status": record.status,
        "error_message": record.error_message,
        "outcome_json": record.outcome_json or {},
    }
