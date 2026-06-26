import { invoke } from "@tauri-apps/api/core";

export interface ApiErrorPayload {
  code: string;
  message: string;
}

export interface AuditRef {
  ref_type: string;
  ref_id: string;
}

export interface ResultEnvelope<TData> {
  ok: boolean;
  data?: TData;
  error?: ApiErrorPayload | null;
  warnings: string[];
  audit_ref?: AuditRef | null;
}

export interface BackendResponse<TData> {
  data: TData;
  warnings: string[];
  auditRef?: AuditRef;
}

export class BackendApiError extends Error {
  readonly code: string;
  readonly warnings: string[];
  readonly auditRef?: AuditRef;

  constructor(message: string, code = "ExternalAdapterFailed", warnings: string[] = [], auditRef?: AuditRef) {
    super(message);
    this.name = "BackendApiError";
    this.code = code;
    this.warnings = warnings;
    this.auditRef = auditRef;
  }
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
  return (await requestBackend<HealthData>("/api/v1/health")).data;
}

export async function runSqliteSmoke(): Promise<SqliteSmokeData> {
  return (
    await requestBackend<SqliteSmokeData>("/api/v1/debug/sqlite-smoke", {
      method: "POST"
    })
  ).data;
}

export async function requestBackend<TData>(path: string, init?: RequestInit): Promise<BackendResponse<TData>> {
  const baseUrl = await getBackendBaseUrl();
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers ?? {})
    }
  });

  if (!response.ok) {
    throw new BackendApiError(`Backend request failed with HTTP ${response.status}`);
  }

  const envelope = (await response.json()) as ResultEnvelope<TData>;
  if (!envelope.ok || envelope.data === undefined || envelope.data === null) {
    throw new BackendApiError(
      envelope.error?.message ?? "Backend returned an unsuccessful response",
      envelope.error?.code,
      envelope.warnings,
      envelope.audit_ref ?? undefined
    );
  }

  return {
    data: envelope.data,
    warnings: envelope.warnings,
    auditRef: envelope.audit_ref ?? undefined
  };
}

export function jsonRequest<TBody>(body: TBody, init?: RequestInit): RequestInit {
  return {
    ...init,
    method: init?.method ?? "POST",
    body: JSON.stringify(body)
  };
}

export async function getBackendBaseUrl(): Promise<string> {
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
