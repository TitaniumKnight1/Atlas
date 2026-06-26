import { BackendApiError } from "../api/backend";
import type { ReactNode } from "react";

interface LoadingStateProps {
  title?: string;
  detail?: string;
}

interface ErrorStateProps {
  error: unknown;
  action?: string;
}

interface EmptyStateProps {
  title: string;
  detail: string;
  action?: ReactNode;
}

export function LoadingState({ title = "Loading", detail = "Reading the local backend state." }: LoadingStateProps) {
  return (
    <section className="state-panel" aria-live="polite">
      <span className="state-pulse" aria-hidden="true" />
      <div>
        <h2>{title}</h2>
        <p>{detail}</p>
      </div>
    </section>
  );
}

export function ErrorState({ error, action }: ErrorStateProps) {
  const normalized = normalizeError(error);
  return (
    <section className="state-panel state-panel--error" role="alert">
      <span className="state-code">{normalized.code}</span>
      <div>
        <h2>{normalized.message}</h2>
        <p>{action ?? "Check the input, then try the command again."}</p>
      </div>
    </section>
  );
}

export function EmptyState({ title, detail, action }: EmptyStateProps) {
  return (
    <section className="empty-panel">
      <h2>{title}</h2>
      <p>{detail}</p>
      {action ? <div className="empty-panel__action">{action}</div> : null}
    </section>
  );
}

function normalizeError(error: unknown): { code: string; message: string } {
  if (error instanceof BackendApiError) {
    return { code: error.code, message: error.message };
  }
  if (error instanceof Error) {
    return { code: "ClientError", message: error.message };
  }
  return { code: "Unknown", message: "Something unexpected happened." };
}
