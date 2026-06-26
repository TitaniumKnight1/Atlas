import { invoke } from "@tauri-apps/api/core";

export interface ResultEnvelope<TData> {
  ok: boolean;
  data?: TData;
  error?: {
    code: string;
    message: string;
  } | null;
  warnings: string[];
}

export interface HealthData {
  status: "ok";
  service: "atlas-backend";
  transport: "loopback-http";
  database_path: string;
  database_journal_mode: string;
}

export interface SqliteSmokeData {
  database_path: string;
  journal_mode: string;
  inserted_key: string;
  round_tripped_value: string;
}

let backendBaseUrlPromise: Promise<string> | undefined;

export async function getHealth(): Promise<HealthData> {
  return requestBackend<HealthData>("/api/v1/health");
}

export async function runSqliteSmoke(): Promise<SqliteSmokeData> {
  return requestBackend<SqliteSmokeData>("/api/v1/debug/sqlite-smoke", {
    method: "POST"
  });
}

async function requestBackend<TData>(path: string, init?: RequestInit): Promise<TData> {
  const baseUrl = await getBackendBaseUrl();
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.headers ?? {})
    }
  });

  if (!response.ok) {
    throw new Error(`Backend request failed with HTTP ${response.status}`);
  }

  const envelope = (await response.json()) as ResultEnvelope<TData>;
  if (!envelope.ok || !envelope.data) {
    throw new Error(envelope.error?.message ?? "Backend returned an unsuccessful response");
  }

  return envelope.data;
}

async function getBackendBaseUrl(): Promise<string> {
  backendBaseUrlPromise ??= resolveBackendBaseUrl();
  return backendBaseUrlPromise;
}

async function resolveBackendBaseUrl(): Promise<string> {
  const configuredUrl = import.meta.env.VITE_ATLAS_BACKEND_URL;
  if (configuredUrl) {
    return configuredUrl.replace(/\/$/, "");
  }

  const baseUrl = await invoke<string>("backend_base_url");
  return baseUrl.replace(/\/$/, "");
}
