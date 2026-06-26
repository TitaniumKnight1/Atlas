from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.api.dependencies import get_container
from backend.api.schemas.incident import CompareIncidentsRequest, ErrorPayload, ResponseEnvelope
from backend.application.incident import IncidentApplicationError
from backend.domain.shared_kernel import ProjectId
from backend.infrastructure.di import ApplicationContainer


router = APIRouter(prefix="/api/v1", tags=["incidents"])


@router.get("/projects/{project_id}/incidents", response_model=ResponseEnvelope)
def list_incidents(
    project_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(container.create_incident_service().list_incidents(ProjectId(project_id), limit=limit))
    except IncidentApplicationError as error:
        return _failure(error)


@router.get("/projects/{project_id}/incidents/{incident_group_id}", response_model=ResponseEnvelope)
def get_incident(project_id: str, incident_group_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _success(container.create_incident_service().get_incident(ProjectId(project_id), incident_group_id))
    except IncidentApplicationError as error:
        return _failure(error)


@router.get("/projects/{project_id}/incidents/{incident_group_id}/timeline", response_model=ResponseEnvelope)
def get_group_timeline(project_id: str, incident_group_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _success(container.create_incident_service().get_group_timeline(ProjectId(project_id), incident_group_id))
    except IncidentApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/incidents/compare", response_model=ResponseEnvelope)
def compare_incidents(
    project_id: str,
    body: CompareIncidentsRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(
            container.create_incident_service().compare_incidents(ProjectId(project_id), incident_group_ids=body.incident_group_ids)
        )
    except IncidentApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/incidents/migrate-grouping", response_model=ResponseEnvelope)
def migrate_grouping(project_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _success(container.create_incident_service().migrate_placeholder_incidents(ProjectId(project_id)))
    except IncidentApplicationError as error:
        return _failure(error)


@router.get("/projects/{project_id}/incidents/occurrences/{occurrence_id}/timeline", response_model=ResponseEnvelope)
def get_occurrence_timeline(
    project_id: str,
    occurrence_id: str,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(container.create_incident_service().get_occurrence_timeline(ProjectId(project_id), occurrence_id))
    except IncidentApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/incidents/capture/crash", response_model=ResponseEnvelope)
def capture_crash_explicit(
    project_id: str,
    process_run_id: str,
    exit_code: int | None = None,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(
            container.create_incident_service().capture_server_crash(
                ProjectId(project_id),
                process_run_id=process_run_id,
                exit_code=exit_code,
            )
        )
    except IncidentApplicationError as error:
        return _failure(error)


def _success(data: dict | list[dict]) -> ResponseEnvelope:
    return ResponseEnvelope(ok=True, data=data)


def _failure(error: IncidentApplicationError) -> ResponseEnvelope:
    return ResponseEnvelope(ok=False, error=ErrorPayload(code=error.code.value, message=str(error)))
