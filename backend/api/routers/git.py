from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.api.dependencies import get_container
from backend.api.schemas.git import (
    AuditReference,
    CheckoutRefRequest,
    CloneRepositoryRequest,
    CreateBranchRequest,
    CreateCommitRequest,
    DeleteBranchRequest,
    DiscoverGitRequest,
    ErrorPayload,
    PullRepositoryRequest,
    ResponseEnvelope,
)
from backend.application.commands import CommandExecutionResult, CommandPreview
from backend.application.git import GitApplicationError
from backend.domain.shared_kernel import ProjectId
from backend.infrastructure.di import ApplicationContainer


router = APIRouter(prefix="/api/v1", tags=["git"])


@router.get("/projects/{project_id}/git/repositories", response_model=ResponseEnvelope)
def list_repositories(project_id: str, role: str | None = None, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    return _success(container.create_git_service().list_git_repositories(ProjectId(project_id), role))


@router.get("/projects/{project_id}/git/repositories/{repo_id}", response_model=ResponseEnvelope)
def get_repository(project_id: str, repo_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _success(container.create_git_service().get_git_repository(ProjectId(project_id), repo_id))
    except GitApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/git/discover", response_model=ResponseEnvelope)
def discover_repositories(project_id: str, request: DiscoverGitRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _success(container.create_git_service().execute_discover_git_repositories(project_id=ProjectId(project_id), path_filters=request.path_filters))
    except GitApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/git/clone-plan", response_model=ResponseEnvelope)
def plan_clone(project_id: str, request: CloneRepositoryRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    preview = container.create_git_service().preview_clone_repository(
        project_id=ProjectId(project_id),
        remote_url=request.remote_url,
        destination_path=request.destination_path,
        repository_role=request.repository_role,
    )
    return _success(_preview_data(preview), warnings=preview.warnings)


@router.post("/projects/{project_id}/git/clone", response_model=ResponseEnvelope)
def clone_repository(project_id: str, request: CloneRepositoryRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _command_success(
            container.create_git_service().execute_clone_repository(
                project_id=ProjectId(project_id),
                remote_url=request.remote_url,
                destination_path=request.destination_path,
                repository_role=request.repository_role,
            )
        )
    except GitApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/git/repositories/{repo_id}/fetch-plan", response_model=ResponseEnvelope)
def plan_fetch(project_id: str, repo_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        preview = container.create_git_service().preview_fetch_repository(project_id=ProjectId(project_id), git_repository_id=repo_id)
        return _success(_preview_data(preview), warnings=preview.warnings)
    except GitApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/git/repositories/{repo_id}/fetch", response_model=ResponseEnvelope)
def fetch_repository(project_id: str, repo_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _command_success(container.create_git_service().execute_fetch_repository(project_id=ProjectId(project_id), git_repository_id=repo_id))
    except GitApplicationError as error:
        return _failure(error)


@router.get("/projects/{project_id}/git/repositories/{repo_id}/status", response_model=ResponseEnvelope)
def get_status(project_id: str, repo_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _success(container.create_git_service().get_worktree_status(ProjectId(project_id), repo_id))
    except GitApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/git/repositories/{repo_id}/pull-plan", response_model=ResponseEnvelope)
def plan_pull(project_id: str, repo_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        preview = container.create_git_service().preview_pull_repository(project_id=ProjectId(project_id), git_repository_id=repo_id)
        return _success(_preview_data(preview), warnings=preview.warnings)
    except GitApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/git/repositories/{repo_id}/pull", response_model=ResponseEnvelope)
def pull_repository(project_id: str, repo_id: str, request: PullRepositoryRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _command_success(
            container.create_git_service().execute_pull_repository(
                project_id=ProjectId(project_id),
                git_repository_id=repo_id,
                idempotency_key=request.idempotency_key,
            )
        )
    except GitApplicationError as error:
        return _failure(error)


@router.get("/projects/{project_id}/git/repositories/{repo_id}/refs", response_model=ResponseEnvelope)
def list_refs(project_id: str, repo_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _success(container.create_git_service().list_refs(ProjectId(project_id), repo_id))
    except GitApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/git/repositories/{repo_id}/branches", response_model=ResponseEnvelope)
def create_branch(project_id: str, repo_id: str, request: CreateBranchRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _command_success(
            container.create_git_service().execute_create_branch(
                project_id=ProjectId(project_id),
                git_repository_id=repo_id,
                branch_name=request.branch_name,
                idempotency_key=request.idempotency_key,
            )
        )
    except GitApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/git/repositories/{repo_id}/checkout", response_model=ResponseEnvelope)
def checkout_ref(project_id: str, repo_id: str, request: CheckoutRefRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _command_success(
            container.create_git_service().execute_checkout_ref(
                project_id=ProjectId(project_id),
                git_repository_id=repo_id,
                ref_name=request.ref_name,
                idempotency_key=request.idempotency_key,
            )
        )
    except GitApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/git/repositories/{repo_id}/branches/delete-plan", response_model=ResponseEnvelope)
def plan_delete_branch(project_id: str, repo_id: str, request: DeleteBranchRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        preview = container.create_git_service().preview_delete_branch(
            project_id=ProjectId(project_id), git_repository_id=repo_id, branch_name=request.branch_name
        )
        return _success(_preview_data(preview), warnings=preview.warnings)
    except GitApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/git/repositories/{repo_id}/branches/delete", response_model=ResponseEnvelope)
def delete_branch(project_id: str, repo_id: str, request: DeleteBranchRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _command_success(
            container.create_git_service().execute_delete_branch(
                project_id=ProjectId(project_id),
                git_repository_id=repo_id,
                branch_name=request.branch_name,
                idempotency_key=request.idempotency_key,
            )
        )
    except GitApplicationError as error:
        return _failure(error)


@router.get("/projects/{project_id}/git/repositories/{repo_id}/diff", response_model=ResponseEnvelope)
def get_diff(
    project_id: str,
    repo_id: str,
    base_ref: str = Query(...),
    head_ref: str = Query(...),
    path_filter: str | None = None,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(container.create_git_service().get_diff_summary(ProjectId(project_id), repo_id, base_ref, head_ref, path_filter))
    except GitApplicationError as error:
        return _failure(error)


@router.get("/projects/{project_id}/git/repositories/{repo_id}/commits/compare", response_model=ResponseEnvelope)
def compare_commits(
    project_id: str,
    repo_id: str,
    base_ref: str = Query(...),
    head_ref: str = Query(...),
    limit: int = 20,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(container.create_git_service().compare_commits(ProjectId(project_id), repo_id, base_ref, head_ref, limit))
    except GitApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/git/repositories/{repo_id}/commits", response_model=ResponseEnvelope)
def create_commit(project_id: str, repo_id: str, request: CreateCommitRequest, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _command_success(
            container.create_git_service().execute_create_commit(
                project_id=ProjectId(project_id),
                git_repository_id=repo_id,
                message=request.message,
                paths=request.paths,
                idempotency_key=request.idempotency_key,
            )
        )
    except GitApplicationError as error:
        return _failure(error)


@router.get("/projects/{project_id}/git/operations", response_model=ResponseEnvelope)
def list_operations(project_id: str, repo_id: str | None = None, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    return _success(container.create_git_service().list_git_operations(ProjectId(project_id), repo_id))


def _success(data: dict | list[dict], warnings: list[str] | None = None) -> ResponseEnvelope:
    return ResponseEnvelope(ok=True, data=data, warnings=warnings or [])


def _failure(error: GitApplicationError) -> ResponseEnvelope:
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
