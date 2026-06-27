import { jsonRequest, requestBackend, type BackendResponse } from "./backend";
import type { CommandPreviewData, CommandResultData, DryRunData } from "./project";

export interface GitRepository {
  git_repository_id: string;
  project_id: string;
  local_path: string;
  remote_url: string | null;
  default_branch: string | null;
  repository_role: string;
  last_scanned_at: string | null;
}

export interface GitRef {
  ref_name: string;
  ref_type: string;
  commit_sha: string;
  is_current: boolean;
}

export interface GitFileChange {
  path: string;
  change_status: string;
  old_path: string | null;
  insertions: number;
  deletions: number;
}

export interface GitStatus {
  head_commit_sha: string;
  branch_name: string | null;
  is_dirty: boolean;
  ahead_count: number;
  behind_count: number;
  file_changes: GitFileChange[];
  summary: string;
}

export interface GitCommit {
  commit_sha: string;
  parent_shas: string[];
  author_name: string;
  committed_at: string;
  message_summary: string;
}

export interface CloneRepositoryRequest {
  remote_url: string;
  destination_path: string;
  repository_role?: string;
}

export type GitCommandResponse = BackendResponse<CommandResultData>;

export async function listGitRepositories(projectId: string, role?: string | null): Promise<GitRepository[]> {
  const query = role ? `?role=${encodeURIComponent(role)}` : "";
  return (await requestBackend<GitRepository[]>(`/api/v1/projects/${projectId}/git/repositories${query}`)).data;
}

export async function getGitRepository(projectId: string, repoId: string): Promise<GitRepository> {
  return (await requestBackend<GitRepository>(`/api/v1/projects/${projectId}/git/repositories/${repoId}`)).data;
}

export async function discoverGitRepositories(projectId: string, pathFilters?: string[] | null): Promise<Record<string, unknown>> {
  return (await requestBackend<Record<string, unknown>>(`/api/v1/projects/${projectId}/git/discover`, jsonRequest({ path_filters: pathFilters ?? null }))).data;
}

export async function previewCloneRepository(projectId: string, request: CloneRepositoryRequest): Promise<BackendResponse<CommandPreviewData>> {
  return requestBackend<CommandPreviewData>(`/api/v1/projects/${projectId}/git/clone-plan`, jsonRequest(request));
}

export async function dryRunCloneRepository(projectId: string, request: CloneRepositoryRequest): Promise<BackendResponse<DryRunData>> {
  return requestBackend<DryRunData>(`/api/v1/projects/${projectId}/git/clone-dry-run`, jsonRequest(request));
}

export async function cloneRepository(projectId: string, request: CloneRepositoryRequest): Promise<GitCommandResponse> {
  return requestBackend<CommandResultData>(`/api/v1/projects/${projectId}/git/clone`, jsonRequest(request));
}

export async function fetchRepository(projectId: string, repoId: string): Promise<GitCommandResponse> {
  return requestBackend<CommandResultData>(`/api/v1/projects/${projectId}/git/repositories/${repoId}/fetch`, jsonRequest({}));
}

export async function previewPullRepository(projectId: string, repoId: string): Promise<BackendResponse<CommandPreviewData>> {
  return requestBackend<CommandPreviewData>(`/api/v1/projects/${projectId}/git/repositories/${repoId}/pull-plan`, jsonRequest({}));
}

export async function dryRunPullRepository(projectId: string, repoId: string): Promise<BackendResponse<DryRunData>> {
  return requestBackend<DryRunData>(`/api/v1/projects/${projectId}/git/repositories/${repoId}/pull-dry-run`, jsonRequest({}));
}

export async function pullRepository(projectId: string, repoId: string, idempotencyKey?: string | null): Promise<GitCommandResponse> {
  return requestBackend<CommandResultData>(
    `/api/v1/projects/${projectId}/git/repositories/${repoId}/pull`,
    jsonRequest({ idempotency_key: idempotencyKey ?? crypto.randomUUID() })
  );
}

export async function getGitStatus(projectId: string, repoId: string): Promise<GitStatus> {
  return (await requestBackend<GitStatus>(`/api/v1/projects/${projectId}/git/repositories/${repoId}/status`)).data;
}

export async function listGitRefs(projectId: string, repoId: string): Promise<GitRef[]> {
  return (await requestBackend<GitRef[]>(`/api/v1/projects/${projectId}/git/repositories/${repoId}/refs`)).data;
}

export async function createBranch(projectId: string, repoId: string, branchName: string): Promise<GitCommandResponse> {
  return requestBackend<CommandResultData>(
    `/api/v1/projects/${projectId}/git/repositories/${repoId}/branches`,
    jsonRequest({ branch_name: branchName, idempotency_key: crypto.randomUUID() })
  );
}

export async function checkoutRef(projectId: string, repoId: string, refName: string): Promise<GitCommandResponse> {
  return requestBackend<CommandResultData>(
    `/api/v1/projects/${projectId}/git/repositories/${repoId}/checkout`,
    jsonRequest({ ref_name: refName, idempotency_key: crypto.randomUUID() })
  );
}

export async function previewDeleteBranch(projectId: string, repoId: string, branchName: string): Promise<BackendResponse<CommandPreviewData>> {
  return requestBackend<CommandPreviewData>(
    `/api/v1/projects/${projectId}/git/repositories/${repoId}/branches/delete-plan`,
    jsonRequest({ branch_name: branchName })
  );
}

export async function dryRunDeleteBranch(projectId: string, repoId: string, branchName: string): Promise<BackendResponse<DryRunData>> {
  const preview = await previewDeleteBranch(projectId, repoId, branchName);
  return {
    data: {
      command_type: preview.data.command_type,
      valid: true,
      simulation: preview.data.preview
    },
    warnings: preview.warnings,
    auditRef: preview.auditRef
  };
}

export async function deleteBranch(projectId: string, repoId: string, branchName: string): Promise<GitCommandResponse> {
  return requestBackend<CommandResultData>(
    `/api/v1/projects/${projectId}/git/repositories/${repoId}/branches/delete`,
    jsonRequest({ branch_name: branchName, idempotency_key: crypto.randomUUID() })
  );
}

export async function getGitDiff(
  projectId: string,
  repoId: string,
  baseRef: string,
  headRef: string,
  pathFilter?: string | null
): Promise<Record<string, unknown>> {
  const params = new URLSearchParams({ base_ref: baseRef, head_ref: headRef });
  if (pathFilter) {
    params.set("path_filter", pathFilter);
  }
  return (await requestBackend<Record<string, unknown>>(`/api/v1/projects/${projectId}/git/repositories/${repoId}/diff?${params}`)).data;
}

export async function compareCommits(
  projectId: string,
  repoId: string,
  baseRef: string,
  headRef: string,
  limit = 20
): Promise<GitCommit[]> {
  const params = new URLSearchParams({ base_ref: baseRef, head_ref: headRef, limit: String(limit) });
  return (await requestBackend<GitCommit[]>(`/api/v1/projects/${projectId}/git/repositories/${repoId}/commits/compare?${params}`)).data;
}

export async function createCommit(
  projectId: string,
  repoId: string,
  message: string,
  paths?: string[] | null
): Promise<GitCommandResponse> {
  return requestBackend<CommandResultData>(
    `/api/v1/projects/${projectId}/git/repositories/${repoId}/commits`,
    jsonRequest({ message, paths: paths ?? null, idempotency_key: crypto.randomUUID() })
  );
}

export async function listGitOperations(projectId: string, repoId?: string | null): Promise<Record<string, unknown>[]> {
  const query = repoId ? `?repo_id=${encodeURIComponent(repoId)}` : "";
  return (await requestBackend<Record<string, unknown>[]>(`/api/v1/projects/${projectId}/git/operations${query}`)).data;
}
