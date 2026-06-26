from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.adapters.persistence import AuditRepository, ProjectRepository, SetupRepository
from backend.adapters.persistence.models import DependencyCheckRecord, SetupProcessRunRecord
from backend.adapters.streams import StreamEventPublisher
from backend.application.commands import CommandContext, CommandExecutionResult, CommandPreview, DryRunResult, RiskLevel, UndoPlan
from backend.application.commands.recorder import CommandAuditRecorder
from backend.domain.setup import (
    ArtifactChannel,
    ArtifactInstallPlan,
    ArtifactPlatform,
    ArtifactVersion,
    DependencyCategory,
    DependencyStatus,
    FiveMArtifactPort,
    ProcessLaunchPlan,
    ProcessPort,
    ServerProcessState,
    SetupFilesystemPort,
    TxAdminPort,
    artifact_catalog_refreshed,
    artifact_installed,
    artifact_version_pinned,
    server_config_written,
    server_crashed,
    server_started,
    server_stopped,
    setup_run_completed,
)
from backend.domain.shared_kernel import ErrorCode, ProjectId, StableIdentifier
from backend.infrastructure.unit_of_work import RepositoryContext


class SetupApplicationError(RuntimeError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class RemovePathsCompensation:
    paths: list[str]
    action_type: str = "remove_setup_paths"

    def describe(self) -> dict[str, Any]:
        return {"action_type": self.action_type, "paths": self.paths}

    def apply(self, context: CommandContext) -> dict[str, Any]:
        removed: list[str] = []
        for raw_path in sorted(self.paths, reverse=True):
            path = Path(raw_path)
            if path.is_dir():
                shutil.rmtree(path)
                removed.append(str(path))
            elif path.exists():
                path.unlink()
                removed.append(str(path))
        return {"removed_paths": removed}


@dataclass(frozen=True, slots=True)
class RestoreServerConfigCompensation:
    server_cfg_path: str
    prior_content: str | None
    action_type: str = "restore_server_cfg"

    def describe(self) -> dict[str, Any]:
        return {"action_type": self.action_type, "server_cfg_path": self.server_cfg_path, "had_prior_content": self.prior_content is not None}

    def apply(self, context: CommandContext) -> dict[str, Any]:
        path = Path(self.server_cfg_path)
        if self.prior_content is None:
            if path.exists():
                path.unlink()
            return {"server_cfg_path": str(path), "restored": "deleted_new_file"}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.prior_content, encoding="utf-8")
        return {"server_cfg_path": str(path), "restored": "prior_content"}


@dataclass(frozen=True, slots=True)
class DeleteDependencyChecksCompensation:
    dependency_check_ids: list[str]
    action_type: str = "delete_dependency_checks"

    def describe(self) -> dict[str, Any]:
        return {"action_type": self.action_type, "dependency_check_ids": self.dependency_check_ids}

    def apply(self, context: CommandContext) -> dict[str, Any]:
        deleted = 0
        for check_id in self.dependency_check_ids:
            record = context.uow.session.get(DependencyCheckRecord, check_id)
            if record is not None:
                context.uow.session.delete(record)
                deleted += 1
        return {"deleted_dependency_checks": deleted}


@dataclass(frozen=True, slots=True)
class StopServerProcessCompensation:
    process_port: ProcessPort
    project_id: ProjectId
    process_run_id: str
    action_type: str = "stop_server_process"

    def describe(self) -> dict[str, Any]:
        return {"action_type": self.action_type, "process_run_id": self.process_run_id}

    def apply(self, context: CommandContext) -> dict[str, Any]:
        status = self.process_port.stop(self.process_run_id)
        context.uow.repository(SetupRepository).update_process_run(
            project_id=self.project_id,
            process_run_id=StableIdentifier(self.process_run_id),
            state=ServerProcessState.STOPPED.value,
            stopped_at=datetime.now(UTC),
            exit_code=status.exit_code,
            stdout_tail=status.stdout_tail,
            stderr_tail=status.stderr_tail,
        )
        return _process_status_data(status)


class SetupApplicationService:
    def __init__(
        self,
        *,
        container: Any,
        artifact_client: FiveMArtifactPort,
        filesystem: SetupFilesystemPort,
        process_port: ProcessPort,
        txadmin: TxAdminPort,
        stream_publisher: StreamEventPublisher | None = None,
    ) -> None:
        self._container = container
        self._artifact_client = artifact_client
        self._filesystem = filesystem
        self._process_port = process_port
        self._txadmin = txadmin
        self._stream_publisher = stream_publisher
        self._recorder = CommandAuditRecorder()

    def preview_refresh_artifact_catalog(self, platform: str, channel: str | None = None) -> CommandPreview:
        return CommandPreview(
            "RefreshArtifactCatalog",
            "Refresh local FXServer artifact catalog cache",
            {"platform": platform, "channel": channel, "source": "https://runtime.fivem.net/artifacts/fivem/.../master/{channel}.json"},
        )

    def dry_run_refresh_artifact_catalog(self, platform: str, channel: str | None = None) -> DryRunResult:
        preview = self.preview_refresh_artifact_catalog(platform, channel)
        return DryRunResult(preview.command_type, True, preview.preview, preview.warnings)

    def execute_refresh_artifact_catalog(self, platform: str, channel: str | None = None) -> CommandExecutionResult:
        selected_platform = ArtifactPlatform(platform)
        selected_channel = ArtifactChannel(channel) if channel else None
        artifacts = self._artifact_client.discover(selected_platform, selected_channel)
        preview = self.preview_refresh_artifact_catalog(platform, channel)
        now = datetime.now(UTC)
        with self._container.create_unit_of_work() as uow:
            uow.begin()
            repository = uow.repository(SetupRepository)
            for artifact in artifacts:
                repository.upsert_artifact_version(artifact, now)
            result = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=None,
                entity_type="ArtifactCatalog",
                entity_id=platform,
                summary="Refreshed FXServer artifact catalog",
                result={"platform": platform, "count": len(artifacts), "artifacts": [_artifact_data(item) for item in artifacts]},
                events=[artifact_catalog_refreshed(platform, [item.channel.value for item in artifacts], len(artifacts))],
            )
            uow.commit()
            return result

    def list_artifact_versions(self, platform: str | None = None, channel: str | None = None) -> list[dict[str, Any]]:
        with self._container.session_factory() as session:
            return [_artifact_record_data(record) for record in SetupRepository(RepositoryContext(session=session)).list_artifact_versions(platform, channel)]

    def preview_pin_artifact_version(
        self,
        *,
        project_id: ProjectId,
        artifact_version_id: str | None,
        channel_preference: str,
        environment_id: str | None = None,
        pinned_reason: str | None = None,
    ) -> CommandPreview:
        return CommandPreview(
            "PinArtifactVersion",
            "Pin FXServer artifact policy for project setup",
            {
                "project_id": str(project_id),
                "environment_id": environment_id,
                "artifact_version_id": artifact_version_id,
                "channel_preference": channel_preference,
                "pinned_reason": pinned_reason,
            },
        )

    def dry_run_pin_artifact_version(self, **kwargs: Any) -> DryRunResult:
        preview = self.preview_pin_artifact_version(**kwargs)
        return DryRunResult(preview.command_type, True, preview.preview, preview.warnings)

    def execute_pin_artifact_version(self, **kwargs: Any) -> CommandExecutionResult:
        project_id: ProjectId = kwargs["project_id"]
        preview = self.preview_pin_artifact_version(**kwargs)
        now = datetime.now(UTC)
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            self._require_project(uow.repository(ProjectRepository), project_id)
            record = uow.repository(SetupRepository).upsert_artifact_pin(now=now, **kwargs)
            result = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="ProjectArtifactPin",
                entity_id=record.artifact_pin_id,
                summary="Pinned FXServer artifact policy",
                result=_pin_data(record),
                events=[artifact_version_pinned(project_id, record.artifact_version_id, record.channel_preference)],
            )
            uow.commit()
            return result

    def preview_install_artifact(
        self,
        *,
        project_id: ProjectId,
        build_number: str,
        platform: str = "windows",
        channel: str = "recommended",
    ) -> CommandPreview:
        plan = self._artifact_install_plan(platform=platform, channel=channel, build_number=build_number)
        return CommandPreview(
            "InstallFxServerArtifact",
            f"Download and extract FXServer artifact {build_number}",
            {
                "project_id": str(project_id),
                "artifact": _artifact_data(plan.artifact),
                "download_path": str(plan.download_path),
                "extract_path": str(plan.extract_path),
                "mutations": ["download artifact archive", "extract artifact directory"],
            },
            warnings=plan.warnings,
            risk_level=RiskLevel.HIGH,
        )

    def dry_run_install_artifact(self, **kwargs: Any) -> DryRunResult:
        preview = self.preview_install_artifact(**kwargs)
        return DryRunResult(preview.command_type, True, preview.preview, preview.warnings)

    def execute_install_artifact(self, *, project_id: ProjectId, build_number: str, platform: str = "windows", channel: str = "recommended") -> CommandExecutionResult:
        preview = self.preview_install_artifact(project_id=project_id, build_number=build_number, platform=platform, channel=channel)
        plan = self._artifact_install_plan(platform=platform, channel=channel, build_number=build_number)
        operation_id = str(StableIdentifier.new())
        progress: list[dict[str, Any]] = []
        self._filesystem.ensure_directory(plan.download_path.parent)
        self._filesystem.ensure_directory(plan.extract_path)
        downloaded = self._artifact_client.download(
            plan.artifact,
            plan.download_path,
            progress=lambda item: self._record_download_progress(project_id, item, progress),
            operation_id=operation_id,
        )
        extracted = self._filesystem.extract_zip(downloaded, plan.extract_path)
        undo_plan = UndoPlan(
            "UndoInstallFxServerArtifact",
            "Remove downloaded and extracted FXServer artifact files",
            RemovePathsCompensation([str(plan.extract_path), str(plan.download_path)]),
            {**RemovePathsCompensation([str(plan.extract_path), str(plan.download_path)]).describe(), "project_id": str(project_id)},
        )
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            self._require_project(uow.repository(ProjectRepository), project_id)
            result = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="ArtifactVersion",
                entity_id=build_number,
                summary=f"Installed FXServer artifact {build_number}",
                result={
                    "project_id": str(project_id),
                    "build_number": build_number,
                    "download_path": str(plan.download_path),
                    "extract_path": str(plan.extract_path),
                    "extracted_count": len(extracted),
                    "operation_id": operation_id,
                    "progress": progress,
                },
                events=[artifact_installed(project_id, build_number, str(plan.extract_path))],
                undo_plan=undo_plan,
            )
            uow.commit()
            return result

    def preview_generate_server_cfg(self, *, project_id: ProjectId, server_data_path: str, options: dict[str, Any]) -> CommandPreview:
        plan = self._server_config_plan(server_data_path, options)
        return CommandPreview(
            "GenerateServerConfig",
            "Generate baseline FiveM server.cfg",
            {
                "project_id": str(project_id),
                "server_cfg_path": str(plan.server_cfg_path),
                "content": plan.content,
                "will_replace_existing": plan.prior_content is not None,
            },
            warnings=plan.warnings,
            risk_level=RiskLevel.HIGH,
        )

    def dry_run_generate_server_cfg(self, **kwargs: Any) -> DryRunResult:
        preview = self.preview_generate_server_cfg(**kwargs)
        return DryRunResult(preview.command_type, True, preview.preview, preview.warnings)

    def execute_generate_server_cfg(self, *, project_id: ProjectId, server_data_path: str, options: dict[str, Any]) -> CommandExecutionResult:
        preview = self.preview_generate_server_cfg(project_id=project_id, server_data_path=server_data_path, options=options)
        plan = self._server_config_plan(server_data_path, options)
        self._filesystem.write_text(plan.server_cfg_path, plan.content)
        compensation = RestoreServerConfigCompensation(str(plan.server_cfg_path), plan.prior_content)
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            self._require_project(uow.repository(ProjectRepository), project_id)
            result = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="ServerConfig",
                entity_id=str(plan.server_cfg_path),
                summary="Generated FiveM server.cfg",
                result={"project_id": str(project_id), "server_cfg_path": str(plan.server_cfg_path)},
                events=[server_config_written(project_id, str(plan.server_cfg_path))],
                undo_plan=UndoPlan("UndoGenerateServerConfig", "Restore previous server.cfg state", compensation, {**compensation.describe(), "project_id": str(project_id)}),
            )
            uow.commit()
            return result

    def preview_run_dependency_checks(self, *, project_id: ProjectId, server_data_path: str, categories: list[str] | None = None) -> CommandPreview:
        selected_categories = categories or [item.value for item in DependencyCategory]
        return CommandPreview(
            "RunDependencyChecks",
            "Record setup preflight dependency checks",
            {"project_id": str(project_id), "server_data_path": server_data_path, "categories": selected_categories},
        )

    def dry_run_dependency_checks(self, **kwargs: Any) -> DryRunResult:
        preview = self.preview_run_dependency_checks(**kwargs)
        return DryRunResult(preview.command_type, True, preview.preview, preview.warnings)

    def execute_run_dependency_checks(self, *, project_id: ProjectId, server_data_path: str, categories: list[str] | None = None) -> CommandExecutionResult:
        preview = self.preview_run_dependency_checks(project_id=project_id, server_data_path=server_data_path, categories=categories)
        checks = self._dependency_checks(server_data_path, categories)
        check_ids = [StableIdentifier.new() for _ in checks]
        now = datetime.now(UTC)
        compensation = DeleteDependencyChecksCompensation([str(item) for item in check_ids])
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            self._require_project(uow.repository(ProjectRepository), project_id)
            repository = uow.repository(SetupRepository)
            for check_id, check in zip(check_ids, checks, strict=True):
                repository.add_dependency_check(dependency_check_id=check_id, project_id=project_id, setup_run_id=None, checked_at=now, **check)
            result = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="DependencyCheck",
                entity_id=str(project_id),
                summary="Recorded setup dependency checks",
                result={"project_id": str(project_id), "checks": checks},
                events=[],
                undo_plan=UndoPlan("UndoRunDependencyChecks", "Delete dependency check records", compensation, {**compensation.describe(), "project_id": str(project_id)}),
            )
            uow.commit()
            return result

    def preview_prepare_database(self, *, project_id: ProjectId, server_data_path: str, database_name: str = "fivem.sqlite") -> CommandPreview:
        database_path = Path(server_data_path).expanduser().resolve() / "database" / database_name
        warnings = ["Existing database files are not modified and are not safely reversible."] if database_path.exists() else []
        return CommandPreview(
            "PrepareSetupDatabase",
            "Create a local placeholder database file for setup validation",
            {"project_id": str(project_id), "database_path": str(database_path), "will_create": not database_path.exists()},
            warnings=warnings,
            risk_level=RiskLevel.HIGH if warnings else RiskLevel.MEDIUM,
        )

    def dry_run_prepare_database(self, **kwargs: Any) -> DryRunResult:
        preview = self.preview_prepare_database(**kwargs)
        return DryRunResult(preview.command_type, True, preview.preview, preview.warnings)

    def execute_prepare_database(self, *, project_id: ProjectId, server_data_path: str, database_name: str = "fivem.sqlite") -> CommandExecutionResult:
        preview = self.preview_prepare_database(project_id=project_id, server_data_path=server_data_path, database_name=database_name)
        database_path = Path(preview.preview["database_path"])
        created = self._filesystem.touch_file(database_path)
        paths = [str(database_path)] if created else []
        compensation = RemovePathsCompensation(paths)
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            self._require_project(uow.repository(ProjectRepository), project_id)
            result = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="SetupDatabase",
                entity_id=str(database_path),
                summary="Prepared setup database placeholder",
                result={"project_id": str(project_id), "database_path": str(database_path), "created": created, "reversible": created},
                events=[],
                undo_plan=UndoPlan("UndoPrepareSetupDatabase", "Remove database file created by setup", compensation, {**compensation.describe(), "project_id": str(project_id)}),
            )
            uow.commit()
            return result

    def execute_run_server_setup(
        self,
        *,
        project_id: ProjectId,
        server_data_path: str,
        build_number: str,
        options: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> CommandExecutionResult:
        setup_run_id = StableIdentifier.new()
        started = datetime.now(UTC)
        steps: list[dict[str, Any]] = []
        artifact = self.execute_install_artifact(project_id=project_id, build_number=build_number)
        steps.append(_step("install_artifact", artifact))
        self._publish_setup_step_progress(project_id, str(setup_run_id), "install_artifact", "completed")
        config = self.execute_generate_server_cfg(project_id=project_id, server_data_path=server_data_path, options=options)
        steps.append(_step("generate_server_cfg", config))
        self._publish_setup_step_progress(project_id, str(setup_run_id), "generate_server_cfg", "completed")
        checks = self.execute_run_dependency_checks(project_id=project_id, server_data_path=server_data_path)
        steps.append(_step("dependency_checks", checks))
        self._publish_setup_step_progress(project_id, str(setup_run_id), "dependency_checks", "completed")
        database = self.execute_prepare_database(project_id=project_id, server_data_path=server_data_path)
        steps.append(_step("prepare_database", database))
        self._publish_setup_step_progress(project_id, str(setup_run_id), "prepare_database", "completed")
        preview = CommandPreview(
            "RunServerSetup",
            "Run setup wizard steps",
            {"project_id": str(project_id), "server_data_path": server_data_path, "steps": [step["step_key"] for step in steps]},
            risk_level=RiskLevel.HIGH,
        )
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(SetupRepository)
            repository.create_setup_run(
                setup_run_id=setup_run_id,
                project_id=project_id,
                environment_id=None,
                setup_recipe_id=None,
                status="running",
                dry_run=False,
                started_at=started,
                summary={"steps": steps},
            )
            uow.session.flush()
            for index, step in enumerate(steps, start=1):
                repository.add_setup_step(
                    setup_step_id=StableIdentifier.new(),
                    setup_run_id=setup_run_id,
                    step_order=index,
                    step_key=step["step_key"],
                    status="succeeded",
                    started_at=started,
                    finished_at=datetime.now(UTC),
                    details=step,
                )
            repository.finish_setup_run(setup_run_id, "succeeded", datetime.now(UTC), {"steps": steps})
            result = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="SetupRun",
                entity_id=str(setup_run_id),
                summary="Completed setup wizard run",
                result={"project_id": str(project_id), "setup_run_id": str(setup_run_id), "steps": steps},
                events=[setup_run_completed(project_id, str(setup_run_id), "succeeded")],
                idempotency_key=idempotency_key,
            )
            uow.commit()
            return result

    def preview_start_server(
        self,
        *,
        project_id: ProjectId,
        fxserver_path: str,
        server_data_path: str,
        txadmin_mode: bool = False,
        extra_args: list[str] | None = None,
    ) -> CommandPreview:
        plan = self._process_launch_plan(fxserver_path, server_data_path, txadmin_mode, extra_args)
        return CommandPreview(
            "StartServerProcess",
            "Start supervised FXServer process",
            {
                "project_id": str(project_id),
                "executable_path": str(plan.executable_path),
                "working_directory": str(plan.working_directory),
                "arguments": plan.arguments,
                "mode": plan.mode,
            },
            warnings=["Stop uses terminate followed by full process-tree kill; stdin shutdown is not reliable for FXServer."],
            risk_level=RiskLevel.HIGH,
        )

    def dry_run_start_server(self, **kwargs: Any) -> DryRunResult:
        preview = self.preview_start_server(**kwargs)
        return DryRunResult(preview.command_type, True, preview.preview, preview.warnings)

    def execute_start_server(
        self,
        *,
        project_id: ProjectId,
        fxserver_path: str,
        server_data_path: str,
        txadmin_mode: bool = False,
        extra_args: list[str] | None = None,
    ) -> CommandExecutionResult:
        preview = self.preview_start_server(
            project_id=project_id,
            fxserver_path=fxserver_path,
            server_data_path=server_data_path,
            txadmin_mode=txadmin_mode,
            extra_args=extra_args,
        )
        plan = self._process_launch_plan(fxserver_path, server_data_path, txadmin_mode, extra_args)
        process_run_id = StableIdentifier.new()
        status = self._process_port.start(str(process_run_id), str(project_id), plan)
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            self._require_project(uow.repository(ProjectRepository), project_id)
            uow.repository(SetupRepository).add_process_run(
                process_run_id=process_run_id,
                project_id=project_id,
                pid=int(status.pid or 0),
                state=status.state.value,
                launch={
                    "executable_path": str(plan.executable_path),
                    "working_directory": str(plan.working_directory),
                    "arguments": plan.arguments,
                    "mode": plan.mode,
                },
                started_at=datetime.now(UTC),
                stdout_tail=status.stdout_tail,
                stderr_tail=status.stderr_tail,
            )
            result = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="ServerProcess",
                entity_id=str(process_run_id),
                summary="Started supervised FXServer process",
                result=_process_status_data(status),
                events=[server_started(project_id, str(process_run_id), int(status.pid or 0))],
                undo_plan=UndoPlan(
                    "UndoStartServerProcess",
                    "Stop supervised server process",
                    StopServerProcessCompensation(self._process_port, project_id, str(process_run_id)),
                    {"action_type": "stop_server_process", "project_id": str(project_id), "process_run_id": str(process_run_id)},
                ),
            )
            uow.commit()
            return result

    def preview_stop_server(self, *, project_id: ProjectId, process_run_id: str) -> CommandPreview:
        return CommandPreview(
            "StopServerProcess",
            "Stop supervised FXServer process",
            {"project_id": str(project_id), "process_run_id": process_run_id, "termination": "terminate then full-tree kill"},
            risk_level=RiskLevel.HIGH,
        )

    def dry_run_stop_server(self, **kwargs: Any) -> DryRunResult:
        preview = self.preview_stop_server(**kwargs)
        return DryRunResult(preview.command_type, True, preview.preview, preview.warnings)

    def execute_stop_server(self, *, project_id: ProjectId, process_run_id: str) -> CommandExecutionResult:
        preview = self.preview_stop_server(project_id=project_id, process_run_id=process_run_id)
        with self._container.session_factory() as session:
            repository = SetupRepository(RepositoryContext(session=session, project_id=project_id))
            if repository.get_process_run(project_id, StableIdentifier(process_run_id)) is None:
                raise SetupApplicationError(ErrorCode.NOT_FOUND, f"Process run not found: {process_run_id}")
        status = self._process_port.stop(process_run_id)
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            repository = uow.repository(SetupRepository)
            repository.update_process_run(
                project_id=project_id,
                process_run_id=StableIdentifier(process_run_id),
                state=ServerProcessState.STOPPED.value,
                stopped_at=datetime.now(UTC),
                exit_code=status.exit_code,
                stdout_tail=status.stdout_tail,
                stderr_tail=status.stderr_tail,
            )
            result = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="ServerProcess",
                entity_id=process_run_id,
                summary="Stopped supervised FXServer process",
                result=_process_status_data(status),
                events=[server_stopped(project_id, process_run_id, status.exit_code)],
            )
            uow.commit()
            return result

    def execute_restart_server(
        self,
        *,
        project_id: ProjectId,
        process_run_id: str,
        fxserver_path: str,
        server_data_path: str,
        txadmin_mode: bool = False,
        extra_args: list[str] | None = None,
    ) -> CommandExecutionResult:
        preview = CommandPreview(
            "RestartServerProcess",
            "Restart supervised FXServer process",
            {"project_id": str(project_id), "stopped_process_run_id": process_run_id},
            risk_level=RiskLevel.HIGH,
        )
        stopped = self.execute_stop_server(project_id=project_id, process_run_id=process_run_id)
        started = self.execute_start_server(
            project_id=project_id,
            fxserver_path=fxserver_path,
            server_data_path=server_data_path,
            txadmin_mode=txadmin_mode,
            extra_args=extra_args,
        )
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            result = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="ServerProcess",
                entity_id=str(started.result["process_run_id"]),
                summary="Restarted supervised FXServer process",
                result={
                    "project_id": str(project_id),
                    "process_run_id": started.result["process_run_id"],
                    "state": started.result["state"],
                    "pid": started.result["pid"],
                    "stopped_process_run_id": process_run_id,
                    "started_process_run_id": started.result["process_run_id"],
                    "stopped_command_execution_id": str(stopped.command_execution_id),
                    "started_command_execution_id": str(started.command_execution_id),
                },
                events=[],
            )
            uow.commit()
            return result

    def get_process_status(self, project_id: ProjectId, process_run_id: str) -> dict[str, Any]:
        status = self._process_port.status(process_run_id)
        with self._container.session_factory() as session:
            repository = SetupRepository(RepositoryContext(session=session, project_id=project_id))
            record = repository.get_process_run(project_id, StableIdentifier(process_run_id))
            if record is None:
                raise SetupApplicationError(ErrorCode.NOT_FOUND, f"Process run not found: {process_run_id}")
            return _process_status_data(status) if status else _process_record_data(record)

    def record_process_exit(self, process_run_id: str, exit_code: int | None, expected: bool, stdout_tail: list[str], stderr_tail: list[str]) -> None:
        with self._container.create_unit_of_work() as uow:
            uow.begin()
            record = uow.session.get(SetupProcessRunRecord, process_run_id)
            if record is None:
                uow.rollback()
                return
            project_id = ProjectId(record.project_id)
            state = ServerProcessState.STOPPED if expected else ServerProcessState.CRASHED
            uow.repository(SetupRepository).update_process_run(
                project_id=project_id,
                process_run_id=StableIdentifier(process_run_id),
                state=state.value,
                stopped_at=datetime.now(UTC),
                exit_code=exit_code,
                stdout_tail=stdout_tail,
                stderr_tail=stderr_tail,
            )
            if not expected:
                event = server_crashed(project_id, process_run_id, exit_code)
                uow.repository(AuditRepository).record_domain_event(event, published_at=datetime.now(UTC))
                uow.collect_event(event)
            uow.commit()

    def undo(self, undo_plan: UndoPlan) -> CommandExecutionResult:
        project_id_value = undo_plan.payload.get("project_id")
        project_id = ProjectId(str(project_id_value)) if project_id_value else None
        preview = CommandPreview(undo_plan.command_type, undo_plan.summary, {"undo": undo_plan.payload}, risk_level=RiskLevel.HIGH)
        with self._container.create_unit_of_work(project_id) as uow:
            uow.begin()
            action_result = undo_plan.action.apply(CommandContext(uow=uow))
            result = self._recorder.record_success(
                uow=uow,
                preview=preview,
                project_id=project_id,
                entity_type="SetupUndo",
                entity_id=str(project_id) if project_id else "global",
                summary=undo_plan.summary,
                result=action_result,
                events=[],
                undo_plan=None,
            )
            uow.commit()
            return result

    def get_setup_run(self, project_id: ProjectId, setup_run_id: StableIdentifier) -> dict[str, Any]:
        with self._container.session_factory() as session:
            repository = SetupRepository(RepositoryContext(session=session, project_id=project_id))
            run = repository.get_setup_run(project_id, setup_run_id)
            if run is None:
                raise SetupApplicationError(ErrorCode.NOT_FOUND, f"Setup run not found: {setup_run_id}")
            return {"setup_run_id": run.setup_run_id, "project_id": run.project_id, "status": run.status, "steps": [_setup_step_data(step) for step in repository.list_setup_steps(setup_run_id)]}

    def list_dependency_checks(self, project_id: ProjectId) -> list[dict[str, Any]]:
        with self._container.session_factory() as session:
            repository = SetupRepository(RepositoryContext(session=session, project_id=project_id))
            return [_dependency_record_data(record) for record in repository.list_dependency_checks(project_id)]

    def _artifact_install_plan(self, *, platform: str, channel: str, build_number: str) -> ArtifactInstallPlan:
        artifacts = self._artifact_client.discover(ArtifactPlatform(platform), ArtifactChannel(channel))
        artifact = next((item for item in artifacts if item.build_number == build_number), artifacts[0])
        root = self._container.app_data_dir / "artifacts" / "fxserver" / artifact.platform.value / artifact.build_number
        download = self._container.app_data_dir / "artifacts" / "downloads" / f"fxserver-{artifact.platform.value}-{artifact.build_number}.zip"
        warnings = ["Artifact checksum unavailable; verifying by successful extraction only."] if not artifact.sha256 else []
        return ArtifactInstallPlan(artifact=artifact, download_path=download, extract_path=root, warnings=warnings)

    def _server_config_plan(self, server_data_path: str, options: dict[str, Any]) -> Any:
        path = Path(server_data_path).expanduser().resolve()
        cfg = path / "server.cfg"
        prior = self._filesystem.read_text(cfg)
        content = _server_cfg_content(options)
        warnings = ["Existing server.cfg will be snapshotted and can be restored by undo."] if prior is not None else []
        return type("ServerConfigPlan", (), {"server_data_path": path, "server_cfg_path": cfg, "prior_content": prior, "content": content, "warnings": warnings})()

    def _process_launch_plan(
        self,
        fxserver_path: str,
        server_data_path: str,
        txadmin_mode: bool,
        extra_args: list[str] | None,
    ) -> ProcessLaunchPlan:
        executable = Path(fxserver_path).expanduser().resolve()
        working_directory = Path(server_data_path).expanduser().resolve()
        if extra_args is not None:
            arguments = extra_args
            mode = "custom"
        elif txadmin_mode:
            arguments = []
            mode = "txadmin"
        else:
            arguments = ["+exec", "server.cfg"]
            mode = "direct"
        return ProcessLaunchPlan(executable_path=executable, working_directory=working_directory, arguments=arguments, mode=mode)

    def _record_download_progress(self, project_id: ProjectId, item: Any, progress: list[dict[str, Any]]) -> None:
        entry = {
            "operation_id": item.operation_id,
            "bytes_received": item.bytes_received,
            "total_bytes": item.total_bytes,
            "message": item.message,
        }
        progress.append(entry)
        if self._stream_publisher is not None:
            self._stream_publisher.publish_operation_progress(
                project_id=project_id,
                operation_id=item.operation_id,
                message=item.message,
                bytes_received=item.bytes_received,
                total_bytes=item.total_bytes,
            )

    def _publish_setup_step_progress(self, project_id: ProjectId, setup_run_id: str, step_key: str, status: str) -> None:
        if self._stream_publisher is None:
            return
        self._stream_publisher.publish_operation_progress(
            project_id=project_id,
            operation_id=setup_run_id,
            message=f"Setup step {step_key} {status}",
            step_key=step_key,
        )

    def _dependency_checks(self, server_data_path: str, categories: list[str] | None) -> list[dict[str, Any]]:
        path = Path(server_data_path).expanduser().resolve()
        selected = set(categories or [item.value for item in DependencyCategory])
        checks: list[dict[str, Any]] = []
        if DependencyCategory.FILESYSTEM.value in selected:
            checks.append({"check_key": "server_data_directory", "category": "filesystem", "status": "pass" if path.exists() else "warning", "message": "server-data directory exists" if path.exists() else "server-data directory will be created by setup", "details": {"path": str(path)}})
        if DependencyCategory.CONFIG.value in selected:
            checks.append({"check_key": "server_cfg", "category": "config", "status": "pass" if (path / "server.cfg").exists() else "warning", "message": "server.cfg present" if (path / "server.cfg").exists() else "server.cfg not generated yet", "details": {"path": str(path / "server.cfg")}})
        if DependencyCategory.DATABASE.value in selected:
            checks.append({"check_key": "database_placeholder", "category": "database", "status": "skipped", "message": "External DB creation is deferred; local placeholder can be prepared.", "details": {"reversible": True}})
        return checks

    def _require_project(self, repository: ProjectRepository, project_id: ProjectId) -> None:
        if repository.get_project(project_id) is None:
            raise SetupApplicationError(ErrorCode.NOT_FOUND, f"Project not found: {project_id}")


def _server_cfg_content(options: dict[str, Any]) -> str:
    hostname = str(options.get("hostname", "Atlas FiveM Server")).replace('"', "'")
    project_name = str(options.get("project_name", hostname)).replace('"', "'")
    max_clients = int(options.get("max_clients", 48))
    license_key = str(options.get("license_key", "CHANGE_ME"))
    resources = options.get("ensure_resources", ["mapmanager", "chat", "spawnmanager", "sessionmanager", "hardcap", "baseevents"])
    lines = [
        "# Generated by Atlas. Review secrets before running FXServer.",
        'endpoint_add_tcp "0.0.0.0:30120"',
        'endpoint_add_udp "0.0.0.0:30120"',
        f'sv_hostname "{hostname}"',
        f'sets sv_projectName "{project_name}"',
        f"sv_maxclients {max_clients}",
        f'sv_licenseKey "{license_key}"',
        "",
        "# Baseline resources",
    ]
    lines.extend(f"ensure {resource}" for resource in resources)
    return "\n".join(lines) + "\n"


def _artifact_data(artifact: ArtifactVersion) -> dict[str, Any]:
    return {
        "artifact_version_id": artifact.artifact_version_id,
        "platform": artifact.platform.value,
        "channel": artifact.channel.value,
        "build_number": artifact.build_number,
        "download_url": artifact.download_url,
        "sha256": artifact.sha256,
        "released_at": artifact.released_at,
        "metadata": artifact.metadata,
    }


def _artifact_record_data(record: Any) -> dict[str, Any]:
    return {
        "artifact_version_id": record.artifact_version_id,
        "platform": record.platform,
        "channel": record.channel,
        "build_number": record.build_number,
        "download_url": record.download_url,
        "sha256": record.sha256,
        "released_at": record.released_at,
        "discovered_at": record.discovered_at,
        "metadata": record.metadata_json or {},
    }


def _pin_data(record: Any) -> dict[str, Any]:
    return {
        "artifact_pin_id": record.artifact_pin_id,
        "project_id": record.project_id,
        "environment_id": record.environment_id,
        "artifact_version_id": record.artifact_version_id,
        "channel_preference": record.channel_preference,
    }


def _step(step_key: str, result: CommandExecutionResult) -> dict[str, Any]:
    return {
        "step_key": step_key,
        "command_execution_id": str(result.command_execution_id),
        "audit_ref": result.audit_ref.ref_id,
        "result": result.result,
        "undo_plan": result.undo_plan.payload if result.undo_plan else None,
    }


def _setup_step_data(record: Any) -> dict[str, Any]:
    return {"setup_step_id": record.setup_step_id, "step_key": record.step_key, "status": record.status, "details": record.details_json or {}}


def _dependency_record_data(record: Any) -> dict[str, Any]:
    return {
        "dependency_check_id": record.dependency_check_id,
        "project_id": record.project_id,
        "check_key": record.check_key,
        "category": record.category,
        "status": record.status,
        "message": record.message,
        "details": record.details_json or {},
    }


def _process_status_data(status: Any) -> dict[str, Any]:
    return {
        "process_run_id": status.process_run_id,
        "project_id": status.project_id,
        "state": status.state.value if hasattr(status.state, "value") else status.state,
        "pid": status.pid,
        "started_at": status.started_at,
        "stopped_at": status.stopped_at,
        "exit_code": status.exit_code,
        "stdout_tail": status.stdout_tail,
        "stderr_tail": status.stderr_tail,
    }


def _process_record_data(record: Any) -> dict[str, Any]:
    return {
        "process_run_id": record.process_run_id,
        "project_id": record.project_id,
        "state": record.state,
        "pid": record.pid,
        "started_at": record.started_at,
        "stopped_at": record.stopped_at,
        "exit_code": record.exit_code,
        "stdout_tail": record.stdout_tail_json or [],
        "stderr_tail": record.stderr_tail_json or [],
    }
