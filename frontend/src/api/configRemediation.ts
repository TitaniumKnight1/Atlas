import { jsonRequest, requestBackend, type BackendResponse } from "./backend";
import type { CommandPreviewData, CommandResultData, DryRunData } from "./project";

export async function previewCommentOutDanglingEnsure(
  projectId: string,
  findingId: string
): Promise<BackendResponse<CommandPreviewData>> {
  return requestBackend<CommandPreviewData>(
    `/api/v1/projects/${projectId}/config-remediation/comment-dangling/preview`,
    jsonRequest({ finding_id: findingId })
  );
}

export async function dryRunCommentOutDanglingEnsure(
  projectId: string,
  findingId: string
): Promise<BackendResponse<DryRunData>> {
  return requestBackend<DryRunData>(
    `/api/v1/projects/${projectId}/config-remediation/comment-dangling/dry-run`,
    jsonRequest({ finding_id: findingId })
  );
}

export async function applyCommentOutDanglingEnsure(
  projectId: string,
  findingId: string
): Promise<BackendResponse<CommandResultData>> {
  return requestBackend<CommandResultData>(
    `/api/v1/projects/${projectId}/config-remediation/comment-dangling/apply`,
    jsonRequest({ finding_id: findingId })
  );
}

export async function previewRewriteAbsolutePath(
  projectId: string,
  findingId: string
): Promise<BackendResponse<CommandPreviewData>> {
  return requestBackend<CommandPreviewData>(
    `/api/v1/projects/${projectId}/config-remediation/rewrite-absolute-path/preview`,
    jsonRequest({ finding_id: findingId })
  );
}

export async function dryRunRewriteAbsolutePath(
  projectId: string,
  findingId: string
): Promise<BackendResponse<DryRunData>> {
  return requestBackend<DryRunData>(
    `/api/v1/projects/${projectId}/config-remediation/rewrite-absolute-path/dry-run`,
    jsonRequest({ finding_id: findingId })
  );
}

export async function applyRewriteAbsolutePath(
  projectId: string,
  findingId: string
): Promise<BackendResponse<CommandResultData>> {
  return requestBackend<CommandResultData>(
    `/api/v1/projects/${projectId}/config-remediation/rewrite-absolute-path/apply`,
    jsonRequest({ finding_id: findingId })
  );
}
