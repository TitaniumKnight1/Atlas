import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react";

import { archiveProject, listProjects, type ProjectSummary } from "../api/project";

import { useAsyncTask } from "./useAsyncTask";

type AsyncResource<TData> =
  | { state: "loading"; data?: undefined; error?: undefined }
  | { state: "ready"; data: TData; error?: undefined }
  | { state: "error"; data?: undefined; error: unknown };

function isActiveProject(project: ProjectSummary): boolean {
  return project.status.toLowerCase() === "active";
}

interface ProjectDirectoryContextValue {
  resource: AsyncResource<ProjectSummary[]>;
  projects: ProjectSummary[];
  reload: () => Promise<void>;
  removeProject: (projectId: string) => Promise<void>;
}

const ProjectDirectoryContext = createContext<ProjectDirectoryContextValue | null>(null);

export function ProjectDirectoryProvider({ children }: { children: ReactNode }) {
  const { resource, reload } = useAsyncTask(listProjects, []);
  const projects = resource.state === "ready" ? resource.data.filter(isActiveProject) : [];

  const removeProject = useCallback(
    async (projectId: string) => {
      await archiveProject(projectId, "Removed from workspace list");
      await reload();
    },
    [reload]
  );

  const value = useMemo(
    () => ({
      resource,
      projects,
      reload,
      removeProject
    }),
    [resource, projects, reload, removeProject]
  );

  return <ProjectDirectoryContext.Provider value={value}>{children}</ProjectDirectoryContext.Provider>;
}

export function useProjectDirectory(): ProjectDirectoryContextValue {
  const context = useContext(ProjectDirectoryContext);
  if (context === null) {
    throw new Error("useProjectDirectory must be used within ProjectDirectoryProvider");
  }
  return context;
}
