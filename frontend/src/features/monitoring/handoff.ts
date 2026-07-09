export const MONITORING_HANDOFF_PROJECT_KEY = "atlas.monitoring.handoffProjectId";

/** Stash project id so Monitoring can select it and start collection after wizard Done. */
export function stashMonitoringHandoffProjectId(projectId: string): void {
  sessionStorage.setItem(MONITORING_HANDOFF_PROJECT_KEY, projectId);
}

export function consumeMonitoringHandoffProjectId(): string | null {
  const projectId = sessionStorage.getItem(MONITORING_HANDOFF_PROJECT_KEY);
  if (projectId) {
    sessionStorage.removeItem(MONITORING_HANDOFF_PROJECT_KEY);
  }
  return projectId;
}
