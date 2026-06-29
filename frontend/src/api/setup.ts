import { jsonRequest, requestBackend, type BackendResponse } from "./backend";
import type { CommandPreviewData, CommandResultData, DryRunData } from "./project";

export interface ArtifactVersion {
  artifact_version_id: string;
  platform: string;
  channel: string;
  build_number: string;
  download_url: string | null;
  sha256: string | null;
  released_at: string | null;
  discovered_at: string | null;
  metadata: Record<string, unknown>;
}

export interface DependencyCheck {
  dependency_check_id?: string;
  project_id?: string;
  check_key: string;
  category: string;
  status: string;
  message: string;
  details: Record<string, unknown>;
}

export interface ProcessStatus {
  process_run_id: string;
  project_id: string;
  state: string;
  pid: number | null;
  started_at: string | null;
  stopped_at: string | null;
  exit_code: number | null;
  stdout_tail: string[];
  stderr_tail: string[];
}

export interface InstallArtifactRequest {
  build_number: string;
  platform?: string;
  channel?: string;
}

export interface ServerConfigRequest {
  server_data_path: string;
  options?: Record<string, unknown>;
}

export interface DependencyChecksRequest {
  server_data_path: string;
  categories?: string[] | null;
}

export interface PrepareDatabaseRequest {
  server_data_path: string;
  database_name?: string;
}

export interface StartServerProcessRequest {
  fxserver_path: string;
  server_data_path: string;
  txadmin_mode?: boolean;
  extra_args?: string[] | null;
}

export interface StopServerProcessRequest {
  process_run_id: string;
}

export interface RestartServerProcessRequest extends StartServerProcessRequest {
  process_run_id: string;
}

export interface PinArtifactRequest {
  artifact_version_id?: string | null;
  channel_preference?: string;
  environment_id?: string | null;
  pinned_reason?: string | null;
}

export type SetupCommandResponse = BackendResponse<CommandResultData>;

export async function listArtifacts(platform?: string, channel?: string): Promise<ArtifactVersion[]> {
  const params = new URLSearchParams();
  if (platform) {
    params.set("platform", platform);
  }
  if (channel) {
    params.set("channel", channel);
  }
  const query = params.toString();
  return (await requestBackend<ArtifactVersion[]>(`/api/v1/artifacts${query ? `?${query}` : ""}`)).data;
}

export async function refreshArtifactCatalog(platform = "windows", channel?: string | null): Promise<SetupCommandResponse> {
  return requestBackend<CommandResultData>("/api/v1/artifacts/refresh", jsonRequest({ platform, channel: channel ?? null }));
}

export async function pinArtifactVersion(projectId: string, request: PinArtifactRequest): Promise<SetupCommandResponse> {
  return requestBackend<CommandResultData>(`/api/v1/projects/${projectId}/artifact-pin`, jsonRequest(request, { method: "PUT" }));
}

export async function previewInstallArtifact(projectId: string, request: InstallArtifactRequest): Promise<BackendResponse<CommandPreviewData>> {
  return requestBackend<CommandPreviewData>(`/api/v1/projects/${projectId}/setup/artifact/install-plan`, jsonRequest(request));
}

export async function dryRunInstallArtifact(projectId: string, request: InstallArtifactRequest): Promise<BackendResponse<DryRunData>> {
  return requestBackend<DryRunData>(`/api/v1/projects/${projectId}/setup/artifact/install-dry-run`, jsonRequest(request));
}

export async function installArtifact(projectId: string, request: InstallArtifactRequest): Promise<SetupCommandResponse> {
  return requestBackend<CommandResultData>(`/api/v1/projects/${projectId}/setup/artifact/install`, jsonRequest(request));
}

export async function previewServerConfig(projectId: string, request: ServerConfigRequest): Promise<BackendResponse<CommandPreviewData>> {
  return requestBackend<CommandPreviewData>(`/api/v1/projects/${projectId}/setup/server-config/plan`, jsonRequest(request));
}

export async function dryRunServerConfig(projectId: string, request: ServerConfigRequest): Promise<BackendResponse<DryRunData>> {
  return requestBackend<DryRunData>(`/api/v1/projects/${projectId}/setup/server-config/dry-run`, jsonRequest(request));
}

export async function writeServerConfig(projectId: string, request: ServerConfigRequest): Promise<SetupCommandResponse> {
  return requestBackend<CommandResultData>(`/api/v1/projects/${projectId}/setup/server-config/write`, jsonRequest(request));
}

export async function runDependencyChecks(projectId: string, request: DependencyChecksRequest): Promise<SetupCommandResponse> {
  return requestBackend<CommandResultData>(`/api/v1/projects/${projectId}/dependency-checks/run`, jsonRequest(request));
}

export async function listDependencyChecks(projectId: string): Promise<DependencyCheck[]> {
  return (await requestBackend<DependencyCheck[]>(`/api/v1/projects/${projectId}/dependency-checks`)).data;
}

export async function prepareDatabase(projectId: string, request: PrepareDatabaseRequest): Promise<SetupCommandResponse> {
  return requestBackend<CommandResultData>(`/api/v1/projects/${projectId}/setup/database/prepare`, jsonRequest(request));
}

export async function previewStartProcess(projectId: string, request: StartServerProcessRequest): Promise<BackendResponse<CommandPreviewData>> {
  return requestBackend<CommandPreviewData>(`/api/v1/projects/${projectId}/process/start-plan`, jsonRequest(request));
}

export async function startProcess(projectId: string, request: StartServerProcessRequest): Promise<SetupCommandResponse> {
  return requestBackend<CommandResultData>(`/api/v1/projects/${projectId}/process/start`, jsonRequest(request));
}

export async function stopProcess(projectId: string, request: StopServerProcessRequest): Promise<SetupCommandResponse> {
  return requestBackend<CommandResultData>(`/api/v1/projects/${projectId}/process/stop`, jsonRequest(request));
}

export async function restartProcess(projectId: string, request: RestartServerProcessRequest): Promise<SetupCommandResponse> {
  return requestBackend<CommandResultData>(`/api/v1/projects/${projectId}/process/restart`, jsonRequest(request));
}

export async function getProcessStatus(projectId: string, processRunId: string): Promise<ProcessStatus> {
  return (await requestBackend<ProcessStatus>(`/api/v1/projects/${projectId}/process/${processRunId}`)).data;
}

export interface FxserverDetectResult {
  detected_path: string | null;
  found: boolean;
}

export interface FxserverValidateResult {
  valid: boolean;
  message: string | null;
  resolved_path: string | null;
}

export async function detectFxserver(projectId: string): Promise<BackendResponse<FxserverDetectResult>> {
  return requestBackend<FxserverDetectResult>(`/api/v1/projects/${projectId}/setup/fxserver/detect`);
}

export async function validateFxserverPath(projectId: string, fxserverPath: string): Promise<BackendResponse<FxserverValidateResult>> {
  return requestBackend<FxserverValidateResult>(`/api/v1/projects/${projectId}/setup/fxserver/validate`, jsonRequest({ fxserver_path: fxserverPath }));
}
