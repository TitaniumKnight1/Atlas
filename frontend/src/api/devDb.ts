import { jsonRequest, requestBackend, type BackendResponse } from "./backend";
import type { CommandPreviewData, CommandResultData, DryRunData } from "./project";

export interface DevDatabaseStatus {
  lifecycle: string;
  engine: string;
  container_id?: string | null;
  container_name?: string | null;
  volume_name?: string | null;
  docker_state?: string | null;
  container_running: boolean;
  mysql_reachable: boolean;
  connection_string: string;
  message?: string | null;
}

export async function getDevDatabaseStatus(projectId: string): Promise<BackendResponse<DevDatabaseStatus>> {
  return requestBackend<DevDatabaseStatus>(`/api/v1/projects/${projectId}/dev-db/status`);
}

export async function previewProvisionDevDatabase(projectId: string): Promise<BackendResponse<CommandPreviewData>> {
  return requestBackend<CommandPreviewData>(`/api/v1/projects/${projectId}/dev-db/provision-plan`, { method: "POST" });
}

export async function dryRunProvisionDevDatabase(projectId: string): Promise<BackendResponse<DryRunData>> {
  return requestBackend<DryRunData>(`/api/v1/projects/${projectId}/dev-db/provision-dry-run`, { method: "POST" });
}

export async function provisionDevDatabase(projectId: string): Promise<BackendResponse<CommandResultData>> {
  return requestBackend<CommandResultData>(`/api/v1/projects/${projectId}/dev-db/provision/apply`, { method: "POST" });
}

export async function startDevDatabase(projectId: string): Promise<BackendResponse<CommandResultData>> {
  return requestBackend<CommandResultData>(`/api/v1/projects/${projectId}/dev-db/start/apply`, { method: "POST" });
}

export async function stopDevDatabase(projectId: string): Promise<BackendResponse<CommandResultData>> {
  return requestBackend<CommandResultData>(`/api/v1/projects/${projectId}/dev-db/stop/apply`, { method: "POST" });
}

export async function previewTeardownDevDatabase(projectId: string): Promise<BackendResponse<CommandPreviewData>> {
  return requestBackend<CommandPreviewData>(`/api/v1/projects/${projectId}/dev-db/teardown-plan`, { method: "POST" });
}

export async function teardownDevDatabase(projectId: string): Promise<BackendResponse<CommandResultData>> {
  return requestBackend<CommandResultData>(`/api/v1/projects/${projectId}/dev-db/teardown/apply`, { method: "POST" });
}

export async function undoDevDatabaseCommand(
  projectId: string,
  commandExecutionId: string
): Promise<BackendResponse<CommandResultData>> {
  return requestBackend<CommandResultData>(
    `/api/v1/projects/${projectId}/dev-db/undo`,
    jsonRequest({ command_execution_id: commandExecutionId })
  );
}
