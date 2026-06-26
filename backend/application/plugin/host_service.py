from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from backend.adapters.persistence import PluginRepository, ProjectRepository
from backend.adapters.plugin.subprocess_host import SubprocessPluginHost, default_bootstrap_path
from backend.application.plugin.capability_mediator import PluginCapabilityMediator
from backend.application.plugin.service import PluginApplicationError
from backend.domain.plugin.events import (
    plugin_capability_call_denied,
    plugin_failed,
    plugin_started,
    plugin_stopped,
)
from backend.domain.plugin.ipc import MESSAGE_CAPABILITY_REQUEST, capability_response_message
from backend.domain.plugin.runtime_types import (
    PLUGIN_HANG_KILL_TIMEOUT_SECONDS,
    PLUGIN_STARTUP_TIMEOUT_SECONDS,
    CapabilityCallDecision,
    CapabilityCallOutcome,
    PluginRuntimeStatus,
)
from backend.domain.plugin.types import PluginCapability
from backend.domain.shared_kernel import ErrorCode, ProjectId, StableIdentifier


class PluginHostService:
    """Subprocess plugin host with capability enforcement at the IPC boundary."""

    def __init__(self, *, container: Any, clock: Callable[[], datetime] | None = None) -> None:
        self._container = container
        self._clock = clock or (lambda: datetime.now(UTC))
        self._mediator = PluginCapabilityMediator(container=container, filesystem=container.setup_filesystem)
        self._active_hosts: dict[str, SubprocessPluginHost] = {}

    def start_plugin(
        self,
        plugin_id: str,
        project_id: ProjectId,
        *,
        mode: str = "normal",
        call_timeout_seconds: float = PLUGIN_HANG_KILL_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        registration, grants = self._assert_can_launch(plugin_id, project_id)
        plugin_script = self._resolve_plugin_script(registration)
        runtime_id = StableIdentifier.new()
        now = self._clock()
        host = SubprocessPluginHost(
            bootstrap_script=default_bootstrap_path(),
            plugin_script=plugin_script,
            plugin_id=registration.plugin_key,
            granted_capabilities=grants,
            mode=mode,
            startup_timeout_seconds=PLUGIN_STARTUP_TIMEOUT_SECONDS,
            call_timeout_seconds=call_timeout_seconds,
        )
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            uow.repository(ProjectRepository).get_project(project_id) or self._missing_project(project_id)
            runtime = uow.repository(PluginRepository).create_runtime(
                runtime_id=runtime_id,
                plugin_id=plugin_id,
                project_id=project_id,
                status=PluginRuntimeStatus.STARTING.value,
                pid=None,
                started_at=now,
            )
            uow.commit()
        try:
            pid = host.start()
        except Exception as error:  # noqa: BLE001
            self._finish_runtime(
                str(runtime_id),
                project_id,
                status=PluginRuntimeStatus.FAILED.value,
                exit_code=None,
                summary=self._sanitize_failure(str(error)),
            )
            raise PluginApplicationError(ErrorCode.EXTERNAL_ADAPTER_FAILED, str(error)) from error
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            record = uow.repository(PluginRepository).get_runtime(str(runtime_id))
            assert record is not None
            record.pid = pid
            record.status = PluginRuntimeStatus.RUNNING.value
            uow.collect_event(plugin_started(registration.plugin_key, runtime_id=str(runtime_id), project_id=project_id, pid=pid))
            uow.commit()
        self._active_hosts[str(runtime_id)] = host
        registration_data = self._container.create_plugin_service().get_plugin(plugin_id)
        return _runtime_data(record, host_pid=pid, plugin_key=registration_data.get("plugin_key"))

    def run_plugin(
        self,
        plugin_id: str,
        project_id: ProjectId,
        *,
        mode: str = "normal",
        call_timeout_seconds: float = PLUGIN_HANG_KILL_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        runtime = self.start_plugin(plugin_id, project_id, mode=mode, call_timeout_seconds=call_timeout_seconds)
        runtime_id = runtime["runtime_id"]
        host = self._active_hosts[runtime_id]
        try:
            if mode == "hang":
                import time

                deadline = time.monotonic() + PLUGIN_HANG_KILL_TIMEOUT_SECONDS
                while host.is_running() and time.monotonic() < deadline:
                    time.sleep(0.05)
                result = {"responses": []}
                if host.is_running():
                    host.stop(timeout_seconds=PLUGIN_HANG_KILL_TIMEOUT_SECONDS)
                    self._finish_runtime(
                        runtime_id,
                        project_id,
                        status=PluginRuntimeStatus.TIMED_OUT.value,
                        exit_code=host.pid and -1,
                        summary=self._sanitize_failure("Plugin execution timed out"),
                        plugin_key=runtime.get("plugin_key"),
                    )
                    return {**runtime, "status": PluginRuntimeStatus.TIMED_OUT.value, "responses": result.get("responses", [])}
            else:
                result = host.run_until_shutdown(lambda message: self._handle_message(plugin_id, project_id, runtime_id, message))
            exit_code = host.stop()
            status = PluginRuntimeStatus.STOPPED.value
            failure_summary = None
            if mode == "crash" or (exit_code not in (0, None) and mode != "hang"):
                status = PluginRuntimeStatus.CRASHED.value
                failure_summary = self._sanitize_failure(f"Plugin exited with code {exit_code}")
                self._record_failure_event(plugin_id, project_id, runtime_id, failure_summary)
            self._finish_runtime(
                runtime_id,
                project_id,
                status=status,
                exit_code=exit_code,
                summary=failure_summary,
                plugin_key=None,
            )
            return {**self.get_runtime(runtime_id, project_id), "responses": result.get("responses", [])}
        finally:
            self._active_hosts.pop(runtime_id, None)
            if host.is_running():
                host.stop(timeout_seconds=PLUGIN_HANG_KILL_TIMEOUT_SECONDS)

    def stop_plugin(self, runtime_id: str, project_id: ProjectId) -> dict[str, Any]:
        host = self._active_hosts.pop(runtime_id, None)
        if host is not None:
            exit_code = host.stop()
        else:
            exit_code = None
        self._finish_runtime(runtime_id, project_id, status=PluginRuntimeStatus.STOPPED.value, exit_code=exit_code)
        return self.get_runtime(runtime_id, project_id)

    def get_runtime(self, runtime_id: str, project_id: ProjectId) -> dict[str, Any]:
        with self._container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext

            record = PluginRepository(RepositoryContext(session=session, project_id=project_id)).get_runtime(runtime_id)
        if record is None or record.project_id != str(project_id):
            raise PluginApplicationError(ErrorCode.NOT_FOUND, f"Runtime not found: {runtime_id}")
        registration = self._container.create_plugin_service().get_plugin(record.plugin_id)
        return _runtime_data(record, plugin_key=registration.get("plugin_key"))

    def list_capability_calls(self, plugin_id: str, project_id: ProjectId, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext

            records = PluginRepository(RepositoryContext(session=session, project_id=project_id)).list_capability_calls(
                plugin_id, project_id, limit=limit
            )
        return [_call_data(record) for record in records]

    def _handle_message(self, plugin_id: str, project_id: ProjectId, runtime_id: str, message: dict[str, Any]) -> dict[str, Any]:
        if message.get("type") != MESSAGE_CAPABILITY_REQUEST:
            return capability_response_message(request_id=str(message.get("request_id", "")), granted=False, error="Unsupported IPC message")
        capability = str(message.get("capability") or "")
        granted = self._is_capability_granted(plugin_id, project_id, capability)
        if not granted:
            response = capability_response_message(
                request_id=str(message.get("request_id") or ""),
                granted=False,
                error=f"Capability not granted: {capability}",
            )
            self._audit_call(
                plugin_id=plugin_id,
                project_id=project_id,
                runtime_id=runtime_id,
                capability=capability,
                decision=CapabilityCallDecision.DENIED.value,
                outcome=CapabilityCallOutcome.DENIED.value,
                request=message,
                response=response,
            )
            registration = self._container.create_plugin_service().get_plugin(plugin_id)
            with self._container.create_unit_of_work(project_id) as uow:
                uow.begin()
                uow.collect_event(
                    plugin_capability_call_denied(
                        registration["plugin_key"],
                        capability=capability,
                        project_id=project_id,
                        reason="not_granted",
                    )
                )
                uow.commit()
            return response
        response = self._mediator.handle_request(
            plugin_id=plugin_id,
            project_id=project_id,
            runtime_id=runtime_id,
            message=message,
            is_granted=True,
        )
        outcome = CapabilityCallOutcome.SUCCEEDED.value if response.get("granted") and not response.get("error") else CapabilityCallOutcome.FAILED.value
        self._audit_call(
            plugin_id=plugin_id,
            project_id=project_id,
            runtime_id=runtime_id,
            capability=capability,
            decision=CapabilityCallDecision.GRANTED.value,
            outcome=outcome,
            request=message,
            response=response,
        )
        return response

    def _is_capability_granted(self, plugin_id: str, project_id: ProjectId, capability: str) -> bool:
        try:
            PluginCapability(capability)
        except ValueError:
            return False
        with self._container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext

            repository = PluginRepository(RepositoryContext(session=session, project_id=project_id))
            if not repository.get_global_enabled():
                return False
            registration = repository.get_registration(plugin_id)
            if registration is None or not registration.is_enabled:
                return False
            return repository.get_active_grant(plugin_id, capability, project_id) is not None

    def _audit_call(
        self,
        *,
        plugin_id: str,
        project_id: ProjectId,
        runtime_id: str,
        capability: str,
        decision: str,
        outcome: str,
        request: dict[str, Any],
        response: dict[str, Any],
    ) -> None:
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            uow.repository(PluginRepository).record_capability_call(
                call_id=StableIdentifier.new(),
                runtime_id=runtime_id,
                plugin_id=plugin_id,
                project_id=project_id,
                capability=capability,
                decision=decision,
                outcome=outcome,
                request_json=request,
                response_json=response,
                occurred_at=self._clock(),
            )
            uow.commit()

    def _assert_can_launch(self, plugin_id: str, project_id: ProjectId):
        plugins = self._container.create_plugin_service()
        if not plugins.get_global_settings()["global_enabled"]:
            raise PluginApplicationError(ErrorCode.PRECONDITION_FAILED, "Global plugin kill switch is disabled")
        registration = plugins.get_plugin(plugin_id)
        if not registration["is_enabled"]:
            raise PluginApplicationError(ErrorCode.PRECONDITION_FAILED, "Plugin is disabled")
        caps = plugins.list_capabilities(plugin_id, project_id)
        grants = caps["granted_capabilities"]
        if not grants:
            raise PluginApplicationError(ErrorCode.PRECONDITION_FAILED, "No capabilities granted for project")
        with self._container.session_factory() as session:
            from backend.infrastructure.unit_of_work import RepositoryContext

            record = PluginRepository(RepositoryContext(session=session)).get_registration(plugin_id)
        return record, grants

    def _resolve_plugin_script(self, registration) -> Path:
        manifest = registration.manifest_json or {}
        source_ref = registration.source_ref or manifest.get("source_ref")
        entry_script = manifest.get("entry_script", "plugin.py")
        if not source_ref:
            raise PluginApplicationError(ErrorCode.VALIDATION_FAILED, "Plugin source_ref is required to launch runtime")
        script = Path(source_ref) / entry_script
        if not script.exists():
            raise PluginApplicationError(ErrorCode.NOT_FOUND, f"Plugin entry script not found: {script}")
        return script.resolve()

    def _finish_runtime(
        self,
        runtime_id: str,
        project_id: ProjectId,
        *,
        status: str,
        exit_code: int | None,
        summary: dict[str, Any] | str | None = None,
        plugin_key: str | None = None,
    ) -> None:
        now = self._clock()
        failure = {"summary": summary} if isinstance(summary, str) else summary
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(PluginRepository)
            record = repository.get_runtime(runtime_id)
            if record is None:
                uow.rollback()
                return
            repository.finish_runtime(
                record,
                status=status,
                stopped_at=now,
                exit_code=exit_code,
                failure_summary=failure,
            )
            key = plugin_key or self._container.create_plugin_service().get_plugin(record.plugin_id)["plugin_key"]
            uow.collect_event(plugin_stopped(key, runtime_id=runtime_id, project_id=project_id))
            uow.commit()

    def _record_failure_event(self, plugin_id: str, project_id: ProjectId, runtime_id: str, summary: dict[str, Any]) -> None:
        registration = self._container.create_plugin_service().get_plugin(plugin_id)
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            uow.collect_event(
                plugin_failed(
                    registration["plugin_key"],
                    runtime_id=runtime_id,
                    project_id=project_id,
                    summary=str(summary.get("summary", "plugin failed")),
                )
            )
            uow.commit()

    def _sanitize_failure(self, message: str) -> dict[str, Any]:
        redacted = message.replace("\\", "/")
        if len(redacted) > 500:
            redacted = redacted[:500] + "..."
        return {"summary": redacted, "local_only": True}

    def _missing_project(self, project_id: ProjectId) -> None:
        raise PluginApplicationError(ErrorCode.NOT_FOUND, f"Project not found: {project_id}")


def _runtime_data(record: Any, *, host_pid: int | None = None, plugin_key: str | None = None) -> dict[str, Any]:
    return {
        "runtime_id": record.runtime_id,
        "plugin_id": record.plugin_id,
        "plugin_key": plugin_key,
        "project_id": record.project_id,
        "status": record.status,
        "pid": host_pid if host_pid is not None else record.pid,
        "started_at": record.started_at,
        "stopped_at": record.stopped_at,
        "exit_code": record.exit_code,
        "failure_summary": record.failure_summary_json,
        "atlas_pid": os.getpid(),
    }


def _call_data(record: Any) -> dict[str, Any]:
    return {
        "call_id": record.call_id,
        "runtime_id": record.runtime_id,
        "plugin_id": record.plugin_id,
        "project_id": record.project_id,
        "capability": record.capability,
        "decision": record.decision,
        "outcome": record.outcome,
        "request": record.request_json,
        "response": record.response_json,
        "occurred_at": record.occurred_at,
    }
