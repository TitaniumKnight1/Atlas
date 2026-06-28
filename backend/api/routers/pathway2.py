from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends

from backend.api.dependencies import get_container
from backend.api.schemas.pathway2 import (
    AdoptRepositoryPlanRequest,
    AdoptRepositoryRequest,
    ApplyRepoNormalizationRequest,
    AuditReference,
    ErrorPayload,
    Pathway2UndoRequest,
    ResponseEnvelope,
)
from backend.application.commands import CommandExecutionResult, CommandPreview, DryRunResult
from backend.application.pathway2 import Pathway2ApplicationError
from backend.domain.shared_kernel import ProjectId, StableIdentifier
from backend.infrastructure.di import ApplicationContainer


router = APIRouter(prefix="/api/v1", tags=["pathway2"])


@router.post("/pathway2/adopt-plan", response_model=ResponseEnvelope)
def adopt_repository_plan(
    request: AdoptRepositoryPlanRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        preview = container.create_adopt_service().preview_adopt_repository(
            root_path=Path(request.root_path),
            remote_url=request.remote_url,
        )
        return _success(_preview_data(preview), warnings=preview.warnings)
    except Pathway2ApplicationError as error:
        return _failure(error)


@router.post("/pathway2/adopt-dry-run", response_model=ResponseEnvelope)
def adopt_repository_dry_run(
    request: AdoptRepositoryPlanRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        dry_run = container.create_adopt_service().dry_run_adopt_repository(
            root_path=Path(request.root_path),
            remote_url=request.remote_url,
        )
        return _success(_dry_run_data(dry_run), warnings=dry_run.warnings)
    except Pathway2ApplicationError as error:
        return _failure(error)


@router.post("/pathway2/adopt", response_model=ResponseEnvelope)
def adopt_repository(
    request: AdoptRepositoryRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        result = container.create_adopt_service().execute_adopt_repository(
            root_path=Path(request.root_path),
            remote_url=request.remote_url,
            idempotency_key=request.idempotency_key,
        )
        return _command_success(result)
    except Pathway2ApplicationError as error:
        return _failure(error)


@router.get("/projects/{project_id}/pathway2/status", response_model=ResponseEnvelope)
def get_pathway2_status(project_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _success(container.create_adopt_service().get_adopt_status(ProjectId(project_id)))
    except Pathway2ApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/pathway2/normalization-plan", response_model=ResponseEnvelope)
def plan_repo_normalization(project_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        preview = container.create_adopt_service().preview_repo_normalization(project_id=ProjectId(project_id))
        return _success(_preview_data(preview), warnings=preview.warnings)
    except Pathway2ApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/pathway2/normalization-dry-run", response_model=ResponseEnvelope)
def dry_run_repo_normalization(project_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        dry_run = container.create_adopt_service().dry_run_repo_normalization(project_id=ProjectId(project_id))
        return _success(_dry_run_data(dry_run), warnings=dry_run.warnings)
    except Pathway2ApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/pathway2/normalization/apply", response_model=ResponseEnvelope)
def apply_repo_normalization(
    project_id: str,
    request: ApplyRepoNormalizationRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _command_success(
            container.create_adopt_service().execute_apply_repo_normalization(
                project_id=ProjectId(project_id),
                idempotency_key=request.idempotency_key,
            )
        )
    except Pathway2ApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/pathway2/undo", response_model=ResponseEnvelope)
def undo_pathway2_command(
    project_id: str,
    request: Pathway2UndoRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _command_success(
            container.create_adopt_service().undo_command_execution(StableIdentifier(request.command_execution_id))
        )
    except Pathway2ApplicationError as error:
        return _failure(error)


def _success(data: dict | list, warnings: list[str] | None = None) -> ResponseEnvelope:
    return ResponseEnvelope(ok=True, data=data, warnings=warnings or [])


def _failure(error: Pathway2ApplicationError) -> ResponseEnvelope:
    return ResponseEnvelope(ok=False, error=ErrorPayload(code=error.code.value, message=str(error)))


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
    return {
        "command_type": preview.command_type,
        "summary": preview.summary,
        "risk_level": preview.risk_level.value,
        "preview": preview.preview,
    }


def _dry_run_data(dry_run: DryRunResult) -> dict:
    return {"command_type": dry_run.command_type, "valid": dry_run.valid, "simulation": dry_run.simulation}
