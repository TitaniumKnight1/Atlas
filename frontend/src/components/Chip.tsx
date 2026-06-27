import type { ButtonHTMLAttributes, ReactNode } from "react";

interface ChipProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  active?: boolean;
  count?: number | string;
  children: ReactNode;
}

export function Chip({ active = false, count, children, className, ...props }: ChipProps) {
  return (
    <button
      className={[
        "atlas-chip",
        "atlas-chip--button",
        active ? "atlas-chip--active" : "",
        className ?? ""
      ]
        .filter(Boolean)
        .join(" ")}
      type="button"
      {...props}
    >
      {children}
      {count !== undefined ? <span className="atlas-chip__count">{count}</span> : null}
    </button>
  );
}
