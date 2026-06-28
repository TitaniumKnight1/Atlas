from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

from backend.adapters.persistence import AuditRepository, ProjectRepository
from backend.application.commands import CommandExecutionResult, CommandPreview, DryRunResult, RiskLevel, UndoPlan
from backend.application.commands.recorder import CommandAuditRecorder
from backend.application.dev_db.compensation import ClearDevDatabaseSettingsCompensation, RestoreDevDatabaseSettingsCompensation
from backend.domain.dev_db import (
    DevDatabasePort,
    DockerAvailabilityPort,
    DockerAvailabilityState,
    DevDatabaseAdapterError,
    DevDatabaseLifecycleStatus,
    DevDatabasePlan,
    DevDatabaseRuntimeStatus,
    bring_your_own_mysql_message,
    build_dev_db_port_available_check,
    dev_db_connection_string,
    wait_for_mysql_ready,
)
from backend.domain.pathway2.settings import Pathway2SettingKeys
from backend.domain.shared_kernel import ErrorCode, ProjectId, StableIdentifier
from backend.infrastructure.unit_of_work import RepositoryContext, SingleWriterSQLiteUnitOfWork


class DevDatabaseApplicationError(RuntimeError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


_DEV_DB_SETTING_KEYS = (
    Pathway2SettingKeys.DEV_DB_ENGINE,
    Pathway2SettingKeys.DEV_DB_CONTAINER_ID,
    Pathway2SettingKeys.DEV_DB_CONTAINER_NAME,
    Pathway2SettingKeys.DEV_DB_VOLUME_NAME,
    Pathway2SettingKeys.DEV_DB_STATUS,
    Pathway2SettingKeys.DEV_DB_MYSQL_REACHABLE,
    Pathway2SettingKeys.DEV_DB_ROOT_PASSWORD,
)


class DevDatabaseApplicationService:
    def __init__(
        self,
        *,
        container: Any,
        dev_db_port: DevDatabasePort,
        docker_probe: DockerAvailabilityPort,
    ) -> None:
        self._container = container
        self._dev_db_port = dev_db_port
        self._docker_probe = docker_probe
        self._recorder = CommandAuditRecorder()

    def get_dev_database_status(self, *, project_id: ProjectId) -> dict[str, Any]:
        plan = self._dev_db_port.build_plan(str(project_id))
        runtime = self._dev_db_port.inspect(plan)
        stored = self._read_dev_db_settings(project_id)
        if runtime.lifecycle == DevDatabaseLifecycleStatus.ABSENT and stored:
            self._heal_absent_settings(project_id)
            stored = {}
        payload = _public_status(runtime, plan)
        payload["stored_settings_present"] = bool(stored.get(Pathway2SettingKeys.DEV_DB_CONTAINER_NAME))
        return payload

    def preview_provision_dev_database(self, *, project_id: ProjectId) -> CommandPreview:
        plan = self._dev_db_port.build_plan(str(project_id))
        probe = self._docker_probe.probe()
        port_check = build_dev_db_port_available_check(plan.host, plan.port)
        warnings = _provision_warnings(probe, port_check)
        return CommandPreview(
            "ProvisionDevDatabase",
            f"Provision local MySQL dev database for project {project_id}",
            {
                "project_id": str(project_id),
                "plan": _plan_preview(plan),
                "docker_state": probe.state.value,
                "port_check": port_check,
                "connection_string": plan.connection_string,
            },
            warnings=warnings,
            risk_level=RiskLevel.HIGH,
        )

    def dry_run_provision_dev_database(self, *, project_id: ProjectId) -> DryRunResult:
        preview = self.preview_provision_dev_database(project_id=project_id)
        valid = len(preview.warnings) == 0
        return DryRunResult(preview.command_type, valid, preview.preview, preview.warnings)

    def execute_provision_dev_database(self, *, project_id: ProjectId, idempotency_key: str | None = None) -> CommandExecutionResult:
        preview = self.preview_provision_dev_database(project_id=project_id)
        dry_run = self.dry_run_provision_dev_database(project_id=project_id)
        if not dry_run.valid:
            raise DevDatabaseApplicationError(
                ErrorCode.PRECONDITION_FAILED,
                dry_run.warnings[0] if dry_run.warnings else "Dev database provisioning preconditions failed",
            )

        plan = self._dev_db_port.build_plan(str(project_id))
        root_password = secrets.token_urlsafe(24)

        try:
            self._dev_db_port.pull_image(plan)
            runtime = self._dev_db_port.provision(plan, root_password=root_password)
            _, mysql_reachable = wait_for_mysql_ready(plan.host, plan.port)
            runtime = self._dev_db_port.inspect(plan)
            if mysql_reachable:
                runtime = DevDatabaseRuntimeStatus(
                    lifecycle=DevDatabaseLifecycleStatus.REACHABLE,
                    engine=runtime.engine,
                    container_id=runtime.container_id,
                    container_name=runtime.container_name,
                    volume_name=runtime.volume_name,
                    docker_state=runtime.docker_state,
                    container_running=runtime.container_running,
                    mysql_reachable=True,
                    connection_string=runtime.connection_string,
                    message=f"MySQL reachable at {plan.host}:{plan.port}.",
                )
        except DevDatabaseAdapterError as error:
            self._dev_db_port.remove(plan, remove_volume=False)
            raise DevDatabaseApplicationError(
                ErrorCode.EXTERNAL_ADAPTER_FAILED,
                str(error),
            ) from error

        settings_patch = _settings_patch_from_runtime(runtime, root_password=root_password)
        undo_payload = _remove_undo_payload(project_id, plan, remove_volume=False)
        compensation = ClearDevDatabaseSettingsCompensation(str(project_id))

        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            self._require_project(uow.repository(ProjectRepository), project_id)
            self._upsert_settings(uow, project_id, settings_patch)
            result = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="DevDatabase",
                entity_id=str(project_id),
                summary="Provisioned local MySQL dev database container",
                result={
                    "project_id": str(project_id),
                    "plan": _plan_preview(plan),
                    "status": _public_status(runtime, plan),
                    "connection_string": plan.connection_string,
                },
                events=[],
                undo_plan=UndoPlan(
                    "UndoProvisionDevDatabase",
                    "Remove dev database container (keep named volume)",
                    compensation,
                    undo_payload,
                ),
                idempotency_key=idempotency_key,
            )
            uow.commit()
            return result

    def preview_start_dev_database(self, *, project_id: ProjectId) -> CommandPreview:
        plan = self._dev_db_port.build_plan(str(project_id))
        runtime = self._dev_db_port.inspect(plan)
        return CommandPreview(
            "StartDevDatabase",
            f"Start dev database container {plan.container_name}",
            {"project_id": str(project_id), "plan": _plan_preview(plan), "current_status": _public_status(runtime, plan)},
            risk_level=RiskLevel.MEDIUM,
        )

    def execute_start_dev_database(self, *, project_id: ProjectId, idempotency_key: str | None = None) -> CommandExecutionResult:
        preview = self.preview_start_dev_database(project_id=project_id)
        plan = self._dev_db_port.build_plan(str(project_id))
        prior_settings = self._read_dev_db_settings(project_id)
        try:
            runtime = self._dev_db_port.start(plan)
            _, mysql_reachable = wait_for_mysql_ready(plan.host, plan.port, timeout_seconds=30.0)
            runtime = self._dev_db_port.inspect(plan)
            if mysql_reachable:
                runtime = DevDatabaseRuntimeStatus(
                    lifecycle=DevDatabaseLifecycleStatus.REACHABLE,
                    engine=runtime.engine,
                    container_id=runtime.container_id,
                    container_name=runtime.container_name,
                    volume_name=runtime.volume_name,
                    docker_state=runtime.docker_state,
                    container_running=True,
                    mysql_reachable=True,
                    connection_string=runtime.connection_string,
                    message=f"MySQL reachable at {plan.host}:{plan.port}.",
                )
        except DevDatabaseAdapterError as error:
            raise DevDatabaseApplicationError(ErrorCode.EXTERNAL_ADAPTER_FAILED, str(error)) from error

        settings_patch = _settings_patch_from_runtime(runtime, root_password=prior_settings.get(Pathway2SettingKeys.DEV_DB_ROOT_PASSWORD))
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            self._require_project(uow.repository(ProjectRepository), project_id)
            self._upsert_settings(uow, project_id, settings_patch)
            result = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="DevDatabase",
                entity_id=str(project_id),
                summary=f"Started dev database container {plan.container_name}",
                result={"project_id": str(project_id), "status": _public_status(runtime, plan)},
                events=[],
                undo_plan=UndoPlan(
                    "UndoStartDevDatabase",
                    f"Stop dev database container {plan.container_name}",
                    RestoreDevDatabaseSettingsCompensation(str(project_id), prior_settings),
                    _stop_undo_payload(project_id, plan, prior_settings),
                ),
                idempotency_key=idempotency_key,
            )
            uow.commit()
            return result

    def preview_stop_dev_database(self, *, project_id: ProjectId) -> CommandPreview:
        plan = self._dev_db_port.build_plan(str(project_id))
        runtime = self._dev_db_port.inspect(plan)
        return CommandPreview(
            "StopDevDatabase",
            f"Stop dev database container {plan.container_name}",
            {"project_id": str(project_id), "plan": _plan_preview(plan), "current_status": _public_status(runtime, plan)},
            risk_level=RiskLevel.MEDIUM,
        )

    def execute_stop_dev_database(self, *, project_id: ProjectId, idempotency_key: str | None = None) -> CommandExecutionResult:
        preview = self.preview_stop_dev_database(project_id=project_id)
        plan = self._dev_db_port.build_plan(str(project_id))
        prior_settings = self._read_dev_db_settings(project_id)
        try:
            runtime = self._dev_db_port.stop(plan)
        except DevDatabaseAdapterError as error:
            raise DevDatabaseApplicationError(ErrorCode.EXTERNAL_ADAPTER_FAILED, str(error)) from error

        settings_patch = _settings_patch_from_runtime(runtime, root_password=prior_settings.get(Pathway2SettingKeys.DEV_DB_ROOT_PASSWORD))
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            self._require_project(uow.repository(ProjectRepository), project_id)
            self._upsert_settings(uow, project_id, settings_patch)
            result = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="DevDatabase",
                entity_id=str(project_id),
                summary=f"Stopped dev database container {plan.container_name}",
                result={"project_id": str(project_id), "status": _public_status(runtime, plan)},
                events=[],
                undo_plan=UndoPlan(
                    "UndoStopDevDatabase",
                    f"Start dev database container {plan.container_name}",
                    RestoreDevDatabaseSettingsCompensation(str(project_id), prior_settings),
                    _start_undo_payload(project_id, plan, prior_settings),
                ),
                idempotency_key=idempotency_key,
            )
            uow.commit()
            return result

    def preview_teardown_dev_database(self, *, project_id: ProjectId) -> CommandPreview:
        plan = self._dev_db_port.build_plan(str(project_id))
        return CommandPreview(
            "TeardownDevDatabase",
            f"Remove dev database container and volume {plan.volume_name}",
            {"project_id": str(project_id), "plan": _plan_preview(plan), "remove_volume": True},
            warnings=["This permanently removes the named dev database volume."],
            risk_level=RiskLevel.DESTRUCTIVE,
        )

    def execute_teardown_dev_database(self, *, project_id: ProjectId, idempotency_key: str | None = None) -> CommandExecutionResult:
        preview = self.preview_teardown_dev_database(project_id=project_id)
        plan = self._dev_db_port.build_plan(str(project_id))
        removal = self._dev_db_port.remove(plan, remove_volume=True)
        compensation = ClearDevDatabaseSettingsCompensation(str(project_id))
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            self._require_project(uow.repository(ProjectRepository), project_id)
            self._clear_dev_db_settings(uow, project_id)
            result = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="DevDatabase",
                entity_id=str(project_id),
                summary="Removed dev database container and volume",
                result={"project_id": str(project_id), "removal": removal},
                events=[],
                undo_plan=None,
            )
            uow.commit()
            return result

    def undo(self, undo_plan: UndoPlan) -> CommandExecutionResult:
        project_id = ProjectId(str(undo_plan.payload["project_id"]))
        preview = CommandPreview(undo_plan.command_type, undo_plan.summary, {"undo": _redact_undo_payload(undo_plan.payload)}, risk_level=RiskLevel.HIGH)

        external_result: dict[str, Any] = {}
        settings_patch: dict[str, Any] | None = None
        if undo_plan.command_type == "UndoProvisionDevDatabase":
            plan = _plan_from_payload(undo_plan.payload)
            external_result = self._dev_db_port.remove(plan, remove_volume=bool(undo_plan.payload.get("remove_volume", False)))
            settings_patch = _clear_settings_patch()
        elif undo_plan.command_type == "UndoStartDevDatabase":
            plan = _plan_from_payload(undo_plan.payload)
            external_result = asdict_status(self._dev_db_port.stop(plan))
            settings_patch = dict(undo_plan.payload.get("prior_settings") or {})
        elif undo_plan.command_type == "UndoStopDevDatabase":
            plan = _plan_from_payload(undo_plan.payload)
            external_result = asdict_status(self._dev_db_port.start(plan))
            settings_patch = dict(undo_plan.payload.get("prior_settings") or {})

        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            if settings_patch is not None:
                self._upsert_settings(uow, project_id, settings_patch)
            result = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="DevDatabaseUndo",
                entity_id=str(project_id),
                summary=undo_plan.summary,
                result={"external": external_result, "undo": _redact_undo_payload(undo_plan.payload)},
                events=[],
                undo_plan=None,
            )
            uow.commit()
            return result

    def undo_command_execution(self, command_execution_id: StableIdentifier) -> CommandExecutionResult:
        undo_plan = self._resolve_undo_plan(command_execution_id)
        return self.undo(undo_plan)

    def _resolve_undo_plan(self, command_execution_id: StableIdentifier) -> UndoPlan:
        with self._container.create_unit_of_work() as uow:
            uow.begin()
            try:
                audit_repository = uow.repository(AuditRepository)
                execution = audit_repository.get_command_execution(str(command_execution_id))
                if execution is None:
                    raise DevDatabaseApplicationError(ErrorCode.NOT_FOUND, f"Command execution not found: {command_execution_id}")
                if execution.status != "succeeded":
                    raise DevDatabaseApplicationError(ErrorCode.PRECONDITION_FAILED, "Command execution did not succeed and cannot be undone")
                audit_event = audit_repository.get_audit_event(execution.audit_event_id) if execution.audit_event_id else None
                if audit_event is None:
                    raise DevDatabaseApplicationError(ErrorCode.NOT_FOUND, "Audit record not found for command execution")
                undo_payload = (audit_event.details_json or {}).get("undo")
                if not undo_payload:
                    raise DevDatabaseApplicationError(ErrorCode.PRECONDITION_FAILED, "Command execution is not undoable")
                return UndoPlan(
                    command_type=str(undo_payload.get("command_type") or "UndoProvisionDevDatabase"),
                    summary=str(undo_payload.get("summary") or "Undo dev database command"),
                    action=ClearDevDatabaseSettingsCompensation(str(undo_payload.get("project_id"))),
                    payload=undo_payload,
                )
            finally:
                uow.rollback()

    def _read_dev_db_settings(self, project_id: ProjectId) -> dict[str, Any]:
        settings = self._container.create_project_service().get_project_settings(project_id, list(_DEV_DB_SETTING_KEYS))
        return {key: value for key, value in settings.items() if value is not None}

    def _upsert_settings(self, uow: SingleWriterSQLiteUnitOfWork, project_id: ProjectId, patch: dict[str, Any]) -> None:
        if not patch:
            return
        uow.repository(ProjectRepository).upsert_settings(
            project_id=project_id,
            patch=patch,
            updated_at=datetime.now(UTC),
        )

    def _clear_dev_db_settings(self, uow: SingleWriterSQLiteUnitOfWork, project_id: ProjectId) -> None:
        self._upsert_settings(uow, project_id, _clear_settings_patch())

    def _heal_absent_settings(self, project_id: ProjectId) -> None:
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            self._clear_dev_db_settings(uow, project_id)
            uow.commit()

    def _require_project(self, repository: ProjectRepository, project_id: ProjectId) -> None:
        if repository.get_project(project_id) is None:
            raise DevDatabaseApplicationError(ErrorCode.NOT_FOUND, f"Project not found: {project_id}")


def _provision_warnings(probe: Any, port_check: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if probe.state != DockerAvailabilityState.AVAILABLE:
        warnings.append(
            bring_your_own_mysql_message(
                prefix="Docker is not available for provisioning — install/start Docker Desktop, or",
            )
        )
    if port_check.get("status") == "warning":
        warnings.append(str(port_check.get("message")))
    return warnings


def _plan_preview(plan: DevDatabasePlan) -> dict[str, Any]:
    return {
        "project_id": plan.project_id,
        "engine": plan.engine.value,
        "image": plan.image,
        "container_name": plan.container_name,
        "volume_name": plan.volume_name,
        "host": plan.host,
        "port": plan.port,
        "database": plan.database,
        "user": plan.user,
        "publish_host_port": plan.publish_host_port,
        "connection_string": plan.connection_string,
    }


def _public_status(runtime: DevDatabaseRuntimeStatus, plan: DevDatabasePlan) -> dict[str, Any]:
    return {
        "lifecycle": runtime.lifecycle.value,
        "engine": runtime.engine.value,
        "container_id": runtime.container_id,
        "container_name": runtime.container_name or plan.container_name,
        "volume_name": runtime.volume_name or plan.volume_name,
        "docker_state": runtime.docker_state,
        "container_running": runtime.container_running,
        "mysql_reachable": runtime.mysql_reachable,
        "connection_string": runtime.connection_string,
        "message": runtime.message,
    }


def _settings_patch_from_runtime(runtime: DevDatabaseRuntimeStatus, *, root_password: str | None) -> dict[str, Any]:
    patch: dict[str, Any] = {
        Pathway2SettingKeys.DEV_DB_ENGINE: runtime.engine.value,
        Pathway2SettingKeys.DEV_DB_CONTAINER_ID: runtime.container_id,
        Pathway2SettingKeys.DEV_DB_CONTAINER_NAME: runtime.container_name,
        Pathway2SettingKeys.DEV_DB_VOLUME_NAME: runtime.volume_name,
        Pathway2SettingKeys.DEV_DB_STATUS: runtime.lifecycle.value,
        Pathway2SettingKeys.DEV_DB_MYSQL_REACHABLE: runtime.mysql_reachable,
    }
    if root_password:
        patch[Pathway2SettingKeys.DEV_DB_ROOT_PASSWORD] = root_password
    return patch


def _remove_undo_payload(project_id: ProjectId, plan: DevDatabasePlan, *, remove_volume: bool) -> dict[str, Any]:
    payload = _plan_undo_payload(project_id, plan)
    payload.update(
        {
            "action_type": "remove_dev_database",
            "command_type": "UndoProvisionDevDatabase",
            "summary": "Remove dev database container (keep named volume)" if not remove_volume else "Remove dev database container and volume",
            "remove_volume": remove_volume,
        }
    )
    return payload


def _stop_undo_payload(project_id: ProjectId, plan: DevDatabasePlan, prior_settings: dict[str, Any]) -> dict[str, Any]:
    payload = _plan_undo_payload(project_id, plan)
    payload.update(
        {
            "action_type": "stop_dev_database",
            "command_type": "UndoStartDevDatabase",
            "summary": f"Stop dev database container {plan.container_name}",
            "prior_settings": prior_settings,
        }
    )
    return payload


def _start_undo_payload(project_id: ProjectId, plan: DevDatabasePlan, prior_settings: dict[str, Any]) -> dict[str, Any]:
    payload = _plan_undo_payload(project_id, plan)
    payload.update(
        {
            "action_type": "start_dev_database",
            "command_type": "UndoStopDevDatabase",
            "summary": f"Start dev database container {plan.container_name}",
            "prior_settings": prior_settings,
        }
    )
    return payload


def _plan_undo_payload(project_id: ProjectId, plan: DevDatabasePlan) -> dict[str, Any]:
    return {
        "project_id": str(project_id),
        "engine": plan.engine.value,
        "image": plan.image,
        "container_name": plan.container_name,
        "volume_name": plan.volume_name,
        "host": plan.host,
        "port": plan.port,
        "database": plan.database,
        "user": plan.user,
        "password": plan.password,
        "connection_string": plan.connection_string,
        "publish_host_port": plan.publish_host_port,
    }


def _plan_from_payload(payload: dict[str, Any]) -> DevDatabasePlan:
    from backend.domain.dev_db.types import DevDatabaseEngine

    return DevDatabasePlan(
        project_id=str(payload["project_id"]),
        engine=DevDatabaseEngine(str(payload.get("engine", DevDatabaseEngine.MYSQL.value))),
        image=str(payload["image"]),
        container_name=str(payload["container_name"]),
        volume_name=str(payload["volume_name"]),
        host=str(payload["host"]),
        port=int(payload["port"]),
        database=str(payload["database"]),
        user=str(payload["user"]),
        password=str(payload["password"]),
        connection_string=str(payload.get("connection_string") or dev_db_connection_string()),
        publish_host_port=str(payload["publish_host_port"]),
    )


def _clear_settings_patch() -> dict[str, Any]:
    return {key: None for key in _DEV_DB_SETTING_KEYS}


def asdict_status(runtime: DevDatabaseRuntimeStatus) -> dict[str, Any]:
    return {
        "lifecycle": runtime.lifecycle.value,
        "container_id": runtime.container_id,
        "container_running": runtime.container_running,
        "mysql_reachable": runtime.mysql_reachable,
        "message": runtime.message,
    }


def _redact_undo_payload(payload: dict[str, Any]) -> dict[str, Any]:
    redacted = dict(payload)
    if "prior_settings" in redacted and Pathway2SettingKeys.DEV_DB_ROOT_PASSWORD in redacted["prior_settings"]:
        prior = dict(redacted["prior_settings"])
        prior[Pathway2SettingKeys.DEV_DB_ROOT_PASSWORD] = "[REDACTED]"
        redacted["prior_settings"] = prior
    if "password" in redacted:
        redacted["password"] = "[REDACTED]"
    return redacted
