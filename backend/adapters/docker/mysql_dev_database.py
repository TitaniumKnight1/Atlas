from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any

from backend.domain.dev_db.checks import is_tcp_port_listening
from backend.domain.dev_db.naming import container_name_for_project, volume_name_for_project
from backend.domain.dev_db.types import (
    DEV_DB_DATABASE,
    DEV_DB_PASSWORD,
    DEV_DB_USER,
    MYSQL_IMAGE,
    DevDatabaseAdapterError,
    DevDatabaseEngine,
    DevDatabaseLifecycleStatus,
    DevDatabasePlan,
    DevDatabaseRuntimeStatus,
    dev_db_connection_string,
    dev_db_host,
    dev_db_port,
)


@dataclass(frozen=True, slots=True)
class MySqlDockerDevDatabase:
    pull_timeout_seconds: float = 600.0
    command_timeout_seconds: float = 120.0

    def build_plan(self, project_id: str) -> DevDatabasePlan:
        host = dev_db_host()
        port = dev_db_port()
        return DevDatabasePlan(
            project_id=project_id,
            engine=DevDatabaseEngine.MYSQL,
            image=MYSQL_IMAGE,
            container_name=container_name_for_project(project_id),
            volume_name=volume_name_for_project(project_id),
            host=host,
            port=port,
            database=DEV_DB_DATABASE,
            user=DEV_DB_USER,
            password=DEV_DB_PASSWORD,
            connection_string=dev_db_connection_string(),
            publish_host_port=f"{host}:{port}:{port}",
        )

    def inspect(self, plan: DevDatabasePlan) -> DevDatabaseRuntimeStatus:
        record = self._inspect_record(plan.container_name)
        if record is None:
            return DevDatabaseRuntimeStatus(
                lifecycle=DevDatabaseLifecycleStatus.ABSENT,
                engine=plan.engine,
                container_name=plan.container_name,
                volume_name=plan.volume_name,
                connection_string=plan.connection_string,
                message="Dev database container not found.",
            )

        running = bool(record.get("running"))
        mysql_reachable = running and is_tcp_port_listening(plan.host, plan.port)
        lifecycle = _lifecycle_from_state(running=running, mysql_reachable=mysql_reachable)
        return DevDatabaseRuntimeStatus(
            lifecycle=lifecycle,
            engine=plan.engine,
            container_id=record.get("id"),
            container_name=plan.container_name,
            volume_name=plan.volume_name,
            docker_state=record.get("status"),
            container_running=running,
            mysql_reachable=mysql_reachable,
            connection_string=plan.connection_string,
            message=_status_message(lifecycle, plan.host, plan.port),
        )

    def pull_image(self, plan: DevDatabasePlan) -> None:
        self._run(["docker", "pull", plan.image], timeout=self.pull_timeout_seconds)

    def provision(self, plan: DevDatabasePlan, *, root_password: str) -> DevDatabaseRuntimeStatus:
        existing = self._inspect_record(plan.container_name)
        if existing is not None:
            if existing.get("running"):
                return self.inspect(plan)
            self.start(plan)
            return self.inspect(plan)

        self._ensure_volume(plan.volume_name)
        try:
            completed = self._run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    plan.container_name,
                    "-v",
                    f"{plan.volume_name}:/var/lib/mysql",
                    "-e",
                    f"MYSQL_DATABASE={plan.database}",
                    "-e",
                    f"MYSQL_USER={plan.user}",
                    "-e",
                    f"MYSQL_PASSWORD={plan.password}",
                    "-e",
                    f"MYSQL_ROOT_PASSWORD={root_password}",
                    "-p",
                    plan.publish_host_port,
                    plan.image,
                ],
                timeout=self.command_timeout_seconds,
            )
        except DevDatabaseAdapterError:
            self._safe_remove_container(plan.container_name)
            raise

        container_id = (completed.stdout or "").strip() or None
        status = self.inspect(plan)
        if container_id and not status.container_id:
            return DevDatabaseRuntimeStatus(
                lifecycle=status.lifecycle,
                engine=status.engine,
                container_id=container_id,
                container_name=status.container_name,
                volume_name=status.volume_name,
                docker_state=status.docker_state,
                container_running=status.container_running,
                mysql_reachable=status.mysql_reachable,
                connection_string=status.connection_string,
                message=status.message,
                stderr=status.stderr,
            )
        return status

    def start(self, plan: DevDatabasePlan) -> DevDatabaseRuntimeStatus:
        existing = self._inspect_record(plan.container_name)
        if existing is None:
            raise DevDatabaseAdapterError(f"Container not found: {plan.container_name}")
        if not existing.get("running"):
            self._run(["docker", "start", plan.container_name], timeout=self.command_timeout_seconds)
        return self.inspect(plan)

    def stop(self, plan: DevDatabasePlan) -> DevDatabaseRuntimeStatus:
        existing = self._inspect_record(plan.container_name)
        if existing is None:
            return DevDatabaseRuntimeStatus(
                lifecycle=DevDatabaseLifecycleStatus.ABSENT,
                engine=plan.engine,
                container_name=plan.container_name,
                volume_name=plan.volume_name,
                connection_string=plan.connection_string,
                message="Dev database container already absent.",
            )
        if existing.get("running"):
            self._run(["docker", "stop", plan.container_name], timeout=self.command_timeout_seconds)
        return self.inspect(plan)

    def remove(self, plan: DevDatabasePlan, *, remove_volume: bool) -> dict[str, Any]:
        removed_container = False
        removed_volume = False
        existing = self._inspect_record(plan.container_name)
        if existing is not None:
            self._safe_remove_container(plan.container_name)
            removed_container = True
        if remove_volume:
            result = self._run_optional(["docker", "volume", "rm", plan.volume_name])
            removed_volume = result is not None and result.returncode == 0
        return {
            "container_name": plan.container_name,
            "volume_name": plan.volume_name,
            "removed_container": removed_container,
            "removed_volume": removed_volume,
            "remove_volume": remove_volume,
            "reason": None if existing is not None or remove_volume else "not_found",
        }

    def _ensure_volume(self, volume_name: str) -> None:
        self._run_optional(["docker", "volume", "create", volume_name])

    def _inspect_record(self, container_name: str) -> dict[str, Any] | None:
        completed = self._run_optional(
            [
                "docker",
                "inspect",
                "--format",
                "{{json .}}",
                container_name,
            ],
            timeout=self.command_timeout_seconds,
        )
        if completed is None or completed.returncode != 0:
            return None
        try:
            payload = json.loads((completed.stdout or "").strip())
        except json.JSONDecodeError:
            return None
        state = payload.get("State") or {}
        return {
            "id": payload.get("Id"),
            "running": bool(state.get("Running")),
            "status": state.get("Status"),
        }

    def _safe_remove_container(self, container_name: str) -> None:
        self._run_optional(["docker", "rm", "-f", container_name])

    def _run(self, args: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        try:
            completed = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except FileNotFoundError as error:
            raise DevDatabaseAdapterError("Docker CLI not found", stderr=str(error)) from error
        except subprocess.TimeoutExpired as error:
            raise DevDatabaseAdapterError(f"Docker command timed out: {' '.join(args)}", stderr=str(error)) from error
        except OSError as error:
            raise DevDatabaseAdapterError(f"Docker command failed: {' '.join(args)}", stderr=str(error)) from error

        if completed.returncode != 0:
            raise DevDatabaseAdapterError(
                f"Docker command failed: {' '.join(args)}",
                stderr=_stderr(completed),
            )
        return completed

    def _run_optional(self, args: list[str], *, timeout: float | None = None) -> subprocess.CompletedProcess[str] | None:
        try:
            return subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout or self.command_timeout_seconds,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return None


def _stderr(result: subprocess.CompletedProcess[str]) -> str | None:
    combined = (result.stderr or result.stdout or "").strip()
    return combined or None


def _lifecycle_from_state(*, running: bool, mysql_reachable: bool) -> DevDatabaseLifecycleStatus:
    if not running:
        return DevDatabaseLifecycleStatus.STOPPED
    if mysql_reachable:
        return DevDatabaseLifecycleStatus.REACHABLE
    return DevDatabaseLifecycleStatus.RUNNING


def _status_message(lifecycle: DevDatabaseLifecycleStatus, host: str, port: int) -> str:
    if lifecycle == DevDatabaseLifecycleStatus.REACHABLE:
        return f"MySQL reachable at {host}:{port}."
    if lifecycle == DevDatabaseLifecycleStatus.RUNNING:
        return f"Container running; MySQL not yet reachable at {host}:{port}."
    if lifecycle == DevDatabaseLifecycleStatus.STOPPED:
        return "Dev database container is stopped."
    if lifecycle == DevDatabaseLifecycleStatus.ABSENT:
        return "Dev database container not found."
    return f"Dev database status: {lifecycle.value}."
