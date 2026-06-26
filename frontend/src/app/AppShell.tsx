import type { ReactNode } from "react";

import { featureRoutes } from "./routes";

interface AppShellProps {
  activePath: string;
  onNavigate: (path: string) => void;
  children: ReactNode;
}

export function AppShell({ activePath, onNavigate, children }: AppShellProps) {
  return (
    <div className="atlas-shell">
      <aside className="shell-sidebar">
        <div className="brand-block">
          <span className="brand-mark" aria-hidden="true" />
          <div>
            <p className="eyebrow">Atlas</p>
            <h1>Local server control</h1>
          </div>
        </div>

        <nav className="feature-nav" aria-label="Atlas features">
          {featureRoutes.map((route, index) => (
            <button
              className={route.path === activePath ? "feature-nav__item feature-nav__item--active" : "feature-nav__item"}
              key={route.id}
              type="button"
              onClick={() => onNavigate(route.path)}
            >
              <span className="feature-nav__index">{String(index + 1).padStart(2, "0")}</span>
              <span>
                <strong>{route.label}</strong>
                <small>{route.implemented ? route.summary : "Planned foundation"}</small>
              </span>
            </button>
          ))}
        </nav>
      </aside>

      <main className="shell-main">{children}</main>
    </div>
  );
}
