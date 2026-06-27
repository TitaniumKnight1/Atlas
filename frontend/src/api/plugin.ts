import { jsonRequest, requestBackend } from "./backend";

export interface PluginSettings {
  global_enabled: boolean;
  consent_model: string;
  trust_warning: string;
}

export interface PluginRegistration {
  plugin_id: string;
  plugin_key: string;
  name: string;
  version: string;
  author: string;
  source_ref: string | null;
  contribution_points: string[];
  requested_capabilities: string[];
  registration_status: string;
  trust_status: string;
  is_enabled: boolean;
  registered_at: string;
  updated_at: string;
}

export interface PluginCapabilities {
  plugin_id: string;
  plugin_key: string;
  project_id: string;
  requested_capabilities: string[];
  granted_capabilities: string[];
  trust_status: string;
  consent_model: string | null;
  trust_acknowledgment: Record<string, unknown> | null;
}

export interface PluginRuntime {
  runtime_id: string;
  plugin_id: string;
  plugin_key: string | null;
  project_id: string;
  status: string;
  pid: number | null;
  started_at: string;
  stopped_at: string | null;
  exit_code: number | null;
  failure_summary: Record<string, unknown> | null;
  atlas_pid: number;
}

export interface CapabilityCall {
  call_id: string;
  runtime_id: string;
  plugin_id: string;
  project_id: string;
  capability: string;
  decision: string;
  outcome: string;
  request: Record<string, unknown> | null;
  response: Record<string, unknown> | null;
  occurred_at: string;
}

export interface PluginContribution {
  contribution_id: string;
  plugin_id: string;
  project_id: string;
  contribution_point: string;
  identifier: string;
  required_capability: string;
  descriptor: Record<string, unknown>;
  is_enabled: boolean;
  registered_at: string;
  disabled_at: string | null;
  live_enabled: boolean;
}

export async function getPluginSettings(): Promise<PluginSettings> {
  return (await requestBackend<PluginSettings>("/api/v1/plugin/settings")).data;
}

export async function setGlobalPluginEnabled(globalEnabled: boolean): Promise<{ global_enabled: boolean }> {
  return (await requestBackend<{ global_enabled: boolean }>("/api/v1/plugin/settings", jsonRequest({ global_enabled: globalEnabled }, { method: "PATCH" }))).data;
}

export async function listPlugins(): Promise<PluginRegistration[]> {
  return (await requestBackend<PluginRegistration[]>("/api/v1/plugins")).data;
}

export async function getPlugin(pluginId: string): Promise<PluginRegistration> {
  return (await requestBackend<PluginRegistration>(`/api/v1/plugins/${pluginId}`)).data;
}

export async function setPluginEnabled(pluginId: string, enabled: boolean): Promise<PluginRegistration> {
  return (await requestBackend<PluginRegistration>(`/api/v1/plugins/${pluginId}/state`, jsonRequest({ enabled }, { method: "PATCH" }))).data;
}

export async function listPluginCapabilities(projectId: string, pluginId: string): Promise<PluginCapabilities> {
  return (await requestBackend<PluginCapabilities>(`/api/v1/projects/${projectId}/plugins/${pluginId}/capabilities`)).data;
}

export async function grantPluginCapabilities(
  projectId: string,
  pluginId: string,
  capabilities: string[],
  trustAcknowledgment: Record<string, unknown>
): Promise<Record<string, unknown>> {
  return (
    await requestBackend<Record<string, unknown>>(
      `/api/v1/projects/${projectId}/plugins/${pluginId}/capabilities/grant`,
      jsonRequest({ capabilities, trust_acknowledgment: trustAcknowledgment, idempotency_key: crypto.randomUUID() })
    )
  ).data;
}

export async function revokePluginCapability(projectId: string, pluginId: string, capability: string): Promise<Record<string, unknown>> {
  return (
    await requestBackend<Record<string, unknown>>(
      `/api/v1/projects/${projectId}/plugins/${pluginId}/capabilities/revoke`,
      jsonRequest({ capability, idempotency_key: crypto.randomUUID() })
    )
  ).data;
}

export async function runPluginRuntime(projectId: string, pluginId: string, mode = "normal"): Promise<PluginRuntime & Record<string, unknown>> {
  return (
    await requestBackend<PluginRuntime & Record<string, unknown>>(
      `/api/v1/projects/${projectId}/plugins/${pluginId}/runtime/run`,
      jsonRequest({ mode })
    )
  ).data;
}

export async function getPluginRuntime(projectId: string, pluginId: string, runtimeId: string): Promise<PluginRuntime> {
  return (await requestBackend<PluginRuntime>(`/api/v1/projects/${projectId}/plugins/${pluginId}/runtime/${runtimeId}`)).data;
}

export async function stopPluginRuntime(projectId: string, pluginId: string, runtimeId: string): Promise<PluginRuntime> {
  return (await requestBackend<PluginRuntime>(`/api/v1/projects/${projectId}/plugins/${pluginId}/runtime/${runtimeId}/stop`, jsonRequest({}))).data;
}

export async function listPluginCapabilityCalls(projectId: string, pluginId: string): Promise<CapabilityCall[]> {
  return (await requestBackend<CapabilityCall[]>(`/api/v1/projects/${projectId}/plugins/${pluginId}/capability-calls`)).data;
}

export async function listPluginContributions(projectId: string): Promise<PluginContribution[]> {
  return (await requestBackend<PluginContribution[]>(`/api/v1/projects/${projectId}/plugin-contributions`)).data;
}

export async function registerPluginContributions(projectId: string, pluginId: string): Promise<Record<string, unknown>> {
  return (await requestBackend<Record<string, unknown>>(`/api/v1/projects/${projectId}/plugins/${pluginId}/contributions/register`, jsonRequest({}))).data;
}
