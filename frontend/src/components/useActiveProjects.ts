import { useCallback, useEffect, useState } from "react";

import { useProjectDirectory } from "./ProjectDirectoryContext";

export function useActiveProjects() {
  return useProjectDirectory();
}

export function useActiveProjectSelection() {
  const { resource, projects, removeProject, reload } = useProjectDirectory();
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);

  useEffect(() => {
    if (resource.state !== "ready") {
      return;
    }
    if (!selectedProjectId && projects.length > 0) {
      setSelectedProjectId(projects[0].project_id);
    }
    if (selectedProjectId && !projects.some((project) => project.project_id === selectedProjectId)) {
      setSelectedProjectId(projects[0]?.project_id ?? null);
    }
  }, [projects, resource.state, selectedProjectId]);

  const removeSelectedProject = useCallback(
    async (projectId: string) => {
      const remaining = projects.filter((project) => project.project_id !== projectId);
      await removeProject(projectId);
      if (selectedProjectId === projectId) {
        setSelectedProjectId(remaining[0]?.project_id ?? null);
      }
    },
    [projects, removeProject, selectedProjectId]
  );

  return {
    resource,
    projects,
    selectedProjectId,
    setSelectedProjectId,
    removeProject: removeSelectedProject,
    reload
  };
}
