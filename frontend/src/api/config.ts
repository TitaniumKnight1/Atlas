import { jsonRequest, requestBackend, type BackendResponse } from "./backend";
import type { CommandPreviewData, CommandResultData, DryRunData } from "./project";

export interface ConfigFileSummary {
  config_file_id: string;
  project_id: string;
  path: string;
  config_type: string;
  content_hash: string | null;
  updated_at: string | null;
}

export interface ConfigFileView extends ConfigFileSummary {
  absolute_path: string;
  content: string | null;
}

export interface ValidationFinding {
  finding_id?: string;
  severity: string;
  rule_id: string;
  path: string;
  line: number | null;
  message: string;
  details: Record<string, unknown>;
}

export interface SecretFinding {
  secret_finding_id?: string;
  project_id?: string;
  config_file_id?: string;
  detector_id: string;
  severity: string;
  path: string;
  line: number | null;
  redacted_preview: string;
  secret_type: string | null;
  status?: string;
}

export type ConfigCommandResponse = BackendResponse<CommandResultData>;

export async function listConfigFiles(projectId: string): Promise<ConfigFileSummary[]> {
  return (await requestBackend<ConfigFileSummary[]>(`/api/v1/projects/${projectId}/config-files`)).data;
}

export async function getConfigFile(projectId: string, configFileId: string): Promise<ConfigFileView> {
  return (await requestBackend<ConfigFileView>(`/api/v1/projects/${projectId}/config-files/${configFileId}`)).data;
}

export async function rescanConfigFiles(projectId: string, scanRoots?: string[] | null): Promise<Record<string, unknown>> {
  return (await requestBackend<Record<string, unknown>>(`/api/v1/projects/${projectId}/config-files/rescan`, jsonRequest({ scan_roots: scanRoots ?? null }))).data;
}

export async function previewConfigChange(
  projectId: string,
  configFileId: string,
  proposedContent: string
): Promise<BackendResponse<CommandPreviewData>> {
  return requestBackend<CommandPreviewData>(
    `/api/v1/projects/${projectId}/config/change-plan`,
    jsonRequest({ config_file_id: configFileId, proposed_content: proposedContent })
  );
}

export async function dryRunConfigChange(
  projectId: string,
  configFileId: string,
  proposedContent: string
): Promise<BackendResponse<DryRunData>> {
  return requestBackend<DryRunData>(
    `/api/v1/projects/${projectId}/config/change-dry-run`,
    jsonRequest({ config_file_id: configFileId, proposed_content: proposedContent })
  );
}

export async function applyConfigChange(projectId: string, configFileId: string, proposedContent: string): Promise<ConfigCommandResponse> {
  return requestBackend<CommandResultData>(
    `/api/v1/projects/${projectId}/config/change-sets/apply`,
    jsonRequest({ config_file_id: configFileId, proposed_content: proposedContent, idempotency_key: crypto.randomUUID() })
  );
}

export async function runValidation(projectId: string, configFileId?: string | null): Promise<Record<string, unknown>> {
  return (await requestBackend<Record<string, unknown>>(`/api/v1/projects/${projectId}/config/validation-runs`, jsonRequest({ config_file_id: configFileId ?? null }))).data;
}

export async function listValidationFindings(projectId: string): Promise<ValidationFinding[]> {
  return (await requestBackend<ValidationFinding[]>(`/api/v1/projects/${projectId}/config/findings`)).data;
}

export async function runSecretScan(projectId: string, configFileId?: string | null): Promise<Record<string, unknown>> {
  return (await requestBackend<Record<string, unknown>>(`/api/v1/projects/${projectId}/config/secret-scan`, jsonRequest({ config_file_id: configFileId ?? null }))).data;
}

export async function listSecretFindings(projectId: string): Promise<SecretFinding[]> {
  return (await requestBackend<SecretFinding[]>(`/api/v1/projects/${projectId}/config/secret-findings`)).data;
}

/** Always mask secret values — never display raw content from the backend. */
export function formatMaskedSecret(finding: SecretFinding): string {
  const type = finding.secret_type ?? "unknown";
  const preview = finding.redacted_preview?.trim() ? finding.redacted_preview : "████████";
  return `secret detected: ${type} — ${preview}`;
}
