import type { ReactNode } from "react";

export type BadgeVariant = "success" | "warn" | "danger" | "info" | "neutral";
export type StatusKind = "running" | "idle" | "crashed" | "pending";

interface BadgeProps {
  variant?: BadgeVariant;
  dot?: boolean;
  children: ReactNode;
  className?: string;
}

interface StatusPillProps {
  status: StatusKind;
  children?: ReactNode;
  className?: string;
}

const STATUS_LABELS: Record<StatusKind, string> = {
  running: "Running",
  idle: "Idle",
  crashed: "Crashed",
  pending: "Pending approval"
};

export function Badge({ variant = "neutral", dot = false, children, className }: BadgeProps) {
  return (
    <span className={["atlas-badge", `atlas-badge--${variant}`, className ?? ""].filter(Boolean).join(" ")}>
      {dot ? <span className="atlas-badge__dot" aria-hidden="true" /> : null}
      {children}
    </span>
  );
}

export function StatusPill({ status, children, className }: StatusPillProps) {
  return (
    <span className={["atlas-status-pill", `atlas-status-pill--${status}`, className ?? ""].filter(Boolean).join(" ")}>
      <span className="atlas-status-pill__dot" aria-hidden="true" />
      {children ?? STATUS_LABELS[status]}
    </span>
  );
}
