import type { HTMLAttributes, ReactNode } from "react";

type SurfaceKind = "panel" | "card" | "well";

interface SurfaceProps extends HTMLAttributes<HTMLElement> {
  as?: "section" | "article" | "div";
  kind?: SurfaceKind;
  padded?: boolean;
  selected?: boolean;
  interactive?: boolean;
  children: ReactNode;
}

export function Surface({
  as: Component = "div",
  kind = "card",
  padded = true,
  selected = false,
  interactive = false,
  className,
  children,
  ...props
}: SurfaceProps) {
  const classes = [
    kind === "panel" ? "atlas-panel" : kind === "well" ? "atlas-well" : "atlas-card",
    padded ? "atlas-pad" : "",
    selected ? "atlas-card--selected" : "",
    interactive ? "atlas-card--interactive" : "",
    className ?? ""
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <Component className={classes} {...props}>
      {children}
    </Component>
  );
}

export function SectionHeading({ eyebrow, title, detail }: { eyebrow?: string; title: string; detail?: string }) {
  return (
    <div className="atlas-section-heading">
      {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
      <h2>{title}</h2>
      {detail ? <p>{detail}</p> : null}
    </div>
  );
}

export function DefinitionGrid({ items }: { items: Array<[string, ReactNode]> }) {
  return (
    <dl className="atlas-definition-grid">
      {items.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}
