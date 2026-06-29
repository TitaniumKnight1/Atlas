from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.api.dependencies import get_container
from backend.api.schemas.setup import (
    AuditReference,
    DependencyChecksRequest,
    ErrorPayload,
    InstallArtifactRequest,
    PinArtifactRequest,
    PrepareDatabaseRequest,
    RefreshArtifactCatalogRequest,
    ResponseEnvelope,
    RestartServerProcessRequest,
    RunSetupRequest,
    ServerConfigRequest,
    StartServerProcessRequest,
    StopServerProcessRequest,
    ValidateFxserverPathRequest,
)
from backend.application.commands import CommandExecutionResult, CommandPreview, DryRunResult, RiskLevel
from backend.application.setup import SetupApplicationError
from backend.domain.shared_kernel import ProjectId, StableIdentifier
from backend.infrastructure.di import ApplicationContainer


router = APIRouter(prefix="/api/v1", tags=["setup"])


@router.get("/artifacts", response_model=ResponseEnvelope)
def list_artifacts(
    platform: str | None = None,
    channel: str | None = None,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    return _success(container.create_setup_service().list_artifact_versions(platform, channel))


@router.post("/artifacts/refresh", response_model=ResponseEnvelope)
def refresh_artifact_catalog(
    request: RefreshArtifactCatalogRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _command_success(container.create_setup_service().execute_refresh_artifact_catalog(request.platform, request.channel))
    except (SetupApplicationError, ValueError) as error:
        return _failure(_setup_error(error))


@router.put("/projects/{project_id}/artifact-pin", response_model=ResponseEnvelope)
def pin_artifact_version(
    project_id: str,
    request: PinArtifactRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _command_success(
            container.create_setup_service().execute_pin_artifact_version(
                project_id=ProjectId(project_id),
                artifact_version_id=request.artifact_version_id,
                channel_preference=request.channel_preference,
                environment_id=request.environment_id,
                pinned_reason=request.pinned_reason,
            )
        )
    except SetupApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/setup/artifact/install-plan", response_model=ResponseEnvelope)
def install_artifact_plan(project_id: str, request: InstallArtifactRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        preview = container.create_setup_service().preview_install_artifact(
            project_id=ProjectId(project_id), build_number=request.build_number, platform=request.platform, channel=request.channel
        )
        return _success(_preview_data(preview), warnings=preview.warnings)
    except (SetupApplicationError, ValueError) as error:
        return _failure(_setup_error(error))


@router.post("/projects/{project_id}/setup/artifact/install-dry-run", response_model=ResponseEnvelope)
def install_artifact_dry_run(project_id: str, request: InstallArtifactRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        dry_run = container.create_setup_service().dry_run_install_artifact(
            project_id=ProjectId(project_id), build_number=request.build_number, platform=request.platform, channel=request.channel
        )
        return _success(_dry_run_data(dry_run), warnings=dry_run.warnings)
    except (SetupApplicationError, ValueError) as error:
        return _failure(_setup_error(error))


@router.post("/projects/{project_id}/setup/artifact/install", response_model=ResponseEnvelope)
def install_artifact(project_id: str, request: InstallArtifactRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _command_success(
            container.create_setup_service().execute_install_artifact(
                project_id=ProjectId(project_id), build_number=request.build_number, platform=request.platform, channel=request.channel
            )
        )
    except (SetupApplicationError, ValueError) as error:
        return _failure(_setup_error(error))


@router.post("/projects/{project_id}/setup/server-config/plan", response_model=ResponseEnvelope)
def server_config_plan(project_id: str, request: ServerConfigRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    preview = container.create_setup_service().preview_generate_server_cfg(
        project_id=ProjectId(project_id), server_data_path=request.server_data_path, options=request.options
    )
    return _success(_preview_data(preview), warnings=preview.warnings)


@router.post("/projects/{project_id}/setup/server-config/dry-run", response_model=ResponseEnvelope)
def server_config_dry_run(project_id: str, request: ServerConfigRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    dry_run = container.create_setup_service().dry_run_generate_server_cfg(project_id=ProjectId(project_id), server_data_path=request.server_data_path, options=request.options)
    return _success(_dry_run_data(dry_run), warnings=dry_run.warnings)


@router.post("/projects/{project_id}/setup/server-config/write", response_model=ResponseEnvelope)
def server_config_write(project_id: str, request: ServerConfigRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _command_success(
            container.create_setup_service().execute_generate_server_cfg(
                project_id=ProjectId(project_id), server_data_path=request.server_data_path, options=request.options
            )
        )
    except SetupApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/dependency-checks/run", response_model=ResponseEnvelope)
def run_dependency_checks(project_id: str, request: DependencyChecksRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _command_success(
            container.create_setup_service().execute_run_dependency_checks(
                project_id=ProjectId(project_id), server_data_path=request.server_data_path, categories=request.categories
            )
        )
    except SetupApplicationError as error:
        return _failure(error)


@router.get("/projects/{project_id}/dependency-checks", response_model=ResponseEnvelope)
def list_dependency_checks(project_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    return _success(container.create_setup_service().list_dependency_checks(ProjectId(project_id)))


@router.post("/projects/{project_id}/setup/database/prepare", response_model=ResponseEnvelope)
def prepare_database(project_id: str, request: PrepareDatabaseRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _command_success(
            container.create_setup_service().execute_prepare_database(
                project_id=ProjectId(project_id), server_data_path=request.server_data_path, database_name=request.database_name
            )
        )
    except SetupApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/setup/plan", response_model=ResponseEnvelope)
def plan_server_setup(project_id: str, request: RunSetupRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    preview = CommandPreview(
        "RunServerSetup",
        "Plan setup wizard run",
        {"project_id": project_id, "server_data_path": request.server_data_path, "build_number": request.build_number},
        risk_level=RiskLevel.HIGH,
    )
    return _success(_preview_data(preview), warnings=preview.warnings)


@router.post("/projects/{project_id}/setup/run", response_model=ResponseEnvelope)
def run_server_setup(project_id: str, request: RunSetupRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _command_success(
            container.create_setup_service().execute_run_server_setup(
                project_id=ProjectId(project_id),
                server_data_path=request.server_data_path,
                build_number=request.build_number,
                options=request.options,
                idempotency_key=request.idempotency_key,
            )
        )
    except (SetupApplicationError, ValueError) as error:
        return _failure(_setup_error(error))


@router.get("/projects/{project_id}/setup-runs/{setup_run_id}", response_model=ResponseEnvelope)
def get_setup_run(project_id: str, setup_run_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _success(container.create_setup_service().get_setup_run(ProjectId(project_id), StableIdentifier(setup_run_id)))
    except SetupApplicationError as error:
        return _failure(error)


@router.get("/projects/{project_id}/setup/fxserver/detect", response_model=ResponseEnvelope)
def detect_fxserver(project_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _success(container.create_setup_service().detect_fxserver(project_id=ProjectId(project_id)))
    except SetupApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/setup/fxserver/validate", response_model=ResponseEnvelope)
def validate_fxserver_path_route(
    project_id: str,
    request: ValidateFxserverPathRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    _ = project_id
    return _success(container.create_setup_service().validate_fxserver(fxserver_path=request.fxserver_path))


@router.post("/projects/{project_id}/process/start-plan", response_model=ResponseEnvelope)
def start_process_plan(project_id: str, request: StartServerProcessRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    preview = container.create_setup_service().preview_start_server(
        project_id=ProjectId(project_id),
        fxserver_path=request.fxserver_path,
        server_data_path=request.server_data_path,
        txadmin_mode=request.txadmin_mode,
        extra_args=request.extra_args,
    )
    return _success(_preview_data(preview), warnings=preview.warnings)


@router.post("/projects/{project_id}/process/start", response_model=ResponseEnvelope)
def start_process(project_id: str, request: StartServerProcessRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _command_success(
            container.create_setup_service().execute_start_server(
                project_id=ProjectId(project_id),
                fxserver_path=request.fxserver_path,
                server_data_path=request.server_data_path,
                txadmin_mode=request.txadmin_mode,
                extra_args=request.extra_args,
            )
        )
    except (SetupApplicationError, OSError, KeyError) as error:
        return _failure(_setup_error(error))


@router.post("/projects/{project_id}/process/stop", response_model=ResponseEnvelope)
def stop_process(project_id: str, request: StopServerProcessRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _command_success(container.create_setup_service().execute_stop_server(project_id=ProjectId(project_id), process_run_id=request.process_run_id))
    except (SetupApplicationError, KeyError) as error:
        return _failure(_setup_error(error))


@router.post("/projects/{project_id}/process/restart", response_model=ResponseEnvelope)
def restart_process(project_id: str, request: RestartServerProcessRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _command_success(
            container.create_setup_service().execute_restart_server(
                project_id=ProjectId(project_id),
                process_run_id=request.process_run_id,
                fxserver_path=request.fxserver_path,
                server_data_path=request.server_data_path,
                txadmin_mode=request.txadmin_mode,
                extra_args=request.extra_args,
            )
        )
    except (SetupApplicationError, OSError, KeyError) as error:
        return _failure(_setup_error(error))


@router.get("/projects/{project_id}/process/{process_run_id}", response_model=ResponseEnvelope)
def process_status(project_id: str, process_run_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _success(container.create_setup_service().get_process_status(ProjectId(project_id), process_run_id))
    except SetupApplicationError as error:
        return _failure(error)


def _success(data: dict | list[dict], warnings: list[str] | None = None) -> ResponseEnvelope:
    return ResponseEnvelope(ok=True, data=data, warnings=warnings or [])


def _failure(error: SetupApplicationError) -> ResponseEnvelope:
    return ResponseEnvelope(ok=False, error=ErrorPayload(code=error.code.value, message=str(error)))


def _setup_error(error: Exception) -> SetupApplicationError:
    if isinstance(error, SetupApplicationError):
        return error
    from backend.domain.setup.fxserver_paths import humanize_launch_error
    from backend.domain.shared_kernel import ErrorCode

    if isinstance(error, OSError):
        return SetupApplicationError(ErrorCode.VALIDATION_FAILED, humanize_launch_error(error))
    return SetupApplicationError(ErrorCode.VALIDATION_FAILED, str(error))


def _command_success(result: CommandExecutionResult) -> ResponseEnvelope:
    return ResponseEnvelope(
        ok=True,
        data={
            **result.result,
            "command_plan_id": str(result.command_plan_id),
            "command_execution_id": str(result.command_execution_id),
            "undo_plan": result.undo_plan.payload if result.undo_plan else None,
        },
        audit_ref=AuditReference(ref_type=result.audit_ref.ref_type, ref_id=result.audit_ref.ref_id),
    )


def _preview_data(preview: CommandPreview) -> dict:
    return {"command_type": preview.command_type, "summary": preview.summary, "risk_level": preview.risk_level.value, "preview": preview.preview}


def _dry_run_data(dry_run: DryRunResult) -> dict:
    return {"command_type": dry_run.command_type, "valid": dry_run.valid, "simulation": dry_run.simulation}
