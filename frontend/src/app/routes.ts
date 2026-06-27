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
  group: "Workspace" | "Operate";
  glyph: string;
  count?: number;
}

// To add the next slice: add its route metadata here, add a feature view in
// `frontend/src/features/<slug>/`, then switch the route's `implemented` flag
// and render it from App.tsx. Shared API/state/command components stay outside
// the feature folder.
export const featureRoutes: FeatureRoute[] = [
  {
    id: "project",
    path: "/projects",
    label: "Projects",
    summary: "Import, open, and configure local server workspaces.",
    implemented: true,
    group: "Workspace",
    glyph: "P"
  },
  {
    id: "setup",
    path: "/setup",
    label: "Setup",
    summary: "Prepare artifacts and txAdmin handoff.",
    implemented: false,
    group: "Workspace",
    glyph: "S"
  },
  {
    id: "resources",
    path: "/resources",
    label: "Resources",
    summary: "Install, update, and reason about resources.",
    implemented: false,
    group: "Workspace",
    glyph: "R"
  },
  {
    id: "git",
    path: "/git",
    label: "Git",
    summary: "Version project changes deliberately.",
    implemented: false,
    group: "Workspace",
    glyph: "G"
  },
  {
    id: "config",
    path: "/config",
    label: "Config",
    summary: "Edit and validate server configuration.",
    implemented: false,
    group: "Workspace",
    glyph: "C"
  },
  {
    id: "monitoring",
    path: "/monitoring",
    label: "Monitoring",
    summary: "Watch health, metrics, and runtime signals.",
    implemented: false,
    group: "Operate",
    glyph: "M"
  },
  {
    id: "incidents",
    path: "/incidents",
    label: "Incidents",
    summary: "Group crashes and produce explainable reports.",
    implemented: false,
    group: "Operate",
    glyph: "I"
  },
  {
    id: "automation",
    path: "/automation",
    label: "Automation",
    summary: "Build workflows with approvals and undo.",
    implemented: false,
    group: "Operate",
    glyph: "A"
  },
  {
    id: "backup",
    path: "/backup",
    label: "Backup",
    summary: "Plan backups and restores.",
    implemented: false,
    group: "Operate",
    glyph: "B"
  },
  {
    id: "plugins",
    path: "/plugins",
    label: "Plugins",
    summary: "Manage trusted extensions and capabilities.",
    implemented: false,
    group: "Operate",
    glyph: "X"
  }
];

export function normalizeRoutePath(hash: string): string {
  const path = hash.replace(/^#/, "") || "/projects";
  return featureRoutes.some((route) => route.path === path) ? path : "/projects";
}
