from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.api.dependencies import get_container
from backend.api.schemas.config import (
    ApplyConfigChangeRequest,
    AuditReference,
    ConfigChangePlanRequest,
    ConfigRemediationRequest,
    ErrorPayload,
    RescanConfigRequest,
    ResponseEnvelope,
    SecretScanRequest,
    ValidationRunRequest,
)
from backend.application.commands import CommandExecutionResult, CommandPreview, DryRunResult
from backend.application.config import ConfigApplicationError
from backend.application.config.remediation_service import ConfigRemediationError
from backend.domain.shared_kernel import ProjectId
from backend.infrastructure.di import ApplicationContainer


router = APIRouter(prefix="/api/v1", tags=["config"])


@router.get("/projects/{project_id}/config-files", response_model=ResponseEnvelope)
def list_config_files(project_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    return _success(container.create_config_service().list_config_files(ProjectId(project_id)))


@router.get("/projects/{project_id}/config-files/{config_file_id}", response_model=ResponseEnvelope)
def get_config_file(project_id: str, config_file_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _success(container.create_config_service().get_config_file_view(ProjectId(project_id), config_file_id))
    except ConfigApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/config-files/rescan", response_model=ResponseEnvelope)
def rescan_config_files(project_id: str, request: RescanConfigRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _success(container.create_config_service().execute_rescan_config_files(project_id=ProjectId(project_id), scan_roots=request.scan_roots))
    except ConfigApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/config/change-plan", response_model=ResponseEnvelope)
def plan_config_change(project_id: str, request: ConfigChangePlanRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        preview = container.create_config_service().preview_plan_config_change(
            project_id=ProjectId(project_id), config_file_id=request.config_file_id, proposed_content=request.proposed_content
        )
        return _success(_preview_data(preview), warnings=preview.warnings)
    except ConfigApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/config/change-dry-run", response_model=ResponseEnvelope)
def dry_run_config_change(project_id: str, request: ConfigChangePlanRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        dry_run = container.create_config_service().dry_run_plan_config_change(
            project_id=ProjectId(project_id), config_file_id=request.config_file_id, proposed_content=request.proposed_content
        )
        return _success(_dry_run_data(dry_run), warnings=dry_run.warnings)
    except ConfigApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/config/change-sets/apply", response_model=ResponseEnvelope)
def apply_config_change(project_id: str, request: ApplyConfigChangeRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _command_success(
            container.create_config_service().execute_apply_config_change(
                project_id=ProjectId(project_id),
                config_file_id=request.config_file_id,
                proposed_content=request.proposed_content,
                idempotency_key=request.idempotency_key,
            )
        )
    except ConfigApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/config/validation-runs", response_model=ResponseEnvelope)
def run_validation(project_id: str, request: ValidationRunRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _success(container.create_config_service().execute_run_validation(project_id=ProjectId(project_id), config_file_id=request.config_file_id))
    except ConfigApplicationError as error:
        return _failure(error)


@router.get("/projects/{project_id}/config/findings", response_model=ResponseEnvelope)
def list_validation_findings(project_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    return _success(container.create_config_service().list_validation_findings(ProjectId(project_id)))


@router.post("/projects/{project_id}/config/secret-scan", response_model=ResponseEnvelope)
def run_secret_scan(project_id: str, request: SecretScanRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _success(container.create_config_service().execute_run_secret_scan(project_id=ProjectId(project_id), config_file_id=request.config_file_id))
    except ConfigApplicationError as error:
        return _failure(error)


@router.get("/projects/{project_id}/config/secret-findings", response_model=ResponseEnvelope)
def list_secret_findings(project_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    return _success(container.create_config_service().list_secret_findings(ProjectId(project_id)))


@router.get("/projects/{project_id}/config-files/{config_file_id}/snapshots", response_model=ResponseEnvelope)
def list_snapshots(project_id: str, config_file_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _success(container.create_config_service().list_snapshots(ProjectId(project_id), config_file_id))
    except ConfigApplicationError as error:
        return _failure(error)


@router.get("/projects/{project_id}/config-files/{config_file_id}/diff", response_model=ResponseEnvelope)
def get_diff(project_id: str, config_file_id: str, snapshot_id: str | None = None, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _success(container.create_config_service().get_config_diff(ProjectId(project_id), config_file_id, snapshot_id))
    except ConfigApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/config-remediation/comment-dangling/preview", response_model=ResponseEnvelope)
def preview_comment_dangling(project_id: str, request: ConfigRemediationRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        preview = container.create_config_remediation_service().preview_comment_out_dangling_ensure(
            project_id=ProjectId(project_id), finding_id=request.finding_id
        )
        return _success(_preview_data(preview), warnings=preview.warnings)
    except ConfigRemediationError as error:
        return _remediation_failure(error)


@router.post("/projects/{project_id}/config-remediation/comment-dangling/dry-run", response_model=ResponseEnvelope)
def dry_run_comment_dangling(project_id: str, request: ConfigRemediationRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        dry_run = container.create_config_remediation_service().dry_run_comment_out_dangling_ensure(
            project_id=ProjectId(project_id), finding_id=request.finding_id
        )
        return _success(_dry_run_data(dry_run), warnings=dry_run.warnings)
    except ConfigRemediationError as error:
        return _remediation_failure(error)


@router.post("/projects/{project_id}/config-remediation/comment-dangling/apply", response_model=ResponseEnvelope)
def apply_comment_dangling(project_id: str, request: ConfigRemediationRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _command_success(
            container.create_config_remediation_service().execute_comment_out_dangling_ensure(
                project_id=ProjectId(project_id), finding_id=request.finding_id
            )
        )
    except ConfigRemediationError as error:
        return _remediation_failure(error)


@router.post("/projects/{project_id}/config-remediation/rewrite-absolute-path/preview", response_model=ResponseEnvelope)
def preview_rewrite_absolute_path(project_id: str, request: ConfigRemediationRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        preview = container.create_config_remediation_service().preview_rewrite_absolute_path(
            project_id=ProjectId(project_id), finding_id=request.finding_id
        )
        return _success(_preview_data(preview), warnings=preview.warnings)
    except ConfigRemediationError as error:
        return _remediation_failure(error)


@router.post("/projects/{project_id}/config-remediation/rewrite-absolute-path/dry-run", response_model=ResponseEnvelope)
def dry_run_rewrite_absolute_path(project_id: str, request: ConfigRemediationRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        dry_run = container.create_config_remediation_service().dry_run_rewrite_absolute_path(
            project_id=ProjectId(project_id), finding_id=request.finding_id
        )
        return _success(_dry_run_data(dry_run), warnings=dry_run.warnings)
    except ConfigRemediationError as error:
        return _remediation_failure(error)


@router.post("/projects/{project_id}/config-remediation/rewrite-absolute-path/apply", response_model=ResponseEnvelope)
def apply_rewrite_absolute_path(project_id: str, request: ConfigRemediationRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _command_success(
            container.create_config_remediation_service().execute_rewrite_absolute_path(
                project_id=ProjectId(project_id), finding_id=request.finding_id
            )
        )
    except ConfigRemediationError as error:
        return _remediation_failure(error)


def _success(data: dict | list[dict], warnings: list[str] | None = None) -> ResponseEnvelope:
    return ResponseEnvelope(ok=True, data=data, warnings=warnings or [])


def _failure(error: ConfigApplicationError) -> ResponseEnvelope:
    return ResponseEnvelope(ok=False, error=ErrorPayload(code=error.code.value, message=str(error)))


def _remediation_failure(error: ConfigRemediationError) -> ResponseEnvelope:
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
    return {"command_type": preview.command_type, "summary": preview.summary, "risk_level": preview.risk_level.value, "preview": preview.preview}


def _dry_run_data(dry_run: DryRunResult) -> dict:
    return {"command_type": dry_run.command_type, "valid": dry_run.valid, "simulation": dry_run.simulation}
