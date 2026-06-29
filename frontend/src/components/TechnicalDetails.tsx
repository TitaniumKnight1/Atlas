import type { ReactNode } from "react";

interface TechnicalDetailsProps {
  summary?: string;
  children: ReactNode;
  className?: string;
}

/** Collapsed-by-default disclosure for raw payloads — honesty without leading with debug output. */
export function TechnicalDetails({
  summary = "Technical details",
  children,
  className
}: TechnicalDetailsProps) {
  return (
    <details className={["atlas-disclosure", className].filter(Boolean).join(" ")}>
      <summary className="atlas-disclosure__summary">{summary}</summary>
      <div className="atlas-disclosure__body">{children}</div>
    </details>
  );
}
