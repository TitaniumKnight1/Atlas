export type FeatureRouteId =
  | "project"
  | "setup"
  | "resources"
  | "git"
  | "config"
  | "backup"
  | "monitoring"
  | "incidents"
  | "automation"
  | "plugins";

export interface FeatureRoute {
  id: FeatureRouteId;
  path: string;
  label: string;
  summary: string;
  implemented: boolean;
}

// To add the next slice: add its route metadata here, add a feature view in
// `frontend/src/features/<slug>/`, then switch the route's `implemented` flag
// and render it from App.tsx. Shared API/state/command components stay outside
// the feature folder.
export const featureRoutes: FeatureRoute[] = [
  { id: "project", path: "/projects", label: "Projects", summary: "Import, open, and configure local server workspaces.", implemented: true },
  { id: "setup", path: "/setup", label: "Setup", summary: "Prepare artifacts and txAdmin handoff.", implemented: false },
  { id: "resources", path: "/resources", label: "Resources", summary: "Install, update, and reason about resources.", implemented: false },
  { id: "git", path: "/git", label: "Git", summary: "Version project changes deliberately.", implemented: false },
  { id: "config", path: "/config", label: "Config", summary: "Edit and validate server configuration.", implemented: false },
  { id: "backup", path: "/backup", label: "Backup", summary: "Plan backups and restores.", implemented: false },
  { id: "monitoring", path: "/monitoring", label: "Monitoring", summary: "Watch health, metrics, and runtime signals.", implemented: false },
  { id: "incidents", path: "/incidents", label: "Incidents", summary: "Group crashes and produce explainable reports.", implemented: false },
  { id: "automation", path: "/automation", label: "Automation", summary: "Build workflows with approvals and undo.", implemented: false },
  { id: "plugins", path: "/plugins", label: "Plugins", summary: "Manage trusted extensions and capabilities.", implemented: false }
];

export function normalizeRoutePath(hash: string): string {
  const path = hash.replace(/^#/, "") || "/projects";
  return featureRoutes.some((route) => route.path === path) ? path : "/projects";
}
