from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.api.dependencies import get_container
from backend.api.schemas.automation import (
    ApprovalDecisionRequest,
    CreateAutomationWorkflowRequest,
    ErrorPayload,
    InstantiateRecipeRequest,
    ResponseEnvelope,
    RunAutomationRequest,
    SetAutomationEnabledRequest,
    SetGlobalAutomationRequest,
)
from backend.application.automation import AutomationApplicationError
from backend.domain.shared_kernel import ProjectId
from backend.infrastructure.di import ApplicationContainer


router = APIRouter(prefix="/api/v1", tags=["automation"])


@router.get("/automation/settings", response_model=ResponseEnvelope)
def get_global_automation_settings(container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    return _success(container.create_automation_service().get_global_settings())


@router.patch("/automation/settings", response_model=ResponseEnvelope)
def set_global_automation_settings(
    request: SetGlobalAutomationRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    return _success(container.create_automation_service().set_global_enabled(enabled=request.global_enabled))


@router.get("/projects/{project_id}/automation/workflows", response_model=ResponseEnvelope)
def list_automation_workflows(project_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _success(container.create_automation_service().list_workflows(ProjectId(project_id)))
    except AutomationApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/automation/workflows", response_model=ResponseEnvelope)
def create_automation_workflow(
    project_id: str,
    request: CreateAutomationWorkflowRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(
            container.create_automation_service().create_workflow(
                ProjectId(project_id),
                name=request.name,
                description=request.description,
                trigger_type=request.trigger_type,
                trigger_config=request.trigger_config,
                conditions=[item.model_dump() for item in request.conditions] if request.conditions else None,
                actions=[item.model_dump() for item in request.actions],
                schedule_interval_seconds=request.schedule_interval_seconds,
                is_enabled=request.is_enabled,
            )
        )
    except AutomationApplicationError as error:
        return _failure(error)


@router.patch("/projects/{project_id}/automation/workflows/{workflow_id}", response_model=ResponseEnvelope)
def set_automation_workflow_enabled(
    project_id: str,
    workflow_id: str,
    request: SetAutomationEnabledRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(
            container.create_automation_service().set_workflow_enabled(
                ProjectId(project_id), workflow_id, is_enabled=request.is_enabled
            )
        )
    except AutomationApplicationError as error:
        return _failure(error)


@router.get("/projects/{project_id}/automation/runs", response_model=ResponseEnvelope)
def list_automation_runs(
    project_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(container.create_automation_service().list_runs(ProjectId(project_id), limit=limit))
    except AutomationApplicationError as error:
        return _failure(error)


@router.get("/projects/{project_id}/automation/runs/{run_id}", response_model=ResponseEnvelope)
def get_automation_run(
    project_id: str,
    run_id: str,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(container.create_automation_service().get_run(ProjectId(project_id), run_id))
    except AutomationApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/automation/workflows/{workflow_id}/run", response_model=ResponseEnvelope)
def run_automation_now(
    project_id: str,
    workflow_id: str,
    request: RunAutomationRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(
            container.create_automation_service().run_now(
                ProjectId(project_id), workflow_id, idempotency_key=request.idempotency_key
            )
        )
    except AutomationApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/automation/run-steps/{step_id}/undo", response_model=ResponseEnvelope)
def undo_automation_run_step(
    project_id: str,
    step_id: str,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(container.create_automation_service().undo_run_step(ProjectId(project_id), step_id))
    except AutomationApplicationError as error:
        return _failure(error)


@router.get("/automation/recipes", response_model=ResponseEnvelope)
def list_automation_recipes(container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    return _success(container.create_automation_service().list_recipes())


@router.post("/projects/{project_id}/automation/recipes/{recipe_key}", response_model=ResponseEnvelope)
def instantiate_automation_recipe(
    project_id: str,
    recipe_key: str,
    request: InstantiateRecipeRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(
            container.create_automation_service().instantiate_recipe(
                ProjectId(project_id),
                recipe_key,
                params=request.params,
                is_enabled=request.is_enabled,
            )
        )
    except AutomationApplicationError as error:
        return _failure(error)


@router.get("/projects/{project_id}/automation/recipe-instances", response_model=ResponseEnvelope)
def list_recipe_instances(project_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _success(container.create_automation_service().list_recipe_instances(ProjectId(project_id)))
    except AutomationApplicationError as error:
        return _failure(error)


@router.get("/projects/{project_id}/automation/approvals/pending", response_model=ResponseEnvelope)
def list_pending_approvals(project_id: str, container: ApplicationContainer = Depends(get_container)) -> ResponseEnvelope:
    try:
        return _success(container.create_automation_service().list_pending_approvals(ProjectId(project_id)))
    except AutomationApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/automation/runs/{run_id}/approvals/{approval_id}/approve", response_model=ResponseEnvelope)
def approve_automation_run(
    project_id: str,
    run_id: str,
    approval_id: str,
    request: ApprovalDecisionRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(
            container.create_automation_service().approve_run(
                ProjectId(project_id), run_id, approval_id, decided_by=request.decided_by
            )
        )
    except AutomationApplicationError as error:
        return _failure(error)


@router.post("/projects/{project_id}/automation/runs/{run_id}/approvals/{approval_id}/reject", response_model=ResponseEnvelope)
def reject_automation_run(
    project_id: str,
    run_id: str,
    approval_id: str,
    request: ApprovalDecisionRequest,
    container: ApplicationContainer = Depends(get_container),
) -> ResponseEnvelope:
    try:
        return _success(
            container.create_automation_service().reject_run(
                ProjectId(project_id), run_id, approval_id, reason=request.reason, decided_by=request.decided_by
            )
        )
    except AutomationApplicationError as error:
        return _failure(error)


def _success(data: dict | list[dict]) -> ResponseEnvelope:
    return ResponseEnvelope(ok=True, data=data)


def _failure(error: AutomationApplicationError) -> ResponseEnvelope:
    return ResponseEnvelope(ok=False, error=ErrorPayload(code=error.code.value, message=str(error)))
