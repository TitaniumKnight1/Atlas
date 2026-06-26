import { useEffect, useMemo, useState } from "react";

import {
  createEnvironmentProfile,
  dryRunImportProject,
  getProject,
  getProjectSettings,
  importProject,
  listEnvironmentProfiles,
  listProjects,
  openProject,
  previewImportProject,
  undoCommandExecution,
  updateProjectSettings,
  type EnvironmentProfile,
  type ProjectDetail,
  type ProjectSummary,
  type SettingsData
} from "../../api/project";
import { CommandPanel } from "../../components/CommandPanel";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { useAsyncTask } from "../../components/useAsyncTask";
import { useProjectStream } from "../../components/useProjectStream";

type ProjectWorkspace =
  | { state: "empty" }
  | { state: "loading" }
  | {
      state: "ready";
      detail: ProjectDetail;
      settings: SettingsData;
      environments: EnvironmentProfile[];
    }
  | { state: "error"; error: unknown };

export function ProjectView() {
  const { resource: projectsResource, reload: reloadProjects } = useAsyncTask<ProjectSummary[]>(listProjects, []);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [workspace, setWorkspace] = useState<ProjectWorkspace>({ state: "empty" });
  const [importPath, setImportPath] = useState("");
  const [settingKey, setSettingKey] = useState("server.name");
  const [settingValue, setSettingValue] = useState("");
  const [environmentName, setEnvironmentName] = useState("local");
  const [environmentDisplayName, setEnvironmentDisplayName] = useState("Local");
  const [lastMutation, setLastMutation] = useState<string | null>(null);

  const projects = projectsResource.state === "ready" ? projectsResource.data : [];

  useEffect(() => {
    if (!selectedProjectId && projects.length > 0) {
      setSelectedProjectId(projects[0].project_id);
    }
  }, [projects, selectedProjectId]);

  useEffect(() => {
    if (!selectedProjectId) {
      setWorkspace({ state: "empty" });
      return;
    }

    const projectId = selectedProjectId;
    let cancelled = false;
    async function loadWorkspace() {
      setWorkspace({ state: "loading" });
      try {
        const [detail, settings, environments] = await Promise.all([
          getProject(projectId),
          getProjectSettings(projectId),
          listEnvironmentProfiles(projectId)
        ]);
        if (!cancelled) {
          setWorkspace({ state: "ready", detail, settings, environments });
        }
      } catch (error) {
        if (!cancelled) {
          setWorkspace({ state: "error", error });
        }
      }
    }

    void loadWorkspace();
    return () => {
      cancelled = true;
    };
  }, [selectedProjectId, lastMutation]);

  async function refreshAfterMutation(projectId?: string) {
    await reloadProjects();
    if (projectId) {
      setSelectedProjectId(projectId);
    }
    setLastMutation(String(Date.now()));
  }

  const selectedProject = useMemo(
    () => projects.find((project) => project.project_id === selectedProjectId) ?? null,
    [projects, selectedProjectId]
  );
  const { events: streamEvents, connected: streamConnected } = useProjectStream(selectedProjectId, ["server-output"]);
  const serverLines = useMemo(
    () =>
      streamEvents
        .filter((event) => event.topic === "server-output")
        .map((event) => String(event.payload.line ?? ""))
        .filter(Boolean)
        .slice(-12),
    [streamEvents]
  );

  return (
    <div className="feature-page">
      <header className="feature-header">
        <div>
          <p className="eyebrow">Project context</p>
          <h2>Choose the workspace Atlas controls</h2>
          <p>
            Projects are local metadata over your server paths. Atlas previews commands first, then writes through the
            backend command rail.
          </p>
        </div>
      </header>

      <div className="project-layout">
        <section className="project-sidebar">
          <div className="section-heading">
            <h2>Projects</h2>
            <p>Persisted local workspaces.</p>
          </div>

          {projectsResource.state === "loading" ? <LoadingState title="Loading projects" detail="Reading project metadata." /> : null}
          {projectsResource.state === "error" ? <ErrorState error={projectsResource.error} /> : null}
          {projectsResource.state === "ready" && projects.length === 0 ? (
            <EmptyState title="No projects yet" detail="Import a local server path to create the first workspace." />
          ) : null}

          <div className="project-list">
            {projects.map((project) => (
              <button
                className={project.project_id === selectedProjectId ? "project-card project-card--active" : "project-card"}
                key={project.project_id}
                type="button"
                onClick={() => setSelectedProjectId(project.project_id)}
              >
                <strong>{project.display_name}</strong>
                <span>{project.status}</span>
                <small>{project.slug}</small>
              </button>
            ))}
          </div>
        </section>

        <section className="project-main">
          <div className="import-card">
            <label className="field">
              <span>Project root path</span>
              <input
                value={importPath}
                onChange={(event) => setImportPath(event.target.value)}
                placeholder="C:\\servers\\fivem-local"
              />
            </label>
            <CommandPanel
              title="Import project"
              description="Preview detected paths, dry-run validation, then persist project metadata."
              executeLabel="Import"
              disabled={!importPath.trim()}
              onPreview={() => previewImportProject(importPath)}
              onDryRun={() => dryRunImportProject(importPath)}
              onExecute={() => importProject({ root_path: importPath })}
              onUndo={(commandExecutionId) => undoCommandExecution(commandExecutionId)}
              onSuccess={(result) => void refreshAfterMutation(String(result.data.project_id ?? ""))}
              onUndoSuccess={() => void refreshAfterMutation()}
            />
          </div>

          {workspace.state === "empty" ? (
            <EmptyState title="Select a project" detail="Project settings and environments appear after a workspace is selected." />
          ) : null}
          {workspace.state === "loading" ? <LoadingState title="Loading project" detail="Collecting paths, settings, and environments." /> : null}
          {workspace.state === "error" ? <ErrorState error={workspace.error} /> : null}

          {workspace.state === "ready" && selectedProject ? (
            <div className="workspace-grid">
              <section className="workspace-panel workspace-panel--wide">
                <div className="section-heading">
                  <p className="eyebrow">Opened workspace</p>
                  <h2>{workspace.detail.display_name}</h2>
                  <p>{workspace.detail.paths.length} tracked path references. No files are read directly by the UI.</p>
                </div>
                <button
                  className="button button--secondary"
                  type="button"
                  onClick={async () => {
                    const result = await openProject(workspace.detail.project_id);
                    setLastMutation(result.data.command_execution_id);
                  }}
                >
                  Open project
                </button>
                <dl className="definition-grid">
                  {workspace.detail.paths.map((path) => (
                    <div key={path.project_path_id}>
                      <dt>{path.path_role}</dt>
                      <dd>{path.absolute_path}</dd>
                    </div>
                  ))}
                </dl>
              </section>

              <section className="workspace-panel">
                <div className="section-heading">
                  <h2>Settings</h2>
                  <p>Patch project metadata through audited commands.</p>
                </div>
                <label className="field">
                  <span>Setting key</span>
                  <input value={settingKey} onChange={(event) => setSettingKey(event.target.value)} />
                </label>
                <label className="field">
                  <span>Value</span>
                  <input value={settingValue} onChange={(event) => setSettingValue(event.target.value)} />
                </label>
                <button
                  className="button"
                  type="button"
                  disabled={!settingKey.trim()}
                  onClick={async () => {
                    const result = await updateProjectSettings(workspace.detail.project_id, {
                      settings_patch: { [settingKey]: settingValue }
                    });
                    setLastMutation(result.data.command_execution_id);
                  }}
                >
                  Update settings
                </button>
                <pre>{JSON.stringify(workspace.settings.settings, null, 2)}</pre>
              </section>

              <section className="workspace-panel">
                <div className="section-heading">
                  <h2>Live server output</h2>
                  <p>{streamConnected ? "Listening on the multiplexed SSE stream." : "Waiting for the local stream connection."}</p>
                </div>
                {serverLines.length === 0 ? (
                  <p className="muted-copy">Server stdout/stderr lines appear here when a supervised process is running.</p>
                ) : (
                  <pre className="live-stream-log">{serverLines.join("\n")}</pre>
                )}
              </section>

              <section className="workspace-panel">
                <div className="section-heading">
                  <h2>Environments</h2>
                  <p>Create local profiles for later setup and automation modules.</p>
                </div>
                <label className="field">
                  <span>Name</span>
                  <input value={environmentName} onChange={(event) => setEnvironmentName(event.target.value)} />
                </label>
                <label className="field">
                  <span>Display name</span>
                  <input value={environmentDisplayName} onChange={(event) => setEnvironmentDisplayName(event.target.value)} />
                </label>
                <button
                  className="button"
                  type="button"
                  disabled={!environmentName.trim()}
                  onClick={async () => {
                    const result = await createEnvironmentProfile(workspace.detail.project_id, {
                      name: environmentName,
                      display_name: environmentDisplayName,
                      settings: { profile: environmentName },
                      is_default: workspace.environments.length === 0
                    });
                    setLastMutation(result.data.command_execution_id);
                  }}
                >
                  Create profile
                </button>
                <div className="environment-list">
                  {workspace.environments.map((environment) => (
                    <article className="environment-item" key={environment.environment_id}>
                      <strong>{environment.display_name}</strong>
                      <span>{environment.name}</span>
                      <small>{environment.is_default ? "Default" : "Profile"}</small>
                    </article>
                  ))}
                </div>
              </section>
            </div>
          ) : null}
        </section>
      </div>
    </div>
  );
}
