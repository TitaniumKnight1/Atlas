from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Query

from backend.api.dependencies import get_container
from backend.api.schemas.project import (
    AuditReference,
    ArchiveProjectRequest,
    CreateEnvironmentProfileRequest,
    ErrorPayload,
    ImportProjectPlanRequest,
    ImportProjectRequest,
    RecordTrustDecisionRequest,
    ResponseEnvelope,
    UndoCommandRequest,
    UpdateEnvironmentProfileRequest,
    UpdateProjectSettingsRequest,
)
from backend.application.commands import CommandExecutionResult, CommandPreview, DryRunResult
from backend.application.project import ProjectApplicationError
from backend.domain.shared_kernel import ProjectId, StableIdentifier
from backend.infrastructure.di import ApplicationContainer


router = APIRouter(prefix="/api/v1", tags=["projects"])


@router.get("/projects", response_model=ResponseEnvelope)
def list_projects(container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    return _success(container.create_project_service().list_projects())


@router.get("/project-templates", response_model=ResponseEnvelope)
def list_project_templates(container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    return _success(container.create_project_service().list_project_templates())


@router.post("/projects/import-plan", response_model=ResponseEnvelope)
def import_project_plan(
    request: ImportProjectPlanRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        preview = container.create_project_service().preview_import_project(Path(request.root_path), request.template_id)
        return _success(_preview_data(preview), warnings=preview.warnings)
    except ProjectApplicationError as error:
        return _failure(error)


@router.post("/projects/import-dry-run", response_model=ResponseEnvelope)
def import_project_dry_run(
    request: ImportProjectPlanRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        dry_run = container.create_project_service().dry_run_import_project(Path(request.root_path), request.template_id)
        return _success(_dry_run_data(dry_run), warnings=dry_run.warnings)
    except ProjectApplicationError as error:
        return _failure(error)


@router.post("/projects/import", response_model=ResponseEnvelope)
def import_project(
    request: ImportProjectRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        result = container.create_project_service().execute_import_project(
            root_path=Path(request.root_path),
            template_id=request.template_id,
            idempotency_key=request.idempotency_key,
        )
        return _command_success(result)
    except ProjectApplicationError as error:
        return _failure(error)


@router.post("/projects/undo", response_model=ResponseEnvelope)
def undo_command_execution(
    request: UndoCommandRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        result = container.create_project_service().undo_command_execution(StableIdentifier(request.command_execution_id))
        return _command_success(result)
    except ProjectApplicationError as error:
        return _failure(error)


@router.get("/projects/{project_id}", response_model=ResponseEnvelope)
def get_project(project_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _success(container.create_project_service().get_project(ProjectId(project_id)))
    except ProjectApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/open", response_model=ResponseEnvelope)
def open_project(project_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _command_success(container.create_project_service().open_project(ProjectId(project_id)))
    except ProjectApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/archive", response_model=ResponseEnvelope)
def archive_project(
    project_id: str,
    request: ArchiveProjectRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _command_success(container.create_project_service().archive_project(ProjectId(project_id), request.reason))
    except ProjectApplicationError as error:
        return _failure(error)


@router.patch("/projects/{project_id}/settings", response_model=ResponseEnvelope)
def update_project_settings(
    project_id: str,
    request: UpdateProjectSettingsRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _command_success(
            container.create_project_service().update_project_settings(
                project_id=ProjectId(project_id),
                patch=request.settings_patch,
                expected_version=request.expected_version,
            )
        )
    except ProjectApplicationError as error:
        return _failure(error)


@router.get("/projects/{project_id}/settings", response_model=ResponseEnvelope)
def get_project_settings(project_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        data = container.create_project_service().get_project_settings(ProjectId(project_id))
        return _success({"project_id": project_id, "settings": data})
    except ProjectApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/environments", response_model=ResponseEnvelope)
def create_environment_profile(
    project_id: str,
    request: CreateEnvironmentProfileRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _command_success(
            container.create_project_service().create_environment_profile(
                project_id=ProjectId(project_id),
                name=request.name,
                display_name=request.display_name,
                artifact_channel=request.artifact_channel,
                settings=request.settings,
                is_default=request.is_default,
            )
        )
    except ProjectApplicationError as error:
        return _failure(error)


@router.get("/projects/{project_id}/environments", response_model=ResponseEnvelope)
def list_environment_profiles(project_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _success(container.create_project_service().list_environment_profiles(ProjectId(project_id)))
    except ProjectApplicationError as error:
        return _failure(error)


@router.patch("/projects/{project_id}/environments/{environment_id}", response_model=ResponseEnvelope)
def update_environment_profile(
    project_id: str,
    environment_id: str,
    request: UpdateEnvironmentProfileRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _command_success(
            container.create_project_service().update_environment_profile(
                project_id=ProjectId(project_id),
                environment_id=StableIdentifier(environment_id),
                display_name=request.display_name,
                artifact_channel=request.artifact_channel,
                settings=request.settings,
            )
        )
    except ProjectApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/trust-decisions", response_model=ResponseEnvelope)
def record_trust_decision(
    project_id: str,
    request: RecordTrustDecisionRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _command_success(
            container.create_project_service().record_workspace_trust_decision(
                project_id=ProjectId(project_id),
                scope=request.scope,
                scope_ref=request.scope_ref,
                trust_state=request.trust_state,
                reason=request.reason,
                decided_by=request.decided_by,
            )
        )
    except ProjectApplicationError as error:
        return _failure(error)


@router.get("/projects/{project_id}/trust-decisions", response_model=ResponseEnvelope)
def list_trust_decisions(project_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _success(container.create_project_service().list_trust_decisions(ProjectId(project_id)))
    except ProjectApplicationError as error:
        return _failure(error)


@router.get("/projects/{project_id}/topology", response_model=ResponseEnvelope)
def get_project_topology(
    project_id: str,
    path: str | None = Query(default=None, description="Optional file path to resolve owning repo"),
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        service = container.create_project_topology_service()
        if path:
            return _success(service.resolve_path_owner(ProjectId(project_id), Path(path)))
        return _success(service.get_topology(ProjectId(project_id)))
    except ProjectApplicationError as error:
        return _failure(error)


def _success(data: dict | list[dict], warnings: list[str] | None = None) -> ResponseEnvelope:
    return ResponseEnvelope(ok=True, data=data, warnings=warnings or [])


def _failure(error: ProjectApplicationError) -> ResponseEnvelope:
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
    return {
        "command_type": dry_run.command_type,
        "valid": dry_run.valid,
        "simulation": dry_run.simulation,
    }
