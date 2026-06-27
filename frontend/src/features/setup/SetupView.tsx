import { useCallback, useEffect, useMemo, useState } from "react";

import {
  dryRunInstallArtifact,
  dryRunServerConfig,
  getProcessStatus,
  installArtifact,
  listArtifacts,
  listDependencyChecks,
  pinArtifactVersion,
  prepareDatabase,
  previewInstallArtifact,
  previewServerConfig,
  previewStartProcess,
  refreshArtifactCatalog,
  restartProcess,
  runDependencyChecks,
  startProcess,
  stopProcess,
  writeServerConfig,
  type ArtifactVersion,
  type DependencyCheck,
  type ProcessStatus
} from "../../api/setup";
import { formatAuditRef, getProject, listProjects, undoCommandExecution, type ProjectDetail, type ProjectSummary } from "../../api/project";
import {
  Alert,
  Badge,
  Button,
  DefinitionGrid,
  Field,
  Input,
  ProgressBar,
  SectionHeading,
  Select,
  StatusPill,
  Surface,
  WizardStepper,
  type StatusKind,
  type WizardStepItem
} from "../../components";
import { CommandPanel } from "../../components/CommandPanel";
import { EmptyState, ErrorState, LoadingState, OnboardingEmptyState } from "../../components/StateViews";
import { useAsyncTask } from "../../components/useAsyncTask";
import { useProjectStream } from "../../components/useProjectStream";

const WIZARD_STEP_DEFS = [
  { id: "project", label: "Project" },
  { id: "artifact", label: "Artifact" },
  { id: "install", label: "Install" },
  { id: "config", label: "server.cfg" },
  { id: "dependencies", label: "Dependencies" },
  { id: "database", label: "Database" },
  { id: "validate", label: "Validate" }
] as const;

type WizardStepId = (typeof WIZARD_STEP_DEFS)[number]["id"];

interface SetupDraft {
  platform: string;
  channel: string;
  buildNumber: string;
  serverDataPath: string;
  fxserverPath: string;
  extractPath: string;
  hostname: string;
  projectName: string;
  maxClients: string;
  licenseKey: string;
  txadminMode: boolean;
  databaseName: string;
}

const DEFAULT_DRAFT: SetupDraft = {
  platform: "windows",
  channel: "recommended",
  buildNumber: "",
  serverDataPath: "",
  fxserverPath: "",
  extractPath: "",
  hostname: "Atlas FiveM Server",
  projectName: "Atlas FiveM Server",
  maxClients: "48",
  licenseKey: "CHANGE_ME",
  txadminMode: false,
  databaseName: "fivem.sqlite"
};

export function SetupView() {
  const { resource: projectsResource, reload: reloadProjects } = useAsyncTask<ProjectSummary[]>(listProjects, []);
  const [activeStep, setActiveStep] = useState<WizardStepId>("project");
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [projectDetail, setProjectDetail] = useState<ProjectDetail | null>(null);
  const [projectLoading, setProjectLoading] = useState(false);
  const [projectError, setProjectError] = useState<unknown>(null);
  const [draft, setDraft] = useState<SetupDraft>(DEFAULT_DRAFT);
  const [artifacts, setArtifacts] = useState<ArtifactVersion[]>([]);
  const [artifactsLoading, setArtifactsLoading] = useState(false);
  const [artifactsError, setArtifactsError] = useState<unknown>(null);
  const [completedSteps, setCompletedSteps] = useState<Set<WizardStepId>>(() => new Set());
  const [dependencyChecks, setDependencyChecks] = useState<DependencyCheck[]>([]);
  const [dependencyBusy, setDependencyBusy] = useState(false);
  const [dependencyError, setDependencyError] = useState<unknown>(null);
  const [databaseBusy, setDatabaseBusy] = useState(false);
  const [databaseResult, setDatabaseResult] = useState<string | null>(null);
  const [databaseError, setDatabaseError] = useState<unknown>(null);
  const [processRunId, setProcessRunId] = useState<string | null>(null);
  const [processStatus, setProcessStatus] = useState<ProcessStatus | null>(null);
  const [processBusy, setProcessBusy] = useState(false);
  const [processError, setProcessError] = useState<unknown>(null);
  const [processPreviewSummary, setProcessPreviewSummary] = useState<string | null>(null);
  const [lastAuditRef, setLastAuditRef] = useState<string | null>(null);
  const [installExecuting, setInstallExecuting] = useState(false);
  const [mutationTick, setMutationTick] = useState(0);

  const projects = projectsResource.state === "ready" ? projectsResource.data : [];
  const { events: streamEvents, connected: streamConnected } = useProjectStream(selectedProjectId, [
    "op-progress",
    "server-output",
    "process-lifecycle"
  ]);

  useEffect(() => {
    if (!selectedProjectId && projects.length > 0) {
      setSelectedProjectId(projects[0].project_id);
    }
  }, [projects, selectedProjectId]);

  useEffect(() => {
    if (!selectedProjectId) {
      setProjectDetail(null);
      return;
    }

    const projectId = selectedProjectId;
    let cancelled = false;
    async function loadProject() {
      setProjectLoading(true);
      setProjectError(null);
      try {
        const detail = await getProject(projectId);
        if (!cancelled) {
          setProjectDetail(detail);
          setDraft((current) => ({
            ...current,
            serverDataPath: current.serverDataPath || resolveServerDataPath(detail),
            hostname: detail.display_name,
            projectName: detail.display_name
          }));
        }
      } catch (error) {
        if (!cancelled) {
          setProjectError(error);
        }
      } finally {
        if (!cancelled) {
          setProjectLoading(false);
        }
      }
    }

    void loadProject();
    return () => {
      cancelled = true;
    };
  }, [selectedProjectId, mutationTick]);

  const loadArtifacts = useCallback(async () => {
    setArtifactsLoading(true);
    setArtifactsError(null);
    try {
      const rows = await listArtifacts(draft.platform, draft.channel);
      setArtifacts(rows);
      if (!draft.buildNumber && rows.length > 0) {
        setDraft((current) => ({ ...current, buildNumber: rows[0].build_number }));
      }
    } catch (error) {
      setArtifactsError(error);
    } finally {
      setArtifactsLoading(false);
    }
  }, [draft.platform, draft.channel, draft.buildNumber]);

  useEffect(() => {
    if (activeStep === "artifact" || activeStep === "install") {
      void loadArtifacts();
    }
  }, [activeStep, loadArtifacts]);

  useEffect(() => {
    if (!selectedProjectId || activeStep !== "dependencies") {
      return;
    }
    void listDependencyChecks(selectedProjectId)
      .then(setDependencyChecks)
      .catch(() => setDependencyChecks([]));
  }, [selectedProjectId, activeStep, mutationTick]);

  useEffect(() => {
    if (!selectedProjectId || !processRunId) {
      return;
    }

    const projectId = selectedProjectId;
    const runId = processRunId;
    let cancelled = false;
    async function refreshStatus() {
      try {
        const status = await getProcessStatus(projectId, runId);
        if (!cancelled) {
          setProcessStatus(status);
        }
      } catch {
        if (!cancelled) {
          setProcessStatus(null);
        }
      }
    }

    void refreshStatus();
    const timer = window.setInterval(() => void refreshStatus(), 4000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [selectedProjectId, processRunId, mutationTick]);

  useEffect(() => {
    const lifecycleEvents = streamEvents.filter((event) => event.topic === "process-lifecycle");
    const lifecycle = lifecycleEvents.length > 0 ? lifecycleEvents[lifecycleEvents.length - 1] : undefined;
    if (!lifecycle || !processRunId) {
      return;
    }
    const payloadRunId = String(lifecycle.payload.process_run_id ?? "");
    if (payloadRunId && payloadRunId !== processRunId) {
      return;
    }
    if (lifecycle.event_type === "ServerStarted") {
      setProcessStatus((current) => ({ ...(current ?? emptyProcessStatus(processRunId, selectedProjectId ?? "")), state: "running" }));
    }
    if (lifecycle.event_type === "ServerStopped") {
      setProcessStatus((current) => ({ ...(current ?? emptyProcessStatus(processRunId, selectedProjectId ?? "")), state: "stopped" }));
    }
    if (lifecycle.event_type === "ServerCrashed") {
      setProcessStatus((current) => ({ ...(current ?? emptyProcessStatus(processRunId, selectedProjectId ?? "")), state: "crashed" }));
    }
  }, [streamEvents, processRunId, selectedProjectId]);

  const latestOpProgress = useMemo(() => {
    const progressEvents = streamEvents.filter((event) => event.topic === "op-progress" && event.event_type === "OperationProgress");
    return progressEvents.length > 0 ? progressEvents[progressEvents.length - 1] : undefined;
  }, [streamEvents]);

  const downloadProgress = useMemo(() => {
    if (!latestOpProgress) {
      return null;
    }
    const bytesReceived = Number(latestOpProgress.payload.bytes_received ?? 0);
    const totalBytes = Number(latestOpProgress.payload.total_bytes ?? 0);
    const message = String(latestOpProgress.payload.message ?? "Working…");
    return { bytesReceived, totalBytes, message };
  }, [latestOpProgress]);

  const serverLines = useMemo(
    () =>
      streamEvents
        .filter((event) => event.topic === "server-output")
        .map((event) => {
          const stream = String(event.payload.stream ?? "stdout");
          const line = String(event.payload.line ?? "");
          return stream === "stderr" ? `[stderr] ${line}` : line;
        })
        .filter(Boolean)
        .slice(-20),
    [streamEvents]
  );

  const wizardSteps = useMemo<WizardStepItem[]>(() => {
    const stepOrder = WIZARD_STEP_DEFS.map((step) => step.id);
    const activeIndex = stepOrder.indexOf(activeStep);
    return WIZARD_STEP_DEFS.map((step, index) => {
      let status: WizardStepItem["status"] = "upcoming";
      if (completedSteps.has(step.id)) {
        status = "complete";
      } else if (step.id === activeStep) {
        status = "active";
      } else if (index < activeIndex) {
        status = "complete";
      }
      return { id: step.id, label: step.label, status };
    });
  }, [activeStep, completedSteps]);

  const selectedProject = projects.find((project) => project.project_id === selectedProjectId) ?? null;
  const processStatusKind = mapProcessState(processStatus?.state);

  function markStepComplete(step: WizardStepId) {
    setCompletedSteps((current) => new Set([...current, step]));
  }

  function goToStep(step: WizardStepId) {
    setActiveStep(step);
  }

  function bumpMutation() {
    setMutationTick((value) => value + 1);
  }

  async function handleRefreshCatalog() {
    if (!selectedProjectId) {
      return;
    }
    setArtifactsLoading(true);
    setArtifactsError(null);
    try {
      await refreshArtifactCatalog(draft.platform, draft.channel);
      await loadArtifacts();
    } catch (error) {
      setArtifactsError(error);
    } finally {
      setArtifactsLoading(false);
    }
  }

  async function handlePinArtifact() {
    if (!selectedProjectId) {
      return;
    }
    const artifact = artifacts.find((row) => row.build_number === draft.buildNumber);
    try {
      await pinArtifactVersion(selectedProjectId, {
        artifact_version_id: artifact?.artifact_version_id ?? null,
        channel_preference: draft.channel
      });
      markStepComplete("artifact");
    } catch (error) {
      setArtifactsError(error);
    }
  }

  async function handleRunDependencyChecks() {
    if (!selectedProjectId || !draft.serverDataPath.trim()) {
      return;
    }
    setDependencyBusy(true);
    setDependencyError(null);
    try {
      const result = await runDependencyChecks(selectedProjectId, { server_data_path: draft.serverDataPath });
      setLastAuditRef(formatAuditRef(result.auditRef) ?? null);
      const checks = Array.isArray(result.data.checks) ? (result.data.checks as DependencyCheck[]) : [];
      setDependencyChecks(checks);
      markStepComplete("dependencies");
      bumpMutation();
    } catch (error) {
      setDependencyError(error);
    } finally {
      setDependencyBusy(false);
    }
  }

  async function handlePrepareDatabase() {
    if (!selectedProjectId || !draft.serverDataPath.trim()) {
      return;
    }
    setDatabaseBusy(true);
    setDatabaseError(null);
    try {
      const result = await prepareDatabase(selectedProjectId, {
        server_data_path: draft.serverDataPath,
        database_name: draft.databaseName
      });
      setLastAuditRef(formatAuditRef(result.auditRef) ?? null);
      setDatabaseResult(String(result.data.database_path ?? "Database prepared"));
      markStepComplete("database");
      bumpMutation();
    } catch (error) {
      setDatabaseError(error);
    } finally {
      setDatabaseBusy(false);
    }
  }

  async function handlePreviewStart() {
    if (!selectedProjectId) {
      return;
    }
    setProcessError(null);
    try {
      const preview = await previewStartProcess(selectedProjectId, {
        fxserver_path: draft.fxserverPath,
        server_data_path: draft.serverDataPath,
        txadmin_mode: draft.txadminMode
      });
      setProcessPreviewSummary(preview.data.summary);
    } catch (error) {
      setProcessError(error);
    }
  }

  async function handleStartProcess() {
    if (!selectedProjectId) {
      return;
    }
    setProcessBusy(true);
    setProcessError(null);
    try {
      const result = await startProcess(selectedProjectId, {
        fxserver_path: draft.fxserverPath,
        server_data_path: draft.serverDataPath,
        txadmin_mode: draft.txadminMode
      });
      setLastAuditRef(formatAuditRef(result.auditRef) ?? null);
      const runId = String(result.data.process_run_id ?? "");
      setProcessRunId(runId || null);
      setProcessStatus(result.data as unknown as ProcessStatus);
      markStepComplete("validate");
    } catch (error) {
      setProcessError(error);
    } finally {
      setProcessBusy(false);
    }
  }

  async function handleStopProcess() {
    if (!selectedProjectId || !processRunId) {
      return;
    }
    setProcessBusy(true);
    setProcessError(null);
    try {
      const result = await stopProcess(selectedProjectId, { process_run_id: processRunId });
      setLastAuditRef(formatAuditRef(result.auditRef) ?? null);
      bumpMutation();
    } catch (error) {
      setProcessError(error);
    } finally {
      setProcessBusy(false);
    }
  }

  async function handleRestartProcess() {
    if (!selectedProjectId || !processRunId) {
      return;
    }
    setProcessBusy(true);
    setProcessError(null);
    try {
      const result = await restartProcess(selectedProjectId, {
        process_run_id: processRunId,
        fxserver_path: draft.fxserverPath,
        server_data_path: draft.serverDataPath,
        txadmin_mode: draft.txadminMode
      });
      setLastAuditRef(formatAuditRef(result.auditRef) ?? null);
      const runId = String(result.data.process_run_id ?? processRunId);
      setProcessRunId(runId);
      bumpMutation();
    } catch (error) {
      setProcessError(error);
    } finally {
      setProcessBusy(false);
    }
  }

  const installRequest = {
    build_number: draft.buildNumber,
    platform: draft.platform,
    channel: draft.channel
  };

  const serverConfigRequest = {
    server_data_path: draft.serverDataPath,
    options: {
      hostname: draft.hostname,
      project_name: draft.projectName,
      max_clients: Number.parseInt(draft.maxClients, 10) || 48,
      license_key: draft.licenseKey
    }
  };

  return (
    <div className="feature-page">
      <header className="feature-header atlas-panel">
        <SectionHeading
          detail="Guided onboarding to download FXServer artifacts, generate server.cfg, run preflight checks, and start a supervised process — every write goes through the backend command rail."
          eyebrow="Setup & artifacts"
          title="Stand up your FiveM server"
        />
      </header>

      {projectsResource.state === "loading" ? <LoadingState title="Loading projects" detail="Checking for workspaces to set up." /> : null}
      {projectsResource.state === "error" ? <ErrorState error={projectsResource.error} onRetry={() => void reloadProjects()} /> : null}

      {projectsResource.state === "ready" && projects.length === 0 ? (
        <OnboardingEmptyState
          detail="Import or create a project first, then return here to download artifacts, configure server.cfg, and start FXServer under Atlas supervision."
          primaryAction={
            <Button variant="primary" onClick={() => (window.location.hash = "#/projects")}>
              Go to Projects
            </Button>
          }
          title="No server set up yet"
        />
      ) : null}

      {projects.length > 0 ? (
        <Surface className="setup-wizard" kind="panel" padded={false}>
          <WizardStepper steps={wizardSteps} />

          <div className="setup-wizard__body">
            {activeStep === "project" ? (
              <section className="setup-step">
                <SectionHeading
                  detail="Setup runs in the context of one local project workspace. Atlas reads detected paths from project metadata — you can adjust server-data and FXServer paths in later steps."
                  title="Confirm project"
                />
                {projectLoading ? <LoadingState title="Loading project" detail="Reading workspace paths." /> : null}
                {projectError ? <ErrorState error={projectError} /> : null}
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
                {projectDetail ? (
                  <Surface kind="card">
                    <DefinitionGrid
                      items={[
                        ["Project", selectedProject?.display_name ?? "—"],
                        ["Root path", findPath(projectDetail, "root") ?? "—"],
                        ["Server-data (detected)", resolveServerDataPath(projectDetail) || "Not detected — you will set this next"],
                        ["Paths tracked", String(projectDetail.paths.length)]
                      ]}
                    />
                  </Surface>
                ) : null}
                <div className="setup-step__actions">
                  <Button disabled={!selectedProjectId || projectLoading} variant="primary" onClick={() => goToStep("artifact")}>
                    Continue to artifacts
                  </Button>
                </div>
              </section>
            ) : null}

            {activeStep === "artifact" ? (
              <section className="setup-step">
                <SectionHeading
                  detail="Choose the FXServer build channel and version. Refresh the catalog from Cfx.re, then optionally pin the policy on this project before installing."
                  title="Choose artifact version"
                />
                <div className="setup-form-grid">
                  <Field label="Platform">
                    <Select value={draft.platform} onChange={(event) => setDraft((current) => ({ ...current, platform: event.target.value }))}>
                      <option value="windows">windows</option>
                      <option value="linux">linux</option>
                    </Select>
                  </Field>
                  <Field label="Channel">
                    <Select value={draft.channel} onChange={(event) => setDraft((current) => ({ ...current, channel: event.target.value }))}>
                      <option value="recommended">recommended</option>
                      <option value="optional">optional</option>
                      <option value="latest">latest</option>
                    </Select>
                  </Field>
                  <Field hint="Build number from the local artifact catalog." label="Build">
                    <Select
                      value={draft.buildNumber}
                      onChange={(event) => setDraft((current) => ({ ...current, buildNumber: event.target.value }))}
                    >
                      {artifacts.map((artifact) => (
                        <option key={artifact.artifact_version_id} value={artifact.build_number}>
                          {artifact.build_number} ({artifact.channel})
                        </option>
                      ))}
                    </Select>
                  </Field>
                </div>
                <div className="setup-step__actions">
                  <Button loading={artifactsLoading} variant="secondary" onClick={() => void handleRefreshCatalog()}>
                    Refresh catalog
                  </Button>
                  <Button disabled={!draft.buildNumber} variant="secondary" onClick={() => void handlePinArtifact()}>
                    Pin artifact policy
                  </Button>
                </div>
                {artifactsError ? <ErrorState error={artifactsError} /> : null}
                {artifactsLoading ? <LoadingState title="Loading artifacts" detail="Reading cached FXServer builds." /> : null}
                {!artifactsLoading && artifacts.length === 0 ? (
                  <Alert severity="warn" title="No artifacts cached">
                    Refresh the catalog to discover FXServer builds for your platform and channel.
                  </Alert>
                ) : null}
                {!artifactsLoading && artifacts.length > 0 ? (
                  <div className="atlas-table-wrap">
                    <table className="atlas-table">
                      <thead>
                        <tr>
                          <th>Build</th>
                          <th>Channel</th>
                          <th>Platform</th>
                          <th>SHA256</th>
                        </tr>
                      </thead>
                      <tbody>
                        {artifacts.slice(0, 8).map((artifact) => (
                          <tr key={artifact.artifact_version_id}>
                            <td>{artifact.build_number}</td>
                            <td>{artifact.channel}</td>
                            <td>{artifact.platform}</td>
                            <td>{artifact.sha256 ? `${artifact.sha256.slice(0, 12)}…` : "unverified"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : null}
                <div className="setup-step__actions">
                  <Button variant="secondary" onClick={() => goToStep("project")}>
                    Back
                  </Button>
                  <Button disabled={!draft.buildNumber} variant="primary" onClick={() => goToStep("install")}>
                    Continue to install
                  </Button>
                </div>
              </section>
            ) : null}

            {activeStep === "install" && selectedProjectId ? (
              <section className="setup-step">
                <SectionHeading
                  detail="Downloads and extracts the FXServer artifact. Checksum verification may be unavailable — Atlas verifies by successful extraction. Undo removes downloaded and extracted files."
                  title="Install FXServer artifact"
                />
                <Alert severity="info" title="Live download progress">
                  Progress streams over SSE on the <code>op-progress</code> topic while the install command runs. Keep this step open during
                  download — the HTTP request blocks until extraction completes.
                </Alert>
                {installExecuting || downloadProgress ? (
                  <ProgressBar
                    indeterminate={!downloadProgress?.totalBytes}
                    label={
                      downloadProgress
                        ? `${downloadProgress.message} — ${formatBytes(downloadProgress.bytesReceived)}${downloadProgress.totalBytes ? ` / ${formatBytes(downloadProgress.totalBytes)}` : ""}`
                        : "Waiting for download progress events…"
                    }
                    max={downloadProgress?.totalBytes ?? 100}
                    value={downloadProgress?.bytesReceived ?? 0}
                  />
                ) : null}
                {!streamConnected ? (
                  <Alert severity="warn" title="SSE not connected">
                    Live progress requires an active project stream. It will connect automatically when a project is selected.
                  </Alert>
                ) : null}
                <CommandPanel
                  description="Preview download paths, dry-run validation, then install through the audited command rail."
                  disabled={!draft.buildNumber}
                  executeLabel="Install artifact"
                  title="Install FXServer artifact"
                  onDryRun={() => dryRunInstallArtifact(selectedProjectId, installRequest)}
                  onExecute={async () => {
                    setInstallExecuting(true);
                    try {
                      return await installArtifact(selectedProjectId, installRequest);
                    } finally {
                      setInstallExecuting(false);
                    }
                  }}
                  onPreview={() => previewInstallArtifact(selectedProjectId, installRequest)}
                  onUndo={(commandExecutionId) => undoCommandExecution(commandExecutionId)}
                  onSuccess={(result) => {
                    const extractPath = String(result.data.extract_path ?? "");
                    setDraft((current) => ({
                      ...current,
                      extractPath,
                      fxserverPath: current.fxserverPath || defaultFxserverPath(extractPath, draft.platform)
                    }));
                    markStepComplete("install");
                    bumpMutation();
                  }}
                />
                <div className="setup-step__actions">
                  <Button variant="secondary" onClick={() => goToStep("artifact")}>
                    Back
                  </Button>
                  <Button variant="primary" onClick={() => goToStep("config")}>
                    Continue to server.cfg
                  </Button>
                </div>
              </section>
            ) : null}

            {activeStep === "config" && selectedProjectId ? (
              <section className="setup-step">
                <SectionHeading
                  detail="Generates a baseline server.cfg in your server-data folder. Existing files are snapshotted and restorable via undo."
                  title="Configure server.cfg basics"
                />
                <div className="setup-form-grid">
                  <Field label="Server-data path">
                    <Input
                      value={draft.serverDataPath}
                      onChange={(event) => setDraft((current) => ({ ...current, serverDataPath: event.target.value }))}
                      placeholder="C:\\servers\\fivem\\server-data"
                    />
                  </Field>
                  <Field label="Hostname">
                    <Input value={draft.hostname} onChange={(event) => setDraft((current) => ({ ...current, hostname: event.target.value }))} />
                  </Field>
                  <Field label="Project name">
                    <Input
                      value={draft.projectName}
                      onChange={(event) => setDraft((current) => ({ ...current, projectName: event.target.value }))}
                    />
                  </Field>
                  <Field label="Max clients">
                    <Input value={draft.maxClients} onChange={(event) => setDraft((current) => ({ ...current, maxClients: event.target.value }))} />
                  </Field>
                  <Field hint="Replace before going live." label="License key">
                    <Input
                      value={draft.licenseKey}
                      onChange={(event) => setDraft((current) => ({ ...current, licenseKey: event.target.value }))}
                    />
                  </Field>
                </div>
                <CommandPanel
                  description="Preview generated server.cfg content, validate with dry-run, then write through the backend."
                  disabled={!draft.serverDataPath.trim()}
                  executeLabel="Write server.cfg"
                  title="Generate server.cfg"
                  onDryRun={() => dryRunServerConfig(selectedProjectId, serverConfigRequest)}
                  onExecute={() => writeServerConfig(selectedProjectId, serverConfigRequest)}
                  onPreview={() => previewServerConfig(selectedProjectId, serverConfigRequest)}
                  onUndo={(commandExecutionId) => undoCommandExecution(commandExecutionId)}
                  onSuccess={() => {
                    markStepComplete("config");
                    bumpMutation();
                  }}
                />
                <div className="setup-step__actions">
                  <Button variant="secondary" onClick={() => goToStep("install")}>
                    Back
                  </Button>
                  <Button variant="primary" onClick={() => goToStep("dependencies")}>
                    Continue to dependencies
                  </Button>
                </div>
              </section>
            ) : null}

            {activeStep === "dependencies" && selectedProjectId ? (
              <section className="setup-step">
                <SectionHeading
                  detail="Records filesystem and config preflight checks against your server-data path. Results persist on the project for later slices."
                  title="Dependency checks"
                />
                <Alert severity="info" title="What this step does">
                  Atlas checks that server-data exists (or will be created), whether server.cfg is present, and records a deferred database
                  placeholder note. This is a mutating audit command — not a dry filesystem scan from the UI.
                </Alert>
                {dependencyError ? <ErrorState error={dependencyError} /> : null}
                <div className="setup-step__actions">
                  <Button loading={dependencyBusy} variant="primary" onClick={() => void handleRunDependencyChecks()}>
                    Run dependency checks
                  </Button>
                </div>
                {dependencyChecks.length > 0 ? (
                  <div className="atlas-table-wrap">
                    <table className="atlas-table">
                      <thead>
                        <tr>
                          <th>Check</th>
                          <th>Category</th>
                          <th>Status</th>
                          <th>Message</th>
                        </tr>
                      </thead>
                      <tbody>
                        {dependencyChecks.map((check) => (
                          <tr key={check.dependency_check_id ?? check.check_key}>
                            <td>{check.check_key}</td>
                            <td>{check.category}</td>
                            <td>{check.status}</td>
                            <td>{check.message}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <EmptyState detail="Run checks to record preflight results for this project." title="No dependency checks yet" />
                )}
                <div className="setup-step__actions">
                  <Button variant="secondary" onClick={() => goToStep("config")}>
                    Back
                  </Button>
                  <Button variant="primary" onClick={() => goToStep("database")}>
                    Continue to database
                  </Button>
                </div>
              </section>
            ) : null}

            {activeStep === "database" && selectedProjectId ? (
              <section className="setup-step">
                <SectionHeading
                  detail="Creates a local placeholder database file for setup validation. Existing database files are not modified — but if one already exists, Atlas warns that changes are not safely reversible."
                  title="Database prep"
                />
                <Alert severity="warn" title="Reversibility">
                  New placeholder files can be removed via undo. If a database file already exists at the target path, Atlas will not modify it but
                  warns that existing databases are not safely reversible through setup undo.
                </Alert>
                <Field label="Database file name">
                  <Input
                    value={draft.databaseName}
                    onChange={(event) => setDraft((current) => ({ ...current, databaseName: event.target.value }))}
                  />
                </Field>
                {databaseError ? <ErrorState error={databaseError} /> : null}
                {databaseResult ? (
                  <Alert severity="success" title="Database prepared">
                    {databaseResult}
                  </Alert>
                ) : null}
                <div className="setup-step__actions">
                  <Button loading={databaseBusy} variant="primary" onClick={() => void handlePrepareDatabase()}>
                    Prepare database placeholder
                  </Button>
                </div>
                <div className="setup-step__actions">
                  <Button variant="secondary" onClick={() => goToStep("dependencies")}>
                    Back
                  </Button>
                  <Button variant="primary" onClick={() => goToStep("validate")}>
                    Continue to validate
                  </Button>
                </div>
              </section>
            ) : null}

            {activeStep === "validate" && selectedProjectId ? (
              <section className="setup-step">
                <SectionHeading
                  detail="Review paths, start the supervised FXServer process, and tail stdout/stderr from the server-output SSE topic."
                  title="Validate & run"
                />
                <Surface kind="card">
                  <DefinitionGrid
                    items={[
                      ["Project", selectedProject?.display_name ?? "—"],
                      ["Artifact build", draft.buildNumber || "—"],
                      ["Extract path", draft.extractPath || "—"],
                      ["Server-data", draft.serverDataPath || "—"],
                      ["FXServer", draft.fxserverPath || "—"],
                      ["Stream", streamConnected ? "Connected" : "Connecting…"]
                    ]}
                  />
                </Surface>
                <div className="setup-form-grid">
                  <Field label="FXServer executable">
                    <Input
                      value={draft.fxserverPath}
                      onChange={(event) => setDraft((current) => ({ ...current, fxserverPath: event.target.value }))}
                    />
                  </Field>
                  <Field label="Launch mode">
                    <Select
                      value={draft.txadminMode ? "txadmin" : "direct"}
                      onChange={(event) => setDraft((current) => ({ ...current, txadminMode: event.target.value === "txadmin" }))}
                    >
                      <option value="direct">Direct (+exec server.cfg)</option>
                      <option value="txadmin">txAdmin mode</option>
                    </Select>
                  </Field>
                </div>
                {processPreviewSummary ? (
                  <Alert severity="info" title="Start preview">
                    {processPreviewSummary}. Stop uses terminate followed by full process-tree kill; stdin shutdown is not reliable for FXServer.
                  </Alert>
                ) : null}
                {processError ? <ErrorState error={processError} /> : null}
                {lastAuditRef ? (
                  <Alert severity="info" title="Last audited operation">
                    {lastAuditRef}
                  </Alert>
                ) : null}
                <div className="setup-step__actions">
                  <Button variant="secondary" onClick={() => void handlePreviewStart()}>
                    Preview start
                  </Button>
                  <Button loading={processBusy} variant="primary" onClick={() => void handleStartProcess()}>
                    Start server
                  </Button>
                  <Button disabled={!processRunId || processBusy} variant="secondary" onClick={() => void handleStopProcess()}>
                    Stop
                  </Button>
                  <Button disabled={!processRunId || processBusy} variant="secondary" onClick={() => void handleRestartProcess()}>
                    Restart
                  </Button>
                </div>
                <div className="atlas-row">
                  <StatusPill status={processStatusKind}>{processStatus?.state ?? "Not started"}</StatusPill>
                  {processRunId ? <Badge variant="neutral">run {processRunId.slice(0, 8)}</Badge> : null}
                  {processStatus?.pid ? <Badge variant="info">pid {processStatus.pid}</Badge> : null}
                </div>
                <Surface kind="card">
                  <SectionHeading detail="Live tail from the server-output SSE topic." title="Server output" />
                  {serverLines.length === 0 ? (
                    <p className="muted-copy">Output appears here after the process starts and emits stdout/stderr lines.</p>
                  ) : (
                    <pre className="command-json setup-output-log">{serverLines.join("\n")}</pre>
                  )}
                </Surface>
                <Alert severity="success" title="Setup complete">
                  Your workspace is prepared. Use process controls above to start FXServer under Atlas supervision, or return to Projects to manage
                  settings.
                </Alert>
                <div className="setup-step__actions">
                  <Button variant="secondary" onClick={() => goToStep("database")}>
                    Back
                  </Button>
                </div>
              </section>
            ) : null}
          </div>
        </Surface>
      ) : null}
    </div>
  );
}

function resolveServerDataPath(detail: ProjectDetail): string {
  const serverData = detail.paths.find((path) => path.path_role === "server_data");
  if (serverData) {
    return serverData.absolute_path;
  }
  const root = detail.paths.find((path) => path.path_role === "root");
  if (root) {
    return `${root.absolute_path}\\server-data`;
  }
  return "";
}

function findPath(detail: ProjectDetail, role: string): string | null {
  return detail.paths.find((path) => path.path_role === role)?.absolute_path ?? null;
}

function defaultFxserverPath(extractPath: string, platform: string): string {
  if (!extractPath) {
    return "";
  }
  return platform === "windows" ? `${extractPath}\\FXServer.exe` : `${extractPath}/run.sh`;
}

function formatBytes(value: number): string {
  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(1)} MB`;
  }
  if (value >= 1_000) {
    return `${(value / 1_000).toFixed(1)} KB`;
  }
  return `${value} B`;
}

function mapProcessState(state: string | undefined): StatusKind {
  switch ((state ?? "").toLowerCase()) {
    case "running":
      return "running";
    case "crashed":
      return "crashed";
    case "stopped":
    case "idle":
      return "idle";
    default:
      return "pending";
  }
}

function emptyProcessStatus(processRunId: string, projectId: string): ProcessStatus {
  return {
    process_run_id: processRunId,
    project_id: projectId,
    state: "pending",
    pid: null,
    started_at: null,
    stopped_at: null,
    exit_code: null,
    stdout_tail: [],
    stderr_tail: []
  };
}
