import type { ReactNode, TableHTMLAttributes } from "react";

export function Table({ children, className, ...props }: TableHTMLAttributes<HTMLTableElement>) {
  return (
    <div className="atlas-table-wrap">
      <table className={["atlas-table", className ?? ""].filter(Boolean).join(" ")} {...props}>
        {children}
      </table>
    </div>
  );
}

export function CellStack({ title, detail }: { title: ReactNode; detail?: ReactNode }) {
  return (
    <span className="atlas-stack" style={{ gap: "var(--space-1)" }}>
      <strong>{title}</strong>
      {detail ? <span className="muted-copy">{detail}</span> : null}
    </span>
  );
}
