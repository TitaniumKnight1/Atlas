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
import {
  Badge,
  Button,
  CellStack,
  DefinitionGrid,
  Field,
  Input,
  InputGroup,
  SectionHeading,
  StatusPill,
  Surface,
  Table,
  ViewPage,
  ViewPageBody,
  ViewPageHeader,
  ViewWorkspace
} from "../../components";
import { CommandPanel } from "../../components/CommandPanel";
import { EmptyState, ErrorState, LoadingState, OnboardingEmptyState } from "../../components/StateViews";
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
    <ViewPage>
      <ViewPageHeader>
        <SectionHeading
          detail="Projects are local metadata over your server paths. Atlas previews commands first, then writes through the backend command rail."
          eyebrow="Project context"
          title="Choose the workspace Atlas controls"
        />
      </ViewPageHeader>

      <ViewPageBody>
      <ViewWorkspace>
      <Surface className="project-layout" kind="panel" padded={false}>
        <section className="project-sidebar">
          <SectionHeading detail="Persisted local workspaces." title="Projects" />

          {projectsResource.state === "loading" ? <LoadingState title="Loading projects" detail="Reading project metadata." /> : null}
          {projectsResource.state === "error" ? <ErrorState error={projectsResource.error} /> : null}
          {projectsResource.state === "ready" && projects.length === 0 ? (
            <section className="project-sidebar-empty atlas-card">
              <span className="atlas-status-pill atlas-status-pill--pending">
                <span className="atlas-status-pill__dot" aria-hidden="true" />
                No projects yet
              </span>
              <p className="muted-copy">Use the import form on the right to add your first workspace.</p>
            </section>
          ) : null}

          <div className="project-list">
            {projects.map((project) => (
              <button
                className={project.project_id === selectedProjectId ? "project-card project-card--active" : "project-card"}
                key={project.project_id}
                type="button"
                onClick={() => setSelectedProjectId(project.project_id)}
              >
                <span>
                  <strong>{project.display_name}</strong>
                  <small>{project.slug}</small>
                </span>
                <StatusPill status={project.status.toLowerCase() === "open" ? "running" : "idle"}>{project.status}</StatusPill>
              </button>
            ))}
          </div>
        </section>

        <section className="project-main">
          <Surface as="section" className="import-card" kind="card">
            <Field hint="Paste a local FiveM server folder. Atlas previews before persisting metadata." label="Project root path">
              <InputGroup>
                <span className="muted-copy" aria-hidden="true">
                  path
                </span>
                <Input
                  id="project-root-path"
                  value={importPath}
                  onChange={(event) => setImportPath(event.target.value)}
                  placeholder="C:\\servers\\fivem-local"
                />
              </InputGroup>
            </Field>
            <div style={{ marginTop: "var(--space-4)" }}>
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
          </Surface>

          {workspace.state === "empty" && projects.length > 0 ? (
            <EmptyState title="Select a project" detail="Project settings and environments appear after a workspace is selected." />
          ) : null}
          {projectsResource.state === "ready" && projects.length === 0 ? (
            <OnboardingEmptyState
              primaryAction={
                <Button variant="primary" onClick={() => document.getElementById("project-root-path")?.focus()}>
                  Import existing server
                </Button>
              }
            />
          ) : null}
          {workspace.state === "loading" ? <LoadingState title="Loading project" detail="Collecting paths, settings, and environments." /> : null}
          {workspace.state === "error" ? <ErrorState error={workspace.error} /> : null}

          {workspace.state === "ready" && selectedProject ? (
            <div className="workspace-grid">
              <Surface as="section" className="workspace-panel workspace-panel--wide" kind="card">
                <div className="atlas-row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
                  <SectionHeading
                    detail={`${workspace.detail.paths.length} tracked path references. No files are read directly by the UI.`}
                    eyebrow="Opened workspace"
                    title={workspace.detail.display_name}
                  />
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={async () => {
                      const result = await openProject(workspace.detail.project_id);
                      setLastMutation(result.data.command_execution_id);
                    }}
                  >
                    Open project
                  </Button>
                </div>
                <DefinitionGrid items={workspace.detail.paths.map((path) => [path.path_role, path.absolute_path] as [string, string])} />
              </Surface>

              <Surface as="section" className="workspace-panel" kind="card">
                <SectionHeading detail="Patch project metadata through audited commands." title="Settings" />
                <div className="atlas-grid atlas-grid--2">
                  <Field label="Setting key">
                    <Input value={settingKey} onChange={(event) => setSettingKey(event.target.value)} />
                  </Field>
                  <Field label="Value">
                    <Input value={settingValue} onChange={(event) => setSettingValue(event.target.value)} />
                  </Field>
                </div>
                <div className="atlas-row">
                  <Button
                    type="button"
                    variant="primary"
                    disabled={!settingKey.trim()}
                    onClick={async () => {
                      const result = await updateProjectSettings(workspace.detail.project_id, {
                        settings_patch: { [settingKey]: settingValue }
                      });
                      setLastMutation(result.data.command_execution_id);
                    }}
                  >
                    Update settings
                  </Button>
                  <Badge variant="neutral">Audited</Badge>
                </div>
                <pre>{JSON.stringify(workspace.settings.settings, null, 2)}</pre>
              </Surface>

              <Surface as="section" className="workspace-panel" kind="card">
                <div className="atlas-row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
                  <SectionHeading
                    detail={streamConnected ? "Listening on the multiplexed SSE stream." : "Waiting for the local stream connection."}
                    title="Live server output"
                  />
                  <StatusPill status={streamConnected ? "running" : "idle"}>{streamConnected ? "Connected" : "Waiting"}</StatusPill>
                </div>
                {serverLines.length === 0 ? (
                  <p className="muted-copy">Server stdout/stderr lines appear here when a supervised process is running.</p>
                ) : (
                  <pre className="live-stream-log">{serverLines.join("\n")}</pre>
                )}
              </Surface>

              <Surface as="section" className="workspace-panel" kind="card">
                <SectionHeading detail="Create local profiles for later setup and automation modules." title="Environments" />
                <div className="atlas-grid atlas-grid--2">
                  <Field label="Name">
                    <Input value={environmentName} onChange={(event) => setEnvironmentName(event.target.value)} />
                  </Field>
                  <Field label="Display name">
                    <Input value={environmentDisplayName} onChange={(event) => setEnvironmentDisplayName(event.target.value)} />
                  </Field>
                </div>
                <Button
                  type="button"
                  variant="primary"
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
                </Button>
                {workspace.environments.length > 0 ? (
                  <Table>
                    <thead>
                      <tr>
                        <th>Environment</th>
                        <th>Channel</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {workspace.environments.map((environment) => (
                        <tr key={environment.environment_id}>
                          <td>
                            <CellStack title={environment.display_name} detail={environment.name} />
                          </td>
                          <td>{environment.artifact_channel ?? "Not set"}</td>
                          <td>
                            <Badge variant={environment.is_default ? "info" : "neutral"}>{environment.is_default ? "Default" : "Profile"}</Badge>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                ) : (
                  <EmptyState title="No environment profiles" detail="Create a local, staging, or production profile to prepare for setup automation." />
                )}
              </Surface>
            </div>
          ) : null}
        </section>
      </Surface>
      </ViewWorkspace>
      </ViewPageBody>
    </ViewPage>
  );
}
