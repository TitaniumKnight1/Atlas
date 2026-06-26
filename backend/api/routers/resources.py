from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.api.dependencies import get_container
from backend.api.schemas.resources import (
    ErrorPayload,
    RescanResourcesRequest,
    ResourceSourceRequest,
    ResponseEnvelope,
    SetEnabledStateRequest,
    UpdateResourceRequest,
)
from backend.application.resources import InstallSource, ResourceApplicationError, ResourceLifecycleError
from backend.domain.shared_kernel import ProjectId
from backend.infrastructure.di import ApplicationContainer


router = APIRouter(prefix="/api/v1", tags=["resources"])


@router.get("/projects/{project_id}/resources", response_model=ResponseEnvelope)
def list_resources(project_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    return _success(container.create_resource_service().list_resources(ProjectId(project_id)))


@router.get("/projects/{project_id}/resources/{resource_id}", response_model=ResponseEnvelope)
def get_resource(project_id: str, resource_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _success(container.create_resource_service().get_resource(ProjectId(project_id), resource_id))
    except ResourceApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/resources/scan", response_model=ResponseEnvelope)
def scan_resources(project_id: str, request: RescanResourcesRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _success(
            container.create_resource_service().execute_rescan_resources(
                project_id=ProjectId(project_id), path_filters=request.path_filters
            )
        )
    except ResourceApplicationError as error:
        return _failure(error)


@router.get("/projects/{project_id}/resources/graph", response_model=ResponseEnvelope)
def get_graph(project_id: str, root: str | None = None, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    return _success(container.create_resource_service().get_dependency_graph(ProjectId(project_id), root))


@router.get("/projects/{project_id}/resources/graph/health", response_model=ResponseEnvelope)
def get_graph_health(project_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    return _success(container.create_resource_service().get_graph_health(ProjectId(project_id)))


@router.get("/projects/{project_id}/resources/graph/order", response_model=ResponseEnvelope)
def get_safe_order(project_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    return _success(container.create_resource_service().get_safe_start_order(ProjectId(project_id)))


@router.get("/projects/{project_id}/resources/{resource_id}/dependencies", response_model=ResponseEnvelope)
def get_dependencies(
    project_id: str,
    resource_id: str,
    transitive: bool = Query(default=False),
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(
            container.create_resource_service().get_resource_dependencies(ProjectId(project_id), resource_id, transitive)
        )
    except ResourceApplicationError as error:
        return _failure(error)


@router.get("/projects/{project_id}/resources/{resource_id}/dependents", response_model=ResponseEnvelope)
def get_dependents(
    project_id: str,
    resource_id: str,
    transitive: bool = Query(default=False),
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(container.create_resource_service().get_resource_dependents(ProjectId(project_id), resource_id, transitive))
    except ResourceApplicationError as error:
        return _failure(error)


@router.get("/projects/{project_id}/resources/{resource_id}/health", response_model=ResponseEnvelope)
def get_health(project_id: str, resource_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _success(container.create_resource_service().get_resource_health(ProjectId(project_id), resource_id))
    except ResourceApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/resources/install-plan", response_model=ResponseEnvelope)
def install_plan(project_id: str, request: ResourceSourceRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        preview = container.create_resource_lifecycle_service().preview_install_resource(
            project_id=ProjectId(project_id),
            source=InstallSource(request.source_type, request.source_uri),
            resource_name=request.resource_name,
            enable=request.enable,
        )
        return ResponseEnvelope(ok=True, data=preview.preview, warnings=preview.warnings)
    except ResourceLifecycleError as error:
        return _lifecycle_failure(error)


@router.post("/projects/{project_id}/resources/install-dry-run", response_model=ResponseEnvelope)
def install_dry_run(project_id: str, request: ResourceSourceRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        dry_run = container.create_resource_lifecycle_service().dry_run_install_resource(
            project_id=ProjectId(project_id),
            source=InstallSource(request.source_type, request.source_uri),
            resource_name=request.resource_name,
            enable=request.enable,
        )
        return ResponseEnvelope(ok=dry_run.valid, data=dry_run.simulation, warnings=dry_run.warnings)
    except ResourceLifecycleError as error:
        return _lifecycle_failure(error)


@router.post("/projects/{project_id}/resources/install", response_model=ResponseEnvelope)
def install_resource(project_id: str, request: ResourceSourceRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        result = container.create_resource_lifecycle_service().execute_install_resource(
            project_id=ProjectId(project_id),
            source=InstallSource(request.source_type, request.source_uri),
            resource_name=request.resource_name,
            enable=request.enable,
        )
        return _command_result(result)
    except ResourceLifecycleError as error:
        return _lifecycle_failure(error)


@router.post("/projects/{project_id}/resources/{resource_id}/update-plan", response_model=ResponseEnvelope)
def update_plan(
    project_id: str, resource_id: str, request: UpdateResourceRequest, container: ApplicationContainer = Depends(get_container)
) -> ResponseEnvelope:
    try:
        preview = container.create_resource_lifecycle_service().preview_update_resource(
            project_id=ProjectId(project_id),
            resource_id=resource_id,
            source=InstallSource(request.source_type, request.source_uri),
        )
        return ResponseEnvelope(ok=True, data=preview.preview, warnings=preview.warnings)
    except ResourceLifecycleError as error:
        return _lifecycle_failure(error)


@router.post("/projects/{project_id}/resources/{resource_id}/update", response_model=ResponseEnvelope)
def update_resource(
    project_id: str, resource_id: str, request: UpdateResourceRequest, container: ApplicationContainer = Depends(get_container)
) -> ResponseEnvelope:
    try:
        result = container.create_resource_lifecycle_service().execute_update_resource(
            project_id=ProjectId(project_id),
            resource_id=resource_id,
            source=InstallSource(request.source_type, request.source_uri),
        )
        return _command_result(result)
    except ResourceLifecycleError as error:
        return _lifecycle_failure(error)


@router.post("/projects/{project_id}/resources/{resource_id}/enabled-state-plan", response_model=ResponseEnvelope)
def enabled_state_plan(
    project_id: str, resource_id: str, request: SetEnabledStateRequest, container: ApplicationContainer = Depends(get_container)
) -> ResponseEnvelope:
    try:
        preview = container.create_resource_lifecycle_service().preview_set_enabled_state(
            project_id=ProjectId(project_id), resource_id=resource_id, enabled=request.enabled
        )
        return ResponseEnvelope(ok=True, data=preview.preview, warnings=preview.warnings)
    except ResourceLifecycleError as error:
        return _lifecycle_failure(error)


@router.post("/projects/{project_id}/resources/{resource_id}/enabled-state", response_model=ResponseEnvelope)
def set_enabled_state(
    project_id: str, resource_id: str, request: SetEnabledStateRequest, container: ApplicationContainer = Depends(get_container)
) -> ResponseEnvelope:
    try:
        result = container.create_resource_lifecycle_service().execute_set_enabled_state(
            project_id=ProjectId(project_id), resource_id=resource_id, enabled=request.enabled
        )
        return _command_result(result)
    except ResourceLifecycleError as error:
        return _lifecycle_failure(error)


@router.post("/projects/{project_id}/resources/{resource_id}/delete-plan", response_model=ResponseEnvelope)
def delete_plan(project_id: str, resource_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        preview = container.create_resource_lifecycle_service().preview_delete_resource(
            project_id=ProjectId(project_id), resource_id=resource_id
        )
        return ResponseEnvelope(ok=True, data=preview.preview, warnings=preview.warnings)
    except ResourceLifecycleError as error:
        return _lifecycle_failure(error)


@router.post("/projects/{project_id}/resources/{resource_id}/delete", response_model=ResponseEnvelope)
def delete_resource(project_id: str, resource_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        result = container.create_resource_lifecycle_service().execute_delete_resource(
            project_id=ProjectId(project_id), resource_id=resource_id
        )
        return _command_result(result)
    except ResourceLifecycleError as error:
        return _lifecycle_failure(error)


def _success(data: dict | list[dict]) -> ResponseEnvelope:
    return ResponseEnvelope(ok=True, data=data)


def _failure(error: ResourceApplicationError) -> ResponseEnvelope:
    return ResponseEnvelope(ok=False, error=ErrorPayload(code=error.code.value, message=str(error)))


def _lifecycle_failure(error: ResourceLifecycleError) -> ResponseEnvelope:
    return ResponseEnvelope(ok=False, error=ErrorPayload(code=error.code.value, message=str(error)))


def _command_result(result) -> ResponseEnvelope:
    return ResponseEnvelope(
        ok=True,
        data=result.result,
        audit_ref={"ref_type": result.audit_ref.ref_type, "ref_id": result.audit_ref.ref_id},
    )
