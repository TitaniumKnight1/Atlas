from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.api.dependencies import get_container
from backend.api.schemas.dev_db import AuditReference, DevDatabaseUndoRequest, ErrorPayload, ResponseEnvelope
from backend.application.commands import CommandExecutionResult, CommandPreview, DryRunResult
from backend.application.dev_db import DevDatabaseApplicationError
from backend.domain.shared_kernel import ProjectId, StableIdentifier
from backend.infrastructure.di import ApplicationContainer


router = APIRouter(prefix="/api/v1", tags=["dev-db"])


@router.get("/projects/{project_id}/dev-db/status", response_model=ResponseEnvelope)
def get_dev_database_status(project_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _success(container.create_dev_database_service().get_dev_database_status(project_id=ProjectId(project_id)))
    except DevDatabaseApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/dev-db/provision-plan", response_model=ResponseEnvelope)
def provision_dev_database_plan(project_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        preview = container.create_dev_database_service().preview_provision_dev_database(project_id=ProjectId(project_id))
        return _success(_preview_data(preview), warnings=preview.warnings)
    except DevDatabaseApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/dev-db/provision-dry-run", response_model=ResponseEnvelope)
def provision_dev_database_dry_run(project_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        dry_run = container.create_dev_database_service().dry_run_provision_dev_database(project_id=ProjectId(project_id))
        return _success(_dry_run_data(dry_run), warnings=dry_run.warnings)
    except DevDatabaseApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/dev-db/provision/apply", response_model=ResponseEnvelope)
def provision_dev_database_apply(project_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _command_success(container.create_dev_database_service().execute_provision_dev_database(project_id=ProjectId(project_id)))
    except DevDatabaseApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/dev-db/start/apply", response_model=ResponseEnvelope)
def start_dev_database_apply(project_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _command_success(container.create_dev_database_service().execute_start_dev_database(project_id=ProjectId(project_id)))
    except DevDatabaseApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/dev-db/stop/apply", response_model=ResponseEnvelope)
def stop_dev_database_apply(project_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _command_success(container.create_dev_database_service().execute_stop_dev_database(project_id=ProjectId(project_id)))
    except DevDatabaseApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/dev-db/teardown-plan", response_model=ResponseEnvelope)
def teardown_dev_database_plan(project_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        preview = container.create_dev_database_service().preview_teardown_dev_database(project_id=ProjectId(project_id))
        return _success(_preview_data(preview), warnings=preview.warnings)
    except DevDatabaseApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/dev-db/teardown/apply", response_model=ResponseEnvelope)
def teardown_dev_database_apply(project_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _command_success(container.create_dev_database_service().execute_teardown_dev_database(project_id=ProjectId(project_id)))
    except DevDatabaseApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/dev-db/undo", response_model=ResponseEnvelope)
def undo_dev_database_command(
    project_id: str,
    request: DevDatabaseUndoRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _command_success(
            container.create_dev_database_service().undo_command_execution(StableIdentifier(request.command_execution_id))
        )
    except DevDatabaseApplicationError as error:
        return _failure(error)


def _success(data: dict | list, warnings: list[str] | None = None) -> ResponseEnvelope:
    return ResponseEnvelope(ok=True, data=data, warnings=warnings or [])


def _failure(error: DevDatabaseApplicationError) -> ResponseEnvelope:
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
