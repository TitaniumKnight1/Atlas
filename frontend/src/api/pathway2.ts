import { jsonRequest, requestBackend, type BackendResponse } from "./backend";
import type { CommandPreviewData, CommandResultData, DryRunData } from "./project";

export interface Pathway2Status {
  project_id: string;
  structure_scorecard: StructureScorecard;
  inline_secrets: InlineSecretFinding[];
  pathway2_state: Pathway2State;
  run_blocked_reason: string | null;
}

export interface Pathway2State {
  origin: string | null;
  normalized: boolean;
  secrets_substituted: boolean;
  run_ready: boolean;
  server_cfg_path: string | null;
  overlay_path: string | null;
}

export interface StructureCheck {
  present: boolean;
}

export interface StructureScorecard {
  looks_like_fivem_server: boolean;
  confidence: string;
  score: string;
  checks: Record<string, StructureCheck>;
  server_cfg_path: string | null;
  overlay_path: string | null;
  git_remote_redacted: string | null;
  resource_count: number | null;
}

export interface InlineSecretFinding {
  path: string;
  line: number;
  secret_type: string;
  redacted_preview: string;
  severity: string;
}

export async function previewAdoptRepository(rootPath: string, remoteUrl?: string): Promise<BackendResponse<CommandPreviewData>> {
  return requestBackend<CommandPreviewData>("/api/v1/pathway2/adopt-plan", jsonRequest({ root_path: rootPath, remote_url: remoteUrl ?? null }));
}

export async function dryRunAdoptRepository(rootPath: string, remoteUrl?: string): Promise<BackendResponse<DryRunData>> {
  return requestBackend<DryRunData>("/api/v1/pathway2/adopt-dry-run", jsonRequest({ root_path: rootPath, remote_url: remoteUrl ?? null }));
}

export async function adoptRepository(rootPath: string, remoteUrl?: string): Promise<BackendResponse<CommandResultData>> {
  return requestBackend<CommandResultData>("/api/v1/pathway2/adopt", jsonRequest({ root_path: rootPath, remote_url: remoteUrl ?? null }));
}

export async function getPathway2Status(projectId: string): Promise<BackendResponse<Pathway2Status>> {
  return requestBackend<Pathway2Status>(`/api/v1/projects/${projectId}/pathway2/status`);
}

export async function previewRepoNormalization(projectId: string): Promise<BackendResponse<CommandPreviewData>> {
  return requestBackend<CommandPreviewData>(`/api/v1/projects/${projectId}/pathway2/normalization-plan`, { method: "POST" });
}

export async function dryRunRepoNormalization(projectId: string): Promise<BackendResponse<DryRunData>> {
  return requestBackend<DryRunData>(`/api/v1/projects/${projectId}/pathway2/normalization-dry-run`, { method: "POST" });
}

export async function applyRepoNormalization(projectId: string): Promise<BackendResponse<CommandResultData>> {
  return requestBackend<CommandResultData>(`/api/v1/projects/${projectId}/pathway2/normalization/apply`, jsonRequest({}));
}

export async function undoPathway2Command(projectId: string, commandExecutionId: string): Promise<BackendResponse<CommandResultData>> {
  return requestBackend<CommandResultData>(
    `/api/v1/projects/${projectId}/pathway2/undo`,
    jsonRequest({ command_execution_id: commandExecutionId })
  );
}
