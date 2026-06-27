import { BackendApiError } from "../api/backend";
import type { ReactNode } from "react";

import { Button } from "./Button";

interface LoadingStateProps {
  title?: string;
  detail?: string;
  rows?: number;
}

interface ErrorStateProps {
  error: unknown;
  action?: string;
  onRetry?: () => void;
}

interface EmptyStateProps {
  title: string;
  detail: string;
  action?: ReactNode;
  icon?: ReactNode;
}

export function LoadingState({ title = "Loading", detail = "Reading the local backend state.", rows = 4 }: LoadingStateProps) {
  return (
    <section className="atlas-card atlas-pad" aria-live="polite">
      <div className="atlas-stack">
        <div className="atlas-row">
          <span className="atlas-status-pill atlas-status-pill--pending">
            <span className="atlas-status-pill__dot" aria-hidden="true" />
            {title}
          </span>
          <p className="muted-copy">{detail}</p>
        </div>
        <div className="atlas-stack" aria-hidden="true">
          {Array.from({ length: rows }, (_, index) => (
            <span className="atlas-skeleton" key={index} style={{ width: `${92 - index * 12}%` }} />
          ))}
        </div>
      </div>
    </section>
  );
}

export function ErrorState({ error, action, onRetry }: ErrorStateProps) {
  const normalized = normalizeError(error);
  return (
    <section className="atlas-state atlas-card" role="alert">
      <span className="atlas-state__glyph atlas-state__glyph--danger" aria-hidden="true">
        !
      </span>
      <div>
        <p className="eyebrow">{normalized.code}</p>
        <h2>{normalized.message}</h2>
        <p>{action ?? "Check the input, confirm the local backend is running, then try the command again."}</p>
        {onRetry ? (
          <div className="atlas-state__actions">
            <Button variant="secondary" onClick={onRetry}>
              Retry
            </Button>
          </div>
        ) : null}
      </div>
    </section>
  );
}

export function EmptyState({ title, detail, action, icon = "P" }: EmptyStateProps) {
  return (
    <section className="atlas-state atlas-card">
      <span className="atlas-state__glyph" aria-hidden="true">
        {icon}
      </span>
      <div>
        <h2>{title}</h2>
        <p>{detail}</p>
        {action ? <div className="atlas-state__actions">{action}</div> : null}
      </div>
    </section>
  );
}

interface OnboardingEmptyStateProps {
  title?: string;
  detail?: string;
  primaryAction?: ReactNode;
  secondaryAction?: ReactNode;
}

export function OnboardingEmptyState({
  title = "Let's stand up your first server",
  detail = "Atlas manages setup, resources, config, monitoring, incidents, automation, backups, and plugins. Start by importing an existing server or creating a new project.",
  primaryAction,
  secondaryAction
}: OnboardingEmptyStateProps) {
  return (
    <section className="atlas-onboarding">
      <div className="atlas-onboarding__main">
        <p className="eyebrow">Welcome to Atlas</p>
        <h2>{title}</h2>
        <p>{detail}</p>
        {primaryAction || secondaryAction ? (
          <div className="atlas-row" style={{ marginTop: "var(--space-5)" }}>
            {primaryAction}
            {secondaryAction}
          </div>
        ) : null}
        <div className="atlas-step-list">
          <div className="atlas-step-list__item">
            <span className="atlas-step-list__num">1</span>
            <span>Point Atlas at a server folder or start from setup artifacts.</span>
          </div>
          <div className="atlas-step-list__item">
            <span className="atlas-step-list__num">2</span>
            <span>Preview detected paths, settings, and dependencies before writes.</span>
          </div>
          <div className="atlas-step-list__item">
            <span className="atlas-step-list__num">3</span>
            <span>Execute through the command rail with audit and undo support.</span>
          </div>
        </div>
      </div>
      <aside className="atlas-onboarding__aside">
        <span className="atlas-status-pill atlas-status-pill--pending">
          <span className="atlas-status-pill__dot" aria-hidden="true" />
          No projects yet
        </span>
        <p className="muted-copy">
          Everything Atlas does is previewable and undoable, so the first-run path should feel inviting instead of blank.
        </p>
      </aside>
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
