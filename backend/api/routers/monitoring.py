from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from backend.api.dependencies import get_container
from backend.api.schemas.monitoring import ErrorPayload, ResponseEnvelope, StartCollectionRequest
from backend.application.monitoring import MonitoringApplicationError, MonitoringRetentionError
from backend.domain.shared_kernel import ProjectId
from backend.infrastructure.di import ApplicationContainer


router = APIRouter(prefix="/api/v1", tags=["monitoring"])


@router.get("/projects/{project_id}/monitoring/sources", response_model=ResponseEnvelope)
def list_metric_sources(project_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _success(container.create_monitoring_service().list_sources(ProjectId(project_id)))
    except MonitoringApplicationError as error:
        return _failure(error)


@router.get("/projects/{project_id}/monitoring/latest", response_model=ResponseEnvelope)
def latest_metrics(project_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _success(container.create_monitoring_service().latest_metrics(ProjectId(project_id)))
    except MonitoringApplicationError as error:
        return _failure(error)


@router.get("/projects/{project_id}/monitoring/samples", response_model=ResponseEnvelope)
def recent_samples(
    project_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(container.create_monitoring_service().recent_samples(ProjectId(project_id), limit=limit))
    except MonitoringApplicationError as error:
        return _failure(error)


@router.get("/projects/{project_id}/monitoring/series", response_model=ResponseEnvelope)
def list_metric_series(project_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _success(container.create_monitoring_retention_service().list_series(ProjectId(project_id)))
    except MonitoringRetentionError as error:
        return _retention_failure(error)


@router.get("/projects/{project_id}/monitoring/history", response_model=ResponseEnvelope)
def query_metric_history(
    project_id: str,
    start_at: datetime = Query(...),
    end_at: datetime = Query(...),
    metric_series_id: str | None = None,
    resolution: str | None = Query(default=None, pattern="^(raw|minute|hour)$"),
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(
            container.create_monitoring_retention_service().query_time_window(
                ProjectId(project_id),
                start_at=start_at,
                end_at=end_at,
                metric_series_id=metric_series_id,
                resolution=resolution,
            )
        )
    except MonitoringRetentionError as error:
        return _retention_failure(error)


@router.post("/projects/{project_id}/monitoring/rollup/run", response_model=ResponseEnvelope)
def run_rollup_cycle(project_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _success(container.create_monitoring_retention_service().run_rollup_cycle(ProjectId(project_id)))
    except MonitoringRetentionError as error:
        return _retention_failure(error)


@router.post("/projects/{project_id}/monitoring/collection/start", response_model=ResponseEnvelope)
def start_collection(
    project_id: str,
    request: StartCollectionRequest | None = None,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        service = container.create_monitoring_service()
        interval = request.interval_seconds if request and request.interval_seconds is not None else None
        kwargs = {"interval_seconds": interval} if interval is not None else {}
        return _success(service.start_collection(ProjectId(project_id), **kwargs))
    except MonitoringApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/monitoring/collection/stop", response_model=ResponseEnvelope)
def stop_collection(project_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _success(container.create_monitoring_service().stop_collection(ProjectId(project_id)))
    except MonitoringApplicationError as error:
        return _failure(error)


def _success(data: dict | list[dict]) -> ResponseEnvelope:
    return ResponseEnvelope(ok=True, data=data)


def _failure(error: MonitoringApplicationError) -> ResponseEnvelope:
    return ResponseEnvelope(ok=False, error=ErrorPayload(code=error.code.value, message=str(error)))


def _retention_failure(error: MonitoringRetentionError) -> ResponseEnvelope:
    return ResponseEnvelope(ok=False, error=ErrorPayload(code=error.code.value, message=str(error)))
