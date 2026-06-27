import { jsonRequest, requestBackend, type BackendResponse } from "./backend";

export interface BackupPlan {
  backup_plan_id: string;
  project_id: string;
  name: string;
  backup_scope: string;
  retention_policy: { keep_count?: number; keep_days?: number } | null;
  schedule_interval_seconds: number | null;
  next_run_at: string | null;
  is_enabled: boolean;
}

export interface BackupRun {
  backup_run_id: string;
  backup_plan_id: string | null;
  project_id: string;
  status: string;
  trigger_type: string;
  started_at: string;
  finished_at: string | null;
  total_bytes: number | null;
  content_hash: string | null;
  archive_path: string | null;
  manifest_json: Record<string, unknown> | null;
  idempotency_key: string | null;
}

export interface RestorePreview {
  backup_run_id: string;
  project_root: string;
  overwrite_paths: string[];
  warnings: string[];
  requires_pre_restore_snapshot: boolean;
}

export interface RestoreResult {
  restore_run_id: string;
  status: string;
  command_execution_id?: string;
  pre_restore_snapshot_path?: string | null;
  undo_available?: boolean;
}

export interface CreateBackupPlanRequest {
  name: string;
  backup_scope?: string;
  retention_policy?: { keep_count?: number; keep_days?: number } | null;
  schedule_interval_seconds?: number | null;
  is_enabled?: boolean;
}

export type BackupResponse<T> = BackendResponse<T>;

export async function listBackupPlans(projectId: string): Promise<BackupPlan[]> {
  return (await requestBackend<BackupPlan[]>(`/api/v1/projects/${projectId}/backups/plans`)).data;
}

export async function createBackupPlan(projectId: string, request: CreateBackupPlanRequest): Promise<BackupPlan> {
  return (await requestBackend<BackupPlan>(`/api/v1/projects/${projectId}/backups/plans`, jsonRequest(request))).data;
}

export interface UpdateBackupPlanRequest {
  retention_policy?: { keep_count?: number; keep_days?: number } | null;
  schedule_interval_seconds?: number | null;
  is_enabled?: boolean | null;
}

export async function updateBackupPlan(projectId: string, planId: string, request: UpdateBackupPlanRequest): Promise<BackupPlan> {
  return (await requestBackend<BackupPlan>(`/api/v1/projects/${projectId}/backups/plans/${planId}`, {
    method: "PATCH",
    ...jsonRequest(request)
  })).data;
}

export async function listBackupRuns(projectId: string): Promise<BackupRun[]> {
  return (await requestBackend<BackupRun[]>(`/api/v1/projects/${projectId}/backups/runs`)).data;
}

export async function getBackupRun(projectId: string, backupRunId: string): Promise<BackupRun & { items?: Record<string, unknown>[] }> {
  return (await requestBackend<BackupRun & { items?: Record<string, unknown>[] }>(`/api/v1/projects/${projectId}/backups/runs/${backupRunId}`)).data;
}

export async function runBackup(projectId: string, backupPlanId?: string | null): Promise<BackendResponse<BackupRun>> {
  return requestBackend<BackupRun>(
    `/api/v1/projects/${projectId}/backups/runs`,
    jsonRequest({ backup_plan_id: backupPlanId ?? null, idempotency_key: crypto.randomUUID() })
  );
}

export async function previewRestore(projectId: string, backupRunId: string): Promise<BackupResponse<RestorePreview>> {
  const response = await requestBackend<RestorePreview>(`/api/v1/projects/${projectId}/backups/restores/plan`, jsonRequest({ backup_run_id: backupRunId }));
  return response;
}

export async function executeRestore(
  projectId: string,
  backupRunId: string,
  confirmDestructive: boolean
): Promise<RestoreResult> {
  return (
    await requestBackend<RestoreResult>(
      `/api/v1/projects/${projectId}/backups/restores`,
      jsonRequest({ backup_run_id: backupRunId, confirm_destructive: confirmDestructive, idempotency_key: crypto.randomUUID() })
    )
  ).data;
}

export async function undoRestore(projectId: string, restoreRunId: string): Promise<Record<string, unknown>> {
  return (await requestBackend<Record<string, unknown>>(`/api/v1/projects/${projectId}/backups/restores/${restoreRunId}/undo`, jsonRequest({}))).data;
}

export async function evaluateRetention(projectId: string, backupPlanId?: string | null): Promise<{ pruned: string[]; skipped: string[]; evaluated: number }> {
  return (
    await requestBackend<{ pruned: string[]; skipped: string[]; evaluated: number }>(
      `/api/v1/projects/${projectId}/backups/retention/evaluate`,
      jsonRequest({ backup_plan_id: backupPlanId ?? null })
    )
  ).data;
}
