import type { HTMLAttributes, ReactNode } from "react";

/**
 * View layout convention (pairs with App.css shell + view-page classes):
 *
 * - ViewPage fills shell-main height; header stays compact; body scrolls internally.
 * - ViewWorkspace + project-layout: sidebar + scrollable main on wide viewports.
 * - view-split--2 (on ViewPageBody): two panels side-by-side from 1100px up.
 */
type ViewPageProps = HTMLAttributes<HTMLDivElement> & { children: ReactNode };

export function ViewPage({ children, className, ...props }: ViewPageProps) {
  return (
    <div className={["view-page", className].filter(Boolean).join(" ")} {...props}>
      {children}
    </div>
  );
}

export function ViewPageHeader({ children, className, ...props }: ViewPageProps) {
  return (
    <header className={["view-page__header", "atlas-panel", className].filter(Boolean).join(" ")} {...props}>
      {children}
    </header>
  );
}

export function ViewPageBody({ children, className, ...props }: ViewPageProps) {
  return (
    <div className={["view-page__body", className].filter(Boolean).join(" ")} {...props}>
      {children}
    </div>
  );
}

/** Flex child that grows to fill remaining view height (use inside ViewPageBody). */
export function ViewWorkspace({ children, className, ...props }: ViewPageProps) {
  return (
    <div className={["view-workspace", className].filter(Boolean).join(" ")} {...props}>
      {children}
    </div>
  );
}
