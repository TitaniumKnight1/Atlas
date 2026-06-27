from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.api.dependencies import get_container
from backend.api.schemas.plugin import (
    ErrorPayload,
    GrantCapabilitiesRequest,
    InvokeContributionRequest,
    RegisterPluginRequest,
    ResponseEnvelope,
    RevokeCapabilityRequest,
    SetGlobalPluginRequest,
    SetPluginEnabledRequest,
    StartPluginRunRequest,
    ValidateManifestRequest,
)
from backend.application.plugin import PluginApplicationError
from backend.domain.shared_kernel import ErrorCode, ProjectId
from backend.infrastructure.di import ApplicationContainer


router = APIRouter(prefix="/api/v1", tags=["plugins"])


@router.get("/plugin/settings", response_model=ResponseEnvelope)
def get_plugin_settings(container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    return _success(container.create_plugin_service().get_global_settings())


@router.patch("/plugin/settings", response_model=ResponseEnvelope)
def set_plugin_settings(
    request: SetGlobalPluginRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    return _success(container.create_plugin_service().set_global_enabled(enabled=request.global_enabled))


@router.get("/plugins", response_model=ResponseEnvelope)
def list_plugins(container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    return _success(container.create_plugin_service().list_plugins())


@router.get("/plugins/{plugin_id}", response_model=ResponseEnvelope)
def get_plugin(plugin_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _success(container.create_plugin_service().get_plugin(plugin_id))
    except PluginApplicationError as error:
        return _failure(error)


@router.post("/plugins/validate-manifest", response_model=ResponseEnvelope)
def validate_manifest(
    request: ValidateManifestRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        service = container.create_plugin_service()
        if request.manifest_path:
            return _success(service.validate_manifest_file(request.manifest_path))
        if request.manifest:
            return _success(service.validate_manifest(request.manifest))
        return _failure(PluginApplicationError(ErrorCode.VALIDATION_FAILED, "manifest or manifest_path is required"))
    except PluginApplicationError as error:
        return _failure(error)
    except Exception as error:  # noqa: BLE001
        return _failure(PluginApplicationError(ErrorCode.VALIDATION_FAILED, str(error)))


@router.post("/plugins", response_model=ResponseEnvelope)
def register_plugin(
    request: RegisterPluginRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(
            container.create_plugin_service().register_plugin(
                request.manifest,
                source_ref=request.source_ref,
                idempotency_key=request.idempotency_key,
            )
        )
    except PluginApplicationError as error:
        return _failure(error)


@router.patch("/plugins/{plugin_id}/state", response_model=ResponseEnvelope)
def set_plugin_state(
    plugin_id: str,
    request: SetPluginEnabledRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(container.create_plugin_service().set_plugin_enabled(plugin_id, enabled=request.enabled))
    except PluginApplicationError as error:
        return _failure(error)


@router.get("/projects/{project_id}/plugins/{plugin_id}/capabilities", response_model=ResponseEnvelope)
def list_plugin_capabilities(
    project_id: str,
    plugin_id: str,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(container.create_plugin_service().list_capabilities(plugin_id, ProjectId(project_id)))
    except PluginApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/plugins/{plugin_id}/capabilities/grant", response_model=ResponseEnvelope)
def grant_plugin_capabilities(
    project_id: str,
    plugin_id: str,
    request: GrantCapabilitiesRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(
            container.create_plugin_service().grant_capabilities(
                plugin_id,
                ProjectId(project_id),
                capabilities=request.capabilities,
                trust_acknowledgment=request.trust_acknowledgment,
                idempotency_key=request.idempotency_key,
            )
        )
    except PluginApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/plugins/{plugin_id}/capabilities/revoke", response_model=ResponseEnvelope)
def revoke_plugin_capability(
    project_id: str,
    plugin_id: str,
    request: RevokeCapabilityRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(
            container.create_plugin_service().revoke_capability(
                plugin_id,
                ProjectId(project_id),
                capability=request.capability,
                idempotency_key=request.idempotency_key,
            )
        )
    except PluginApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/plugins/{plugin_id}/runtime/run", response_model=ResponseEnvelope)
def run_plugin_runtime(
    project_id: str,
    plugin_id: str,
    request: StartPluginRunRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(
            container.create_plugin_host_service().run_plugin(
                plugin_id,
                ProjectId(project_id),
                mode=request.mode,
            )
        )
    except PluginApplicationError as error:
        return _failure(error)


@router.get("/projects/{project_id}/plugins/{plugin_id}/runtime/{runtime_id}", response_model=ResponseEnvelope)
def get_plugin_runtime(
    project_id: str,
    plugin_id: str,
    runtime_id: str,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(container.create_plugin_host_service().get_runtime(runtime_id, ProjectId(project_id)))
    except PluginApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/plugins/{plugin_id}/runtime/{runtime_id}/stop", response_model=ResponseEnvelope)
def stop_plugin_runtime(
    project_id: str,
    plugin_id: str,
    runtime_id: str,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(container.create_plugin_host_service().stop_plugin(runtime_id, ProjectId(project_id)))
    except PluginApplicationError as error:
        return _failure(error)


@router.get("/projects/{project_id}/plugins/{plugin_id}/capability-calls", response_model=ResponseEnvelope)
def list_plugin_capability_calls(
    project_id: str,
    plugin_id: str,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(container.create_plugin_host_service().list_capability_calls(plugin_id, ProjectId(project_id)))
    except PluginApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/plugins/{plugin_id}/contributions/register", response_model=ResponseEnvelope)
def register_plugin_contributions(
    project_id: str,
    plugin_id: str,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(container.create_plugin_contribution_service().register_manifest_contributions(plugin_id, ProjectId(project_id)))
    except PluginApplicationError as error:
        return _failure(error)


@router.get("/projects/{project_id}/plugin-contributions", response_model=ResponseEnvelope)
def list_plugin_contributions(
    project_id: str,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(container.create_plugin_contribution_service().list_contributions(ProjectId(project_id)))
    except PluginApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/plugin-contributions/{contribution_id}/invoke", response_model=ResponseEnvelope)
def invoke_plugin_contribution(
    project_id: str,
    contribution_id: str,
    request: InvokeContributionRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(
            container.create_plugin_contribution_service().invoke_contribution(
                contribution_id,
                ProjectId(project_id),
                payload=request.payload,
            )
        )
    except PluginApplicationError as error:
        return _failure(error)


def _success(data: dict | list[dict]) -> ResponseEnvelope:
    return ResponseEnvelope(ok=True, data=data)


def _failure(error: PluginApplicationError) -> ResponseEnvelope:
    code = error.code.value if hasattr(error.code, "value") else str(error.code)
    return ResponseEnvelope(ok=False, error=ErrorPayload(code=code, message=str(error)))
