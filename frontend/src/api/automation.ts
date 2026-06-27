import { jsonRequest, requestBackend, type BackendResponse } from "./backend";

export interface GlobalAutomationSettings {
  global_enabled: boolean;
}

export interface AutomationRecipe {
  recipe_key: string;
  name: string;
  description: string;
  trigger_type: string;
  required_capabilities: string[];
  deferred_capabilities: string[];
  instantiation_status: string;
  actions: Array<{
    action_type: string;
    execution_tier: string;
    safety_class: string;
    capability_id: string | null;
    deferred: boolean;
  }>;
}

export interface AutomationWorkflow {
  automation_workflow_id: string;
  project_id: string;
  name: string;
  description: string | null;
  is_enabled: boolean;
  current_version_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface AutomationRunStep {
  automation_run_step_id: string;
  automation_action_id: string;
  position: number;
  status: string;
  result_json: Record<string, unknown> | null;
  has_undo: boolean;
}

export interface AutomationApproval {
  automation_approval_id: string;
  automation_run_id: string;
  automation_run_step_id: string;
  approval_state: string;
  preview_json: Record<string, unknown> | null;
  requested_at: string;
  decided_at: string | null;
  decided_by: string | null;
  approval_reason: string | null;
}

export interface AutomationRun {
  automation_run_id: string;
  automation_workflow_id: string;
  project_id: string;
  trigger_type: string;
  status: string;
  idempotency_key: string | null;
  started_at: string;
  finished_at: string | null;
  summary: string | null;
  steps: AutomationRunStep[];
  approvals: AutomationApproval[];
}

export interface RecipeInstance {
  automation_recipe_instance_id: string;
  recipe_key: string;
  automation_workflow_id: string;
  instance_status: string;
  deferred_capabilities: string[];
  params: Record<string, unknown>;
  created_at: string;
}

export async function getGlobalAutomationSettings(): Promise<GlobalAutomationSettings> {
  return (await requestBackend<GlobalAutomationSettings>("/api/v1/automation/settings")).data;
}

export async function setGlobalAutomationEnabled(globalEnabled: boolean): Promise<GlobalAutomationSettings> {
  return (await requestBackend<GlobalAutomationSettings>("/api/v1/automation/settings", jsonRequest({ global_enabled: globalEnabled }, { method: "PATCH" }))).data;
}

export async function listAutomationRecipes(): Promise<AutomationRecipe[]> {
  return (await requestBackend<AutomationRecipe[]>("/api/v1/automation/recipes")).data;
}

export async function listAutomationWorkflows(projectId: string): Promise<AutomationWorkflow[]> {
  return (await requestBackend<AutomationWorkflow[]>(`/api/v1/projects/${projectId}/automation/workflows`)).data;
}

export async function setWorkflowEnabled(projectId: string, workflowId: string, isEnabled: boolean): Promise<AutomationWorkflow> {
  return (
    await requestBackend<AutomationWorkflow>(
      `/api/v1/projects/${projectId}/automation/workflows/${workflowId}`,
      jsonRequest({ is_enabled: isEnabled }, { method: "PATCH" })
    )
  ).data;
}

export async function listAutomationRuns(projectId: string, limit = 50): Promise<AutomationRun[]> {
  return (await requestBackend<AutomationRun[]>(`/api/v1/projects/${projectId}/automation/runs?limit=${limit}`)).data;
}

export async function getAutomationRun(projectId: string, runId: string): Promise<AutomationRun> {
  return (await requestBackend<AutomationRun>(`/api/v1/projects/${projectId}/automation/runs/${runId}`)).data;
}

export async function runAutomationNow(projectId: string, workflowId: string, idempotencyKey?: string | null): Promise<Record<string, unknown>> {
  return (
    await requestBackend<Record<string, unknown>>(
      `/api/v1/projects/${projectId}/automation/workflows/${workflowId}/run`,
      jsonRequest({ idempotency_key: idempotencyKey ?? crypto.randomUUID() })
    )
  ).data;
}

export async function instantiateRecipe(
  projectId: string,
  recipeKey: string,
  params?: Record<string, unknown> | null,
  isEnabled = true
): Promise<Record<string, unknown>> {
  return (
    await requestBackend<Record<string, unknown>>(
      `/api/v1/projects/${projectId}/automation/recipes/${recipeKey}`,
      jsonRequest({ params: params ?? {}, is_enabled: isEnabled })
    )
  ).data;
}

export async function listRecipeInstances(projectId: string): Promise<RecipeInstance[]> {
  return (await requestBackend<RecipeInstance[]>(`/api/v1/projects/${projectId}/automation/recipe-instances`)).data;
}

export async function listPendingApprovals(projectId: string): Promise<AutomationApproval[]> {
  return (await requestBackend<AutomationApproval[]>(`/api/v1/projects/${projectId}/automation/approvals/pending`)).data;
}

export async function approveAutomationRun(
  projectId: string,
  runId: string,
  approvalId: string,
  decidedBy?: string | null
): Promise<Record<string, unknown>> {
  return (
    await requestBackend<Record<string, unknown>>(
      `/api/v1/projects/${projectId}/automation/runs/${runId}/approvals/${approvalId}/approve`,
      jsonRequest({ decided_by: decidedBy ?? "atlas-ui" })
    )
  ).data;
}

export async function rejectAutomationRun(
  projectId: string,
  runId: string,
  approvalId: string,
  reason?: string | null,
  decidedBy?: string | null
): Promise<Record<string, unknown>> {
  return (
    await requestBackend<Record<string, unknown>>(
      `/api/v1/projects/${projectId}/automation/runs/${runId}/approvals/${approvalId}/reject`,
      jsonRequest({ reason: reason ?? null, decided_by: decidedBy ?? "atlas-ui" })
    )
  ).data;
}

export async function undoAutomationRunStep(projectId: string, stepId: string): Promise<Record<string, unknown>> {
  return (await requestBackend<Record<string, unknown>>(`/api/v1/projects/${projectId}/automation/run-steps/${stepId}/undo`, jsonRequest({}))).data;
}

/** Sum pending approvals across projects for nav badge. */
export async function countPendingApprovals(projectIds: string[]): Promise<number> {
  let total = 0;
  for (const projectId of projectIds) {
    try {
      const pending = await listPendingApprovals(projectId);
      total += pending.length;
    } catch {
      // ignore per-project failures
    }
  }
  return total;
}
