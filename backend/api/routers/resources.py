from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.api.dependencies import get_container
from backend.api.schemas.resources import ErrorPayload, RescanResourcesRequest, ResponseEnvelope
from backend.application.resources import ResourceApplicationError
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


def _success(data: dict | list[dict]) -> ResponseEnvelope:
    return ResponseEnvelope(ok=True, data=data)


def _failure(error: ResourceApplicationError) -> ResponseEnvelope:
    return ResponseEnvelope(ok=False, error=ErrorPayload(code=error.code.value, message=str(error)))
