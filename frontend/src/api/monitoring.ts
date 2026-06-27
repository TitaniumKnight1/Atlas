import { jsonRequest, requestBackend, type BackendResponse } from "./backend";

export interface MetricSource {
  metric_source_id: string;
  project_id: string;
  source_type: string;
  source_ref: string | null;
  display_name: string;
  is_enabled: boolean;
  metadata: Record<string, unknown>;
}

export interface MetricLatest {
  sample_id: string;
  metric_series_id: string;
  metric_name: string;
  source_type: string;
  source_ref: string | null;
  unit: string | null;
  value_real: number | null;
  value_text: string | null;
  quality: string;
  sampled_at: string;
}

export interface MetricSeries {
  metric_series_id: string;
  metric_source_id: string;
  metric_name: string;
  unit: string | null;
  value_type: string;
  retention_class: string;
}

export interface HistoryPoint {
  metric_series_id: string;
  metric_name?: string;
  bucket_start?: string;
  bucket_end?: string;
  sampled_at?: string;
  min_value?: number;
  max_value?: number;
  avg_value?: number;
  value_real?: number;
  quality?: string;
  sample_count?: number;
}

export interface HistoryResponse {
  resolution: string;
  points: HistoryPoint[];
}

export interface MonitoringAlert {
  monitoring_alert_id: string;
  project_id: string;
  name: string;
  severity: string;
  metric_series_id: string;
  condition: {
    metric_series_id: string;
    comparator: string;
    threshold: number;
    duration_seconds: number;
  };
  is_enabled: boolean;
  runtime_state: string;
  pending_since: string | null;
  created_at: string;
  updated_at: string;
}

export interface AlertEvent {
  alert_event_id: string;
  monitoring_alert_id: string;
  alert_name: string;
  severity: string;
  status: string;
  triggered_at: string;
  resolved_at: string | null;
  details: Record<string, unknown>;
}

export interface CollectionStatus {
  project_id: string;
  status: "running" | "stopped" | "already_running" | "not_running";
  interval_seconds?: number;
}

export interface CreateAlertRequest {
  name: string;
  severity: string;
  metric_series_id: string;
  comparator: string;
  threshold: number;
  duration_seconds?: number;
  is_enabled?: boolean;
}

export interface UpdateAlertRequest {
  name?: string;
  severity?: string;
  metric_series_id?: string;
  comparator?: string;
  threshold?: number;
  duration_seconds?: number;
  is_enabled?: boolean;
}

export async function listMetricSources(projectId: string): Promise<MetricSource[]> {
  return (await requestBackend<MetricSource[]>(`/api/v1/projects/${projectId}/monitoring/sources`)).data;
}

export async function getLatestMetrics(projectId: string): Promise<MetricLatest[]> {
  return (await requestBackend<MetricLatest[]>(`/api/v1/projects/${projectId}/monitoring/latest`)).data;
}

export async function listMetricSeries(projectId: string): Promise<MetricSeries[]> {
  return (await requestBackend<MetricSeries[]>(`/api/v1/projects/${projectId}/monitoring/series`)).data;
}

export async function queryMetricHistory(
  projectId: string,
  startAt: string,
  endAt: string,
  metricSeriesId?: string | null,
  resolution?: "raw" | "minute" | "hour" | null
): Promise<HistoryResponse> {
  const params = new URLSearchParams({ start_at: startAt, end_at: endAt });
  if (metricSeriesId) {
    params.set("metric_series_id", metricSeriesId);
  }
  if (resolution) {
    params.set("resolution", resolution);
  }
  return (await requestBackend<HistoryResponse>(`/api/v1/projects/${projectId}/monitoring/history?${params}`)).data;
}

export async function startCollection(projectId: string, intervalSeconds?: number | null): Promise<CollectionStatus> {
  return (
    await requestBackend<CollectionStatus>(
      `/api/v1/projects/${projectId}/monitoring/collection/start`,
      jsonRequest(intervalSeconds != null ? { interval_seconds: intervalSeconds } : {})
    )
  ).data;
}

export async function stopCollection(projectId: string): Promise<CollectionStatus> {
  return (await requestBackend<CollectionStatus>(`/api/v1/projects/${projectId}/monitoring/collection/stop`, jsonRequest({}))).data;
}

export async function listAlerts(projectId: string): Promise<MonitoringAlert[]> {
  return (await requestBackend<MonitoringAlert[]>(`/api/v1/projects/${projectId}/monitoring/alerts`)).data;
}

export async function createAlert(projectId: string, request: CreateAlertRequest): Promise<MonitoringAlert> {
  return (await requestBackend<MonitoringAlert>(`/api/v1/projects/${projectId}/monitoring/alerts`, jsonRequest(request))).data;
}

export async function updateAlert(projectId: string, alertId: string, request: UpdateAlertRequest): Promise<MonitoringAlert> {
  return (
    await requestBackend<MonitoringAlert>(`/api/v1/projects/${projectId}/monitoring/alerts/${alertId}`, jsonRequest(request, { method: "PATCH" }))
  ).data;
}

export async function deleteAlert(projectId: string, alertId: string): Promise<{ monitoring_alert_id: string; deleted: boolean }> {
  return (
    await requestBackend<{ monitoring_alert_id: string; deleted: boolean }>(
      `/api/v1/projects/${projectId}/monitoring/alerts/${alertId}`,
      { method: "DELETE", headers: { Accept: "application/json" } }
    )
  ).data;
}

export async function listAlertEvents(projectId: string, limit = 100): Promise<AlertEvent[]> {
  return (await requestBackend<AlertEvent[]>(`/api/v1/projects/${projectId}/monitoring/alert-events?limit=${limit}`)).data;
}

export async function evaluateAlerts(projectId: string): Promise<{ fired: number; resolved: number }> {
  return (await requestBackend<{ fired: number; resolved: number }>(`/api/v1/projects/${projectId}/monitoring/alerts/evaluate`, jsonRequest({}))).data;
}
