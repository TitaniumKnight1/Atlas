import { jsonRequest, requestBackend, type AuditRef, type BackendResponse } from "./backend";

export interface ProjectSummary {
  project_id: string;
  slug: string;
  display_name: string;
  description: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  last_opened_at: string | null;
}

export interface ProjectPathRef {
  project_path_id: string;
  project_id: string;
  path_role: string;
  absolute_path: string;
  exists_last_checked: boolean;
  last_checked_at: string | null;
}

export interface ProjectDetail extends ProjectSummary {
  paths: ProjectPathRef[];
  default_environment_id: string | null;
}

export interface EnvironmentProfile {
  environment_id: string;
  project_id: string;
  name: string;
  display_name: string;
  artifact_channel: string | null;
  settings: Record<string, unknown>;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface CommandPreviewData {
  command_type: string;
  summary: string;
  risk_level: string;
  preview: Record<string, unknown>;
}

export interface DryRunData {
  command_type: string;
  valid: boolean;
  simulation: Record<string, unknown>;
}

export interface CommandResultData {
  command_plan_id: string;
  command_execution_id: string;
  undo_plan?: Record<string, unknown> | null;
  [key: string]: unknown;
}

export type CommandResponse = BackendResponse<CommandResultData>;

export interface SettingsData {
  project_id: string;
  settings: Record<string, unknown>;
}

export interface ImportProjectRequest {
  root_path: string;
  template_id?: string | null;
  idempotency_key?: string | null;
}

export interface UpdateSettingsRequest {
  settings_patch: Record<string, unknown>;
  expected_version?: string | null;
}

export interface CreateEnvironmentRequest {
  name: string;
  display_name?: string | null;
  artifact_channel?: string | null;
  settings?: Record<string, unknown>;
  is_default?: boolean;
}

export interface UpdateEnvironmentRequest {
  display_name?: string | null;
  artifact_channel?: string | null;
  settings?: Record<string, unknown> | null;
}

export async function listProjects(): Promise<ProjectSummary[]> {
  return (await requestBackend<ProjectSummary[]>("/api/v1/projects")).data;
}

export async function getProject(projectId: string): Promise<ProjectDetail> {
  return (await requestBackend<ProjectDetail>(`/api/v1/projects/${projectId}`)).data;
}

export async function openProject(projectId: string): Promise<CommandResponse> {
  return requestBackend<CommandResultData>(`/api/v1/projects/${projectId}/open`, jsonRequest({}));
}

export async function previewImportProject(rootPath: string): Promise<BackendResponse<CommandPreviewData>> {
  return requestBackend<CommandPreviewData>("/api/v1/projects/import-plan", jsonRequest({ root_path: rootPath }));
}

export async function dryRunImportProject(rootPath: string): Promise<BackendResponse<DryRunData>> {
  return requestBackend<DryRunData>("/api/v1/projects/import-dry-run", jsonRequest({ root_path: rootPath }));
}

export async function importProject(request: ImportProjectRequest): Promise<CommandResponse> {
  return requestBackend<CommandResultData>(
    "/api/v1/projects/import",
    jsonRequest({
      root_path: request.root_path,
      template_id: request.template_id ?? null,
      idempotency_key: request.idempotency_key ?? crypto.randomUUID()
    })
  );
}

export async function undoCommandExecution(commandExecutionId: string): Promise<CommandResponse> {
  return requestBackend<CommandResultData>("/api/v1/projects/undo", jsonRequest({ command_execution_id: commandExecutionId }));
}

export async function getProjectSettings(projectId: string): Promise<SettingsData> {
  return (await requestBackend<SettingsData>(`/api/v1/projects/${projectId}/settings`)).data;
}

export async function updateProjectSettings(projectId: string, request: UpdateSettingsRequest): Promise<CommandResponse> {
  return requestBackend<CommandResultData>(
    `/api/v1/projects/${projectId}/settings`,
    jsonRequest(request, { method: "PATCH" })
  );
}

export async function listEnvironmentProfiles(projectId: string): Promise<EnvironmentProfile[]> {
  return (await requestBackend<EnvironmentProfile[]>(`/api/v1/projects/${projectId}/environments`)).data;
}

export async function createEnvironmentProfile(projectId: string, request: CreateEnvironmentRequest): Promise<CommandResponse> {
  return requestBackend<CommandResultData>(`/api/v1/projects/${projectId}/environments`, jsonRequest(request));
}

export async function updateEnvironmentProfile(
  projectId: string,
  environmentId: string,
  request: UpdateEnvironmentRequest
): Promise<CommandResponse> {
  return requestBackend<CommandResultData>(
    `/api/v1/projects/${projectId}/environments/${environmentId}`,
    jsonRequest(request, { method: "PATCH" })
  );
}

export function formatAuditRef(auditRef?: AuditRef): string | undefined {
  return auditRef ? `${auditRef.ref_type}:${auditRef.ref_id}` : undefined;
}
