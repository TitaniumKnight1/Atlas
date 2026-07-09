export const ADOPT_RESUME_PROJECT_KEY = "atlas.adopt.resumeProjectId";

export function stashAdoptResumeProjectId(projectId: string): void {
  sessionStorage.setItem(ADOPT_RESUME_PROJECT_KEY, projectId);
}

export function consumeAdoptResumeProjectId(): string | null {
  const projectId = sessionStorage.getItem(ADOPT_RESUME_PROJECT_KEY);
  if (projectId) {
    sessionStorage.removeItem(ADOPT_RESUME_PROJECT_KEY);
  }
  return projectId;
}
