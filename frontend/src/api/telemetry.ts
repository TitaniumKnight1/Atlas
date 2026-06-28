import { jsonRequest, requestBackend } from "./backend";

export interface TelemetryPreferences {
  project_id: string | null;
  telemetry_enabled: boolean;
  crash_reporting_enabled: boolean;
  plugin_telemetry_enabled: boolean;
  last_prompted_at: string | null;
  updated_at: string | null;
  updated_by: string | null;
  error_reporting_available: boolean;
  consent_prompt_pending: boolean;
}

export interface UpdateTelemetryPreferencesInput {
  telemetry_enabled?: boolean;
  crash_reporting_enabled?: boolean;
  plugin_telemetry_enabled?: boolean;
  record_consent_prompt_shown?: boolean;
  updated_by?: string;
}

export async function getTelemetryPreferences(): Promise<TelemetryPreferences> {
  return (await requestBackend<TelemetryPreferences>("/api/v1/telemetry/preferences")).data;
}

export async function updateTelemetryPreferences(
  patch: UpdateTelemetryPreferencesInput
): Promise<TelemetryPreferences> {
  await requestBackend<Record<string, unknown>>(
    "/api/v1/telemetry/preferences",
    jsonRequest(patch, { method: "PATCH" })
  );
  return getTelemetryPreferences();
}
