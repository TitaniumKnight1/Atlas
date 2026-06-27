from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.api.dependencies import get_container
from backend.api.schemas.backup import (
    CreateBackupPlanRequest,
    EvaluateRetentionRequest,
    ErrorPayload,
    ResponseEnvelope,
    RestoreBackupRequest,
    RunBackupRequest,
    UpdateBackupPlanRequest,
)
from backend.application.backup import BackupApplicationError
from backend.domain.shared_kernel import ProjectId
from backend.infrastructure.di import ApplicationContainer


router = APIRouter(prefix="/api/v1", tags=["backup"])


@router.get("/projects/{project_id}/backups/plans", response_model=ResponseEnvelope)
def list_backup_plans(project_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    return _success(container.create_backup_service().list_plans(ProjectId(project_id)))


@router.post("/projects/{project_id}/backups/plans", response_model=ResponseEnvelope)
def create_backup_plan(
    project_id: str,
    request: CreateBackupPlanRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(
            container.create_backup_service().create_plan(
                ProjectId(project_id),
                name=request.name,
                backup_scope=request.backup_scope,
                retention_policy=request.retention_policy,
                schedule_interval_seconds=request.schedule_interval_seconds,
                is_enabled=request.is_enabled,
            )
        )
    except BackupApplicationError as error:
        return _failure(error)


@router.patch("/projects/{project_id}/backups/plans/{plan_id}", response_model=ResponseEnvelope)
def update_backup_plan(
    project_id: str,
    plan_id: str,
    request: UpdateBackupPlanRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(
            container.create_backup_service().update_plan(
                ProjectId(project_id),
                plan_id=plan_id,
                retention_policy=request.retention_policy,
                schedule_interval_seconds=request.schedule_interval_seconds,
                is_enabled=request.is_enabled,
            )
        )
    except BackupApplicationError as error:
        return _failure(error)
@router.get("/projects/{project_id}/backups/runs", response_model=ResponseEnvelope)
def list_backup_runs(project_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    return _success(container.create_backup_service().list_runs(ProjectId(project_id)))


@router.get("/projects/{project_id}/backups/runs/{backup_run_id}", response_model=ResponseEnvelope)
def get_backup_run(
    project_id: str,
    backup_run_id: str,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(container.create_backup_service().get_run(ProjectId(project_id), backup_run_id))
    except BackupApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/backups/runs", response_model=ResponseEnvelope)
def run_backup(
    project_id: str,
    request: RunBackupRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        result = container.create_backup_service().execute_run_backup(
            ProjectId(project_id),
            plan_id=request.backup_plan_id,
            idempotency_key=request.idempotency_key,
        )
        return _success(result, warnings=result.get("warnings", []))
    except BackupApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/backups/restores/plan", response_model=ResponseEnvelope)
def plan_restore(
    project_id: str,
    request: RestoreBackupRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        preview = container.create_backup_service().preview_restore(ProjectId(project_id), request.backup_run_id)
        return _success(preview, warnings=preview.get("warnings", []))
    except BackupApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/backups/restores", response_model=ResponseEnvelope)
def execute_restore(
    project_id: str,
    request: RestoreBackupRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(
            container.create_backup_service().execute_restore(
                ProjectId(project_id),
                request.backup_run_id,
                confirm_destructive=request.confirm_destructive,
                idempotency_key=request.idempotency_key,
            )
        )
    except BackupApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/backups/restores/{restore_run_id}/undo", response_model=ResponseEnvelope)
def undo_restore(
    project_id: str,
    restore_run_id: str,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(container.create_backup_service().undo_restore(ProjectId(project_id), restore_run_id))
    except BackupApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/backups/retention/evaluate", response_model=ResponseEnvelope)
def evaluate_retention(
    project_id: str,
    request: EvaluateRetentionRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(
            container.create_backup_service().evaluate_retention(
                ProjectId(project_id),
                plan_id=request.backup_plan_id,
            )
        )
    except BackupApplicationError as error:
        return _failure(error)


def _success(data: dict | list[dict], *, warnings: list[str] | None = None) -> ResponseEnvelope:
    return ResponseEnvelope(ok=True, data=data, warnings=warnings or [])


def _failure(error: BackupApplicationError) -> ResponseEnvelope:
    return ResponseEnvelope(
        ok=False,
        error=ErrorPayload(code=error.code.value, message=str(error)),
    )
