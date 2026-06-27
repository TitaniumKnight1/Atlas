import type { ReactNode } from "react";

interface TooltipProps {
  content: ReactNode;
  children: ReactNode;
}

export function Tooltip({ content, children }: TooltipProps) {
  return (
    <span className="atlas-tooltip">
      {children}
      <span className="atlas-tooltip__bubble" role="tooltip">
        {content}
      </span>
    </span>
  );
}
