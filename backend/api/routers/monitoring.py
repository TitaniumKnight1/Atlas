from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from backend.api.dependencies import get_container
from backend.api.schemas.monitoring import CreateAlertRequest, ErrorPayload, ResponseEnvelope, StartCollectionRequest, UpdateAlertRequest
from backend.application.monitoring import MonitoringAlertError, MonitoringApplicationError, MonitoringRetentionError
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


@router.get("/projects/{project_id}/monitoring/alerts", response_model=ResponseEnvelope)
def list_alerts(project_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _success(container.create_monitoring_alert_service().list_alerts(ProjectId(project_id)))
    except MonitoringAlertError as error:
        return _alert_failure(error)


@router.post("/projects/{project_id}/monitoring/alerts", response_model=ResponseEnvelope)
def create_alert(project_id: str, request: CreateAlertRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _success(
            container.create_monitoring_alert_service().create_alert(
                ProjectId(project_id),
                name=request.name,
                severity=request.severity,
                metric_series_id=request.metric_series_id,
                comparator=request.comparator,
                threshold=request.threshold,
                duration_seconds=request.duration_seconds,
                is_enabled=request.is_enabled,
            )
        )
    except MonitoringAlertError as error:
        return _alert_failure(error)


@router.patch("/projects/{project_id}/monitoring/alerts/{monitoring_alert_id}", response_model=ResponseEnvelope)
def update_alert(
    project_id: str,
    monitoring_alert_id: str,
    request: UpdateAlertRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(
            container.create_monitoring_alert_service().update_alert(
                ProjectId(project_id),
                monitoring_alert_id,
                name=request.name,
                severity=request.severity,
                metric_series_id=request.metric_series_id,
                comparator=request.comparator,
                threshold=request.threshold,
                duration_seconds=request.duration_seconds,
                is_enabled=request.is_enabled,
            )
        )
    except MonitoringAlertError as error:
        return _alert_failure(error)


@router.delete("/projects/{project_id}/monitoring/alerts/{monitoring_alert_id}", response_model=ResponseEnvelope)
def delete_alert(project_id: str, monitoring_alert_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _success(container.create_monitoring_alert_service().delete_alert(ProjectId(project_id), monitoring_alert_id))
    except MonitoringAlertError as error:
        return _alert_failure(error)


@router.get("/projects/{project_id}/monitoring/alert-events", response_model=ResponseEnvelope)
def list_alert_events(
    project_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(container.create_monitoring_alert_service().list_alert_events(ProjectId(project_id), limit=limit))
    except MonitoringAlertError as error:
        return _alert_failure(error)


@router.post("/projects/{project_id}/monitoring/alerts/evaluate", response_model=ResponseEnvelope)
def evaluate_alerts(project_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _success(container.create_monitoring_alert_service().evaluate_project(ProjectId(project_id)))
    except MonitoringAlertError as error:
        return _alert_failure(error)


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


@router.get("/projects/{project_id}/monitoring/collection/status", response_model=ResponseEnvelope)
def collection_status(project_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _success(container.create_monitoring_service().collection_status(ProjectId(project_id)))
    except MonitoringApplicationError as error:
        return _failure(error)


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


def _alert_failure(error: MonitoringAlertError) -> ResponseEnvelope:
    return ResponseEnvelope(ok=False, error=ErrorPayload(code=error.code.value, message=str(error)))
