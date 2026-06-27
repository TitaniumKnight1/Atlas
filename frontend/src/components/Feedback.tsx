import type { ReactNode } from "react";

import { Button } from "./Button";

export type FeedbackSeverity = "info" | "success" | "warn" | "danger";

interface AlertProps {
  severity?: FeedbackSeverity;
  title: string;
  children: ReactNode;
}

interface ToastProps extends AlertProps {
  onDismiss?: () => void;
}

const ICONS: Record<FeedbackSeverity, string> = {
  info: "i",
  success: "ok",
  warn: "!",
  danger: "x"
};

export function Alert({ severity = "info", title, children }: AlertProps) {
  return (
    <div className={`atlas-alert atlas-alert--${severity}`} role={severity === "danger" ? "alert" : "status"}>
      <span className="atlas-alert__icon" aria-hidden="true">
        {ICONS[severity]}
      </span>
      <div>
        <h4>{title}</h4>
        <p>{children}</p>
      </div>
    </div>
  );
}

export function Toast({ severity = "info", title, children, onDismiss }: ToastProps) {
  return (
    <div className={`atlas-toast atlas-toast--${severity}`} role="status">
      <span className="atlas-toast__bar" aria-hidden="true" />
      <div>
        <h4>{title}</h4>
        <p>{children}</p>
      </div>
      {onDismiss ? (
        <Button aria-label="Dismiss" iconOnly size="sm" variant="ghost" onClick={onDismiss}>
          x
        </Button>
      ) : null}
    </div>
  );
}
