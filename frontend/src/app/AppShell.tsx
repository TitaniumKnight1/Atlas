import type { ReactNode } from "react";

import { ErrorReportingSettings } from "../components/ErrorReportingSettings";
import { StatusPill } from "../components";
import type { FeatureRouteId } from "./routes";
import { featureRoutes } from "./routes";
import type { BackendStatus } from "./useBackendStatus";
import type { ErrorReportingState } from "./useErrorReporting";

interface AppShellProps {
  activePath: string;
  activeLabel: string;
  backendStatus: BackendStatus;
  errorReporting: ErrorReportingState;
  navCounts?: Partial<Record<FeatureRouteId, number>>;
  onNavigate: (path: string) => void;
  children: ReactNode;
}

const GROUPS = ["Workspace", "Operate"] as const;

export function AppShell({ activePath, activeLabel, backendStatus, errorReporting, navCounts, onNavigate, children }: AppShellProps) {
  const countsUnavailable = backendStatus.state !== "ready";

  return (
    <div className={`atlas-shell atlas-shell--${backendStatus.state}`}>
      <aside className="shell-sidebar" aria-label="Atlas navigation">
        <div className="shell-brand">
          <span className="shell-brand__mark" aria-hidden="true" />
          <div>
            <p className="eyebrow">Atlas</p>
            <h1>Local server control</h1>
          </div>
        </div>

        <button className="project-switch" type="button">
          <span className="project-switch__avatar" aria-hidden="true" />
          <span>
            <strong>Local workspace</strong>
            <small>{backendStatus.state === "ready" ? "Backend connected" : "Counts unavailable"}</small>
          </span>
          <span className="project-switch__caret" aria-hidden="true">
            v
          </span>
        </button>

        <nav className="feature-nav" aria-label="Atlas features">
          {GROUPS.map((group) => (
            <div className="feature-nav__group" key={group}>
              <p className="feature-nav__label">{group}</p>
              {featureRoutes
                .filter((route) => route.group === group)
                .map((route) => (
                  <button
                    className={route.path === activePath ? "feature-nav__item feature-nav__item--active" : "feature-nav__item"}
                    key={route.id}
                    type="button"
                    onClick={() => onNavigate(route.path)}
                  >
                    <span className="feature-nav__glyph" aria-hidden="true">
                      {route.glyph}
                    </span>
                    <span className="feature-nav__copy">
                      <strong>{route.label}</strong>
                      <small>{route.implemented ? route.summary : "Planned foundation"}</small>
                    </span>
                    <span className={countsUnavailable ? "feature-nav__count feature-nav__count--unavailable" : "feature-nav__count"}>
                      {countsUnavailable ? "-" : navCounts?.[route.id] ?? route.count ?? ""}
                    </span>
                  </button>
                ))}
            </div>
          ))}
        </nav>

        <div className="shell-sidebar__foot">
          <ErrorReportingSettings
            available={errorReporting.preferences?.error_reporting_available ?? false}
            busy={errorReporting.loading}
            enabled={
              Boolean(
                errorReporting.preferences?.telemetry_enabled && errorReporting.preferences?.crash_reporting_enabled
              )
            }
            onChange={(enabled) => {
              void errorReporting.setErrorReportingEnabled(enabled);
            }}
          />
          <div className="shell-sidebar__foot-user">
            <span className="shell-user" aria-hidden="true">
              AT
            </span>
            <div>
              <strong>Atlas local</strong>
              <small>Review foundation</small>
            </div>
          </div>
        </div>
      </aside>

      <div className="shell-workspace">
        <header className="shell-topbar">
          <div className="shell-crumbs">
            <span>Atlas</span>
            <span aria-hidden="true">/</span>
            <strong>{activeLabel}</strong>
          </div>
          <div className="shell-command-slot" aria-label="Command search placeholder">
            <span aria-hidden="true">/</span>
            <span>Search or run a command</span>
            <kbd>Ctrl K</kbd>
          </div>
          <ShellBackendStatus status={backendStatus} />
        </header>
        <main className="shell-main">{children}</main>
      </div>
    </div>
  );
}

function ShellBackendStatus({ status }: { status: BackendStatus }) {
  if (status.state === "ready") {
    return <StatusPill status="running">Backend ready</StatusPill>;
  }
  if (status.state === "connecting") {
    return <StatusPill status="pending">Connecting</StatusPill>;
  }
  return <StatusPill status="crashed">Backend down</StatusPill>;
}
