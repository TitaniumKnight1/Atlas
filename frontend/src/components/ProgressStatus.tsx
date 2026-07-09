import type { ReactNode } from "react";

import { ProgressBar } from "./ProgressBar";
import { StatusPill, type StatusKind } from "./Badge";
import { Button } from "./Button";

export type ProgressStatusPhase = "idle" | "starting" | "waiting" | "live" | "error";

export interface ProgressStatusAction {
  label: string;
  onClick: () => void;
  loading?: boolean;
  variant?: "primary" | "secondary" | "ghost";
}

interface ProgressStatusProps {
  phase: ProgressStatusPhase;
  title: string;
  detail?: string;
  /** Optional secondary line (e.g. "Metrics stream every ~5s…") */
  hint?: string;
  statusLabel?: string;
  statusKind?: StatusKind;
  action?: ProgressStatusAction;
  secondaryAction?: ProgressStatusAction;
  children?: ReactNode;
  className?: string;
}

const PHASE_STATUS: Record<ProgressStatusPhase, StatusKind> = {
  idle: "idle",
  starting: "pending",
  waiting: "pending",
  live: "running",
  error: "crashed"
};

/**
 * Reusable progress/status surface for Operate and onboarding.
 * Communicates honest phase (off / starting / waiting / live) without empty skeletons.
 */
export function ProgressStatus({
  phase,
  title,
  detail,
  hint,
  statusLabel,
  statusKind,
  action,
  secondaryAction,
  children,
  className
}: ProgressStatusProps) {
  const pillStatus = statusKind ?? PHASE_STATUS[phase];
  const showIndeterminate = phase === "starting" || phase === "waiting";

  return (
    <div className={["atlas-progress-status", `atlas-progress-status--${phase}`, className ?? ""].filter(Boolean).join(" ")}>
      <div className="atlas-progress-status__header">
        <div className="atlas-progress-status__titles">
          <StatusPill status={pillStatus}>{statusLabel ?? title}</StatusPill>
          {detail ? <p className="atlas-progress-status__detail">{detail}</p> : null}
          {hint ? <p className="muted-copy atlas-progress-status__hint">{hint}</p> : null}
        </div>
        {action || secondaryAction ? (
          <div className="atlas-progress-status__actions">
            {secondaryAction ? (
              <Button
                variant={secondaryAction.variant ?? "secondary"}
                loading={secondaryAction.loading}
                onClick={secondaryAction.onClick}
              >
                {secondaryAction.label}
              </Button>
            ) : null}
            {action ? (
              <Button variant={action.variant ?? "primary"} loading={action.loading} onClick={action.onClick}>
                {action.label}
              </Button>
            ) : null}
          </div>
        ) : null}
      </div>
      {showIndeterminate ? (
        <ProgressBar value={0} indeterminate label={phase === "starting" ? "Starting…" : "Waiting for data…"} />
      ) : null}
      {children}
    </div>
  );
}
