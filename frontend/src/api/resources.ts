import { jsonRequest, requestBackend, type BackendResponse } from "./backend";
import type { CommandPreviewData, CommandResultData, DryRunData } from "./project";

export interface ResourceSummary {
  resource_id: string;
  project_id: string;
  resource_name: string;
  relative_path: string;
  resource_type: string;
  enabled_state: string;
  startup_order: number | null;
  current_version_id: string | null;
  git_repository_id: string | null;
  updated_at: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  dependency_type: string;
}

export interface GraphFinding {
  finding_type: string;
  severity: string;
  message: string;
  nodes: string[];
  details: Record<string, unknown>;
}

export interface DependencyGraph {
  root: string | null;
  nodes: string[];
  edges: GraphEdge[];
  provides: Record<string, string[]>;
  findings: GraphFinding[];
  topological_order: string[] | null;
  is_healthy: boolean;
}

export interface ResourceSourceRequest {
  source_type: string;
  source_uri: string;
  resource_name?: string | null;
  enable?: boolean;
}

export interface UpdateResourceRequest {
  source_type: string;
  source_uri: string;
}

export interface RollbackResourcesRequest {
  resource_ids?: string[] | null;
  command_execution_ids?: string[] | null;
}

type ResourceEnvelope<T> = BackendResponse<T>;

function wrapPreview(data: Record<string, unknown>, summary: string, commandType: string, risk = "HIGH"): BackendResponse<CommandPreviewData> {
  return {
    data: {
      command_type: commandType,
      summary,
      risk_level: risk,
      preview: data
    },
    warnings: []
  };
}

function wrapDryRun(data: Record<string, unknown>, commandType: string, valid = true): BackendResponse<DryRunData> {
  return {
    data: {
      command_type: commandType,
      valid,
      simulation: data
    },
    warnings: []
  };
}

export async function listResources(projectId: string): Promise<ResourceSummary[]> {
  return (await requestBackend<ResourceSummary[]>(`/api/v1/projects/${projectId}/resources`)).data;
}

export async function getResource(projectId: string, resourceId: string): Promise<ResourceSummary> {
  return (await requestBackend<ResourceSummary>(`/api/v1/projects/${projectId}/resources/${resourceId}`)).data;
}

export async function getDependencyGraph(projectId: string, root?: string | null): Promise<DependencyGraph> {
  const query = root ? `?root=${encodeURIComponent(root)}` : "";
  return (await requestBackend<DependencyGraph>(`/api/v1/projects/${projectId}/resources/graph${query}`)).data;
}

export async function getGraphHealth(projectId: string): Promise<{ is_healthy: boolean; findings: GraphFinding[]; topological_order: string[] | null }> {
  return (await requestBackend<{ is_healthy: boolean; findings: GraphFinding[]; topological_order: string[] | null }>(`/api/v1/projects/${projectId}/resources/graph/health`)).data;
}

export async function getSafeStartOrder(projectId: string): Promise<{ ok: boolean; order: string[] | null; findings: GraphFinding[] }> {
  return (await requestBackend<{ ok: boolean; order: string[] | null; findings: GraphFinding[] }>(`/api/v1/projects/${projectId}/resources/graph/order`)).data;
}

export async function previewInstallResource(projectId: string, request: ResourceSourceRequest): Promise<ResourceEnvelope<CommandPreviewData>> {
  const response = await requestBackend<Record<string, unknown>>(`/api/v1/projects/${projectId}/resources/install-plan`, jsonRequest(request));
  return {
    ...wrapPreview(response.data, `Install resource from ${request.source_type}`, "PlanInstallResource"),
    warnings: response.warnings,
    auditRef: response.auditRef
  };
}

export async function dryRunInstallResource(projectId: string, request: ResourceSourceRequest): Promise<ResourceEnvelope<DryRunData>> {
  const response = await requestBackend<Record<string, unknown>>(`/api/v1/projects/${projectId}/resources/install-dry-run`, jsonRequest(request));
  return {
    ...wrapDryRun(response.data, "PlanInstallResource"),
    warnings: response.warnings,
    auditRef: response.auditRef
  };
}

export async function installResource(projectId: string, request: ResourceSourceRequest): Promise<ResourceEnvelope<CommandResultData>> {
  return requestBackend<CommandResultData>(`/api/v1/projects/${projectId}/resources/install`, jsonRequest(request));
}

export async function previewUpdateResource(projectId: string, resourceId: string, request: UpdateResourceRequest): Promise<ResourceEnvelope<CommandPreviewData>> {
  const response = await requestBackend<Record<string, unknown>>(
    `/api/v1/projects/${projectId}/resources/${resourceId}/update-plan`,
    jsonRequest(request)
  );
  return {
    ...wrapPreview(response.data, `Update resource ${resourceId}`, "PlanUpdateResource"),
    warnings: response.warnings,
    auditRef: response.auditRef
  };
}

export async function dryRunUpdateResource(projectId: string, resourceId: string, request: UpdateResourceRequest): Promise<ResourceEnvelope<DryRunData>> {
  const response = await requestBackend<Record<string, unknown>>(
    `/api/v1/projects/${projectId}/resources/${resourceId}/update-dry-run`,
    jsonRequest(request)
  );
  return {
    ...wrapDryRun(response.data, "PlanUpdateResource"),
    warnings: response.warnings,
    auditRef: response.auditRef
  };
}

export async function updateResource(projectId: string, resourceId: string, request: UpdateResourceRequest): Promise<ResourceEnvelope<CommandResultData>> {
  return requestBackend<CommandResultData>(`/api/v1/projects/${projectId}/resources/${resourceId}/update`, jsonRequest(request));
}

export async function previewSetEnabledState(projectId: string, resourceId: string, enabled: boolean): Promise<ResourceEnvelope<CommandPreviewData>> {
  const response = await requestBackend<Record<string, unknown>>(
    `/api/v1/projects/${projectId}/resources/${resourceId}/enabled-state-plan`,
    jsonRequest({ enabled })
  );
  return {
    ...wrapPreview(response.data, enabled ? "Enable resource" : "Disable resource", "PlanSetEnabledState"),
    warnings: response.warnings,
    auditRef: response.auditRef
  };
}

export async function dryRunSetEnabledState(projectId: string, resourceId: string, enabled: boolean): Promise<ResourceEnvelope<DryRunData>> {
  const preview = await previewSetEnabledState(projectId, resourceId, enabled);
  return {
    data: {
      command_type: preview.data.command_type,
      valid: !preview.warnings.some((warning) => warning.toLowerCase().includes("blocked")),
      simulation: preview.data.preview
    },
    warnings: preview.warnings,
    auditRef: preview.auditRef
  };
}

export async function setEnabledState(projectId: string, resourceId: string, enabled: boolean): Promise<ResourceEnvelope<CommandResultData>> {
  return requestBackend<CommandResultData>(`/api/v1/projects/${projectId}/resources/${resourceId}/enabled-state`, jsonRequest({ enabled }));
}

export async function previewDeleteResource(projectId: string, resourceId: string): Promise<ResourceEnvelope<CommandPreviewData>> {
  const response = await requestBackend<Record<string, unknown>>(`/api/v1/projects/${projectId}/resources/${resourceId}/delete-plan`, jsonRequest({}));
  return {
    ...wrapPreview(response.data, "Delete resource", "PlanDeleteResource", "DESTRUCTIVE"),
    warnings: response.warnings,
    auditRef: response.auditRef
  };
}

export async function dryRunDeleteResource(projectId: string, resourceId: string): Promise<ResourceEnvelope<DryRunData>> {
  const preview = await previewDeleteResource(projectId, resourceId);
  return {
    data: {
      command_type: preview.data.command_type,
      valid: !preview.warnings.some((warning) => warning.toLowerCase().includes("blocked")),
      simulation: preview.data.preview
    },
    warnings: preview.warnings,
    auditRef: preview.auditRef
  };
}

export async function deleteResource(projectId: string, resourceId: string): Promise<ResourceEnvelope<CommandResultData>> {
  return requestBackend<CommandResultData>(`/api/v1/projects/${projectId}/resources/${resourceId}/delete`, jsonRequest({}));
}

export async function previewRollbackBatch(projectId: string, request: RollbackResourcesRequest): Promise<ResourceEnvelope<CommandPreviewData>> {
  const response = await requestBackend<Record<string, unknown>>(`/api/v1/projects/${projectId}/resources/rollback-plan`, jsonRequest(request));
  return {
    ...wrapPreview(response.data, "Rollback resource batch", "RollbackResourceBatch", "DESTRUCTIVE"),
    warnings: response.warnings,
    auditRef: response.auditRef
  };
}

export async function dryRunRollbackBatch(projectId: string, request: RollbackResourcesRequest): Promise<ResourceEnvelope<DryRunData>> {
  const response = await requestBackend<Record<string, unknown>>(`/api/v1/projects/${projectId}/resources/rollback-dry-run`, jsonRequest(request));
  return {
    ...wrapDryRun(response.data, "RollbackResourceBatch"),
    warnings: response.warnings,
    auditRef: response.auditRef
  };
}

export async function rollbackResources(projectId: string, request: RollbackResourcesRequest): Promise<ResourceEnvelope<CommandResultData>> {
  return requestBackend<CommandResultData>(`/api/v1/projects/${projectId}/resources/rollback`, jsonRequest(request));
}

export async function getRollbackRun(projectId: string, rollbackRunId: string): Promise<Record<string, unknown>> {
  return (await requestBackend<Record<string, unknown>>(`/api/v1/projects/${projectId}/resources/rollback-runs/${rollbackRunId}`)).data;
}
