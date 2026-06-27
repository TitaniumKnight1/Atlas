import { jsonRequest, requestBackend } from "./backend";

export interface IncidentGroup {
  incident_group_id: string;
  project_id: string;
  fingerprint: string;
  title: string;
  severity: string;
  category: string;
  status: string;
  first_seen_at: string;
  last_seen_at: string;
  occurrence_count: number;
}

export interface IncidentOccurrence {
  occurrence_id: string;
  incident_group_id: string;
  project_id: string;
  occurred_at: string;
  source_type: string;
  message: string;
}

export interface IncidentGroupDetail extends IncidentGroup {
  fingerprint_components: Record<string, unknown>;
  occurrences: IncidentOccurrence[];
  related_groups: Array<Record<string, unknown>>;
}

export interface ContextSnapshot {
  context_snapshot_id: string;
  context_type: string;
  snapshot_json: Record<string, unknown>;
  redaction_state: string;
  captured_at: string;
}

export interface OccurrenceTimeline {
  occurrence: IncidentOccurrence;
  breadcrumbs: Array<Record<string, unknown>>;
  context_snapshots: ContextSnapshot[];
  stack_trace: Record<string, unknown> | null;
}

export interface IncidentExportResult {
  incident_export_id: string;
  incident_group_id: string;
  occurrence_id: string | null;
  export_format: string;
  redaction_profile: string;
  content_hash: string;
  local_file_path: string;
  markdown: string;
  redaction_summary: {
    redaction_count: number;
    categories: string[];
    rules_applied: string[];
    policy: string;
    note: string;
  };
  sanitized: boolean;
}

export interface IncidentCompareResult {
  groups: Array<Record<string, unknown>>;
  shared: Record<string, unknown>;
  differences: Array<{ field: string; values: Record<string, unknown> }>;
}



export async function listIncidents(projectId: string, limit = 100): Promise<IncidentGroup[]> {
  return (await requestBackend<IncidentGroup[]>(`/api/v1/projects/${projectId}/incidents?limit=${limit}`)).data;
}

export async function getIncident(projectId: string, incidentGroupId: string): Promise<IncidentGroupDetail> {
  return (await requestBackend<IncidentGroupDetail>(`/api/v1/projects/${projectId}/incidents/${incidentGroupId}`)).data;
}

export async function getGroupTimeline(projectId: string, incidentGroupId: string): Promise<{ incident_group_id: string; timeline: Array<Record<string, unknown>> }> {
  return (await requestBackend<{ incident_group_id: string; timeline: Array<Record<string, unknown>> }>(`/api/v1/projects/${projectId}/incidents/${incidentGroupId}/timeline`)).data;
}

export async function getOccurrenceTimeline(projectId: string, occurrenceId: string): Promise<OccurrenceTimeline> {
  return (await requestBackend<OccurrenceTimeline>(`/api/v1/projects/${projectId}/incidents/occurrences/${occurrenceId}/timeline`)).data;
}

export async function compareIncidents(projectId: string, incidentGroupIds: string[]): Promise<IncidentCompareResult> {
  return (await requestBackend<IncidentCompareResult>(`/api/v1/projects/${projectId}/incidents/compare`, jsonRequest({ incident_group_ids: incidentGroupIds }))).data;
}

export async function exportIncidentMarkdown(
  projectId: string,
  incidentGroupId: string,
  occurrenceId?: string | null,
  redactionProfile = "default"
): Promise<IncidentExportResult> {
  return (
    await requestBackend<IncidentExportResult>(
      `/api/v1/projects/${projectId}/incidents/${incidentGroupId}/exports/markdown`,
      jsonRequest({ occurrence_id: occurrenceId ?? null, redaction_profile: redactionProfile })
    )
  ).data;
}

export async function listIncidentExports(projectId: string, incidentGroupId: string): Promise<Array<Record<string, unknown>>> {
  return (await requestBackend<Array<Record<string, unknown>>>(`/api/v1/projects/${projectId}/incidents/${incidentGroupId}/exports`)).data;
}
