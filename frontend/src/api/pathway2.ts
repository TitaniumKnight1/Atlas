import { jsonRequest, requestBackend, type BackendResponse } from "./backend";
import type { CommandPreviewData, CommandResultData, DryRunData } from "./project";

export interface Pathway2Status {
  project_id: string;
  structure_scorecard: StructureScorecard;
  inline_secrets: InlineSecretFinding[];
  pathway2_state: Pathway2State;
  substitution_slots?: SubstitutionSlotPreview[];
  unset_dev_slots?: string[];
  run_blocked_reason: string | null;
}

export interface SubstitutionSlotPreview {
  slot_id: string;
  line_number: number;
  convar_key: string | null;
  secret_type: string | null;
  handling_class: string;
  masked_source: string;
  replacement_line: string;
}

export interface Pathway2State {
  origin: string | null;
  normalized: boolean;
  secrets_substituted: boolean;
  run_ready: boolean;
  dev_transformed: boolean;
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

export async function previewSecretSubstitution(projectId: string): Promise<BackendResponse<CommandPreviewData>> {
  return requestBackend<CommandPreviewData>(`/api/v1/projects/${projectId}/pathway2/substitution-plan`, { method: "POST" });
}

export async function dryRunSecretSubstitution(projectId: string): Promise<BackendResponse<DryRunData>> {
  return requestBackend<DryRunData>(`/api/v1/projects/${projectId}/pathway2/substitution-dry-run`, { method: "POST" });
}

export async function applySecretSubstitution(projectId: string): Promise<BackendResponse<CommandResultData>> {
  return requestBackend<CommandResultData>(`/api/v1/projects/${projectId}/pathway2/substitution/apply`, jsonRequest({}));
}

export async function applyDevSecret(projectId: string, slotId: string, devValue: string): Promise<BackendResponse<CommandResultData>> {
  return requestBackend<CommandResultData>(
    `/api/v1/projects/${projectId}/pathway2/dev-secret/apply`,
    jsonRequest({ slot_id: slotId, dev_value: devValue })
  );
}

export interface DevTransformOptions {
  hostname?: string;
  max_clients?: number;
  udp_port?: number;
  tcp_port?: number;
}

export async function previewDevConfigTransform(projectId: string, options?: DevTransformOptions): Promise<BackendResponse<CommandPreviewData>> {
  return requestBackend<CommandPreviewData>(`/api/v1/projects/${projectId}/pathway2/transform-plan`, jsonRequest(options ?? {}));
}

export async function dryRunDevConfigTransform(projectId: string, options?: DevTransformOptions): Promise<BackendResponse<DryRunData>> {
  return requestBackend<DryRunData>(`/api/v1/projects/${projectId}/pathway2/transform-dry-run`, jsonRequest(options ?? {}));
}

export async function applyDevConfigTransform(projectId: string, options?: DevTransformOptions): Promise<BackendResponse<CommandResultData>> {
  return requestBackend<CommandResultData>(`/api/v1/projects/${projectId}/pathway2/transform/apply`, jsonRequest(options ?? {}));
}

export interface ReturnPathStatus {
  project_id: string;
  git_repository_id: string;
  branch_name: string | null;
  is_dirty: boolean;
  default_commit_paths: string[];
  contamination_report: ContaminationReport;
  gitignore_contains_overlay: boolean;
  manual_push_message: string;
}

export interface ContaminationReport {
  gate_status: "PASS" | "BLOCKED";
  allowed: boolean;
  staged_paths: string[];
  overlay_excluded: boolean;
  server_cfg_placeholder_only: boolean | null;
  findings: Array<{
    path: string;
    line: number;
    secret_type: string;
    redacted_preview: string;
    reason: string;
  }>;
  summary_lines: string[];
  push_seam: string;
  manual_push_message: string;
}

export interface SafeReturnCommitRequest {
  git_repository_id: string;
  message: string;
  paths?: string[] | null;
  include_server_cfg?: boolean;
}

export async function getReturnPathStatus(projectId: string, gitRepositoryId?: string): Promise<BackendResponse<ReturnPathStatus>> {
  const query = gitRepositoryId ? `?git_repository_id=${encodeURIComponent(gitRepositoryId)}` : "";
  return requestBackend<ReturnPathStatus>(`/api/v1/projects/${projectId}/pathway2/return-path/status${query}`);
}

export async function previewSafeReturnCommit(projectId: string, request: SafeReturnCommitRequest): Promise<BackendResponse<CommandPreviewData>> {
  return requestBackend<CommandPreviewData>(`/api/v1/projects/${projectId}/pathway2/return-commit-plan`, jsonRequest(request));
}

export async function dryRunSafeReturnCommit(projectId: string, request: SafeReturnCommitRequest): Promise<BackendResponse<DryRunData>> {
  return requestBackend<DryRunData>(`/api/v1/projects/${projectId}/pathway2/return-commit-dry-run`, jsonRequest(request));
}

export async function applySafeReturnCommit(projectId: string, request: SafeReturnCommitRequest): Promise<BackendResponse<CommandResultData>> {
  return requestBackend<CommandResultData>(`/api/v1/projects/${projectId}/pathway2/return-commit/apply`, jsonRequest(request));
}

export async function undoPathway2Command(projectId: string, commandExecutionId: string): Promise<BackendResponse<CommandResultData>> {
  return requestBackend<CommandResultData>(
    `/api/v1/projects/${projectId}/pathway2/undo`,
    jsonRequest({ command_execution_id: commandExecutionId })
  );
}
