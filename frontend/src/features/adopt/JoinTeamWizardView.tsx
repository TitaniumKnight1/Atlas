import { useCallback, useEffect, useMemo, useState } from "react";

import {
  adoptRepository,
  applyDevConfigTransform,
  applyRepoNormalization,
  applySecretSubstitution,
  dryRunAdoptRepository,
  dryRunDevConfigTransform,
  dryRunRepoNormalization,
  dryRunSecretSubstitution,
  getPathway2WizardStatus,
  previewAdoptRepository,
  previewDevConfigTransform,
  previewRepoNormalization,
  previewSecretSubstitution,
  undoPathway2Command,
  type Pathway2WizardStatus
} from "../../api/pathway2";
import type { ConfigValidationBlock } from "../../api/configValidation";
import { formatAuditRef, getProject, type ProjectDetail } from "../../api/project";
import {
  getProcessStatus,
  previewStartProcess,
  startProcess,
  stopProcess,
  type ProcessStatus
} from "../../api/setup";
import {
  Alert,
  Badge,
  Button,
  DefinitionGrid,
  Field,
  Input,
  InputGroup,
  SectionHeading,
  StatusPill,
  Surface,
  WizardStepper,
  type StatusKind,
  type WizardStepItem,
  ViewPage,
  ViewPageBody,
  ViewPageHeader,
  ViewWorkspace,
  TechnicalDetails
} from "../../components";
import { CommandPanel } from "../../components/CommandPanel";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { useProjectDirectory } from "../../components/ProjectDirectoryContext";
import { useProjectStream } from "../../components/useProjectStream";
import { PathwayChoice } from "../onboarding/PathwayChoice";
import { ConfigFindingsPanel } from "../config/ConfigFindingsPanel";
import { DevDatabasePanel } from "./DevDatabasePanel";
import {
  DevSecretsStepHero,
  DevLicenseEntryPanel,
  DevSecretEntryForm,
  InlineSecretsReport,
  Pathway2StatusBadges,
  ReturnPathPanel,
  StructureScorecardView,
  SubstitutionSlotsReport,
  WizardGateAlert
} from "./adoptPanels";

const WIZARD_STEP_DEFS = [
  { id: "adopt", label: "Clone & adopt" },
  { id: "normalize", label: "Normalize" },
  { id: "secrets", label: "Dev secrets" },
  { id: "tuning", label: "Dev tuning" },
  { id: "run", label: "Run locally" },
  { id: "return", label: "Return work" },
  { id: "done", label: "Done" }
] as const;

type LocalWizardStepId = (typeof WIZARD_STEP_DEFS)[number]["id"];

export function JoinTeamWizardView() {
  const { resource: projectsResource, projects, reload: reloadProjects } = useProjectDirectory();
  const [projectId, setProjectId] = useState<string | null>(null);
  const [wizardStatus, setWizardStatus] = useState<Pathway2WizardStatus | null>(null);
  const [statusError, setStatusError] = useState<unknown>(null);
  const [statusLoading, setStatusLoading] = useState(false);
  const [activeStep, setActiveStep] = useState<LocalWizardStepId>("adopt");

  const [rootPath, setRootPath] = useState("");
  const [remoteUrl, setRemoteUrl] = useState("");
  const [adoptPreviewValidation, setAdoptPreviewValidation] = useState<ConfigValidationBlock | null>(null);
  const [adoptValidationCheckedAt, setAdoptValidationCheckedAt] = useState<string | null>(null);
  const [wizardValidationCheckedAt, setWizardValidationCheckedAt] = useState<string | null>(null);

  useEffect(() => {
    setAdoptPreviewValidation(null);
    setAdoptValidationCheckedAt(null);
  }, [rootPath, remoteUrl]);

  const [transformHostname, setTransformHostname] = useState("[DEV] Atlas Local Server");
  const [transformMaxClients, setTransformMaxClients] = useState("8");
  const [transformPort, setTransformPort] = useState("30121");

  const [projectDetail, setProjectDetail] = useState<ProjectDetail | null>(null);
  const [fxserverPath, setFxserverPath] = useState("");
  const [serverDataPath, setServerDataPath] = useState("");
  const [txadminMode, setTxadminMode] = useState(false);
  const [processRunId, setProcessRunId] = useState<string | null>(null);
  const [processStatus, setProcessStatus] = useState<ProcessStatus | null>(null);
  const [processBusy, setProcessBusy] = useState(false);
  const [processError, setProcessError] = useState<unknown>(null);
  const [processPreviewSummary, setProcessPreviewSummary] = useState<string | null>(null);
  const [lastAuditRef, setLastAuditRef] = useState<string | null>(null);
  const [commitCompleted, setCommitCompleted] = useState(false);

  useEffect(() => {
    if (!projectId || projectsResource.state !== "ready") {
      return;
    }
    if (!projects.some((project) => project.project_id === projectId)) {
      setProjectId(null);
      setWizardStatus(null);
      setProjectDetail(null);
      setActiveStep("adopt");
    }
  }, [projectId, projects, projectsResource.state]);

  const transformOptions = useMemo(
    () => ({
      hostname: transformHostname.trim() || undefined,
      max_clients: Number.parseInt(transformMaxClients, 10) || undefined,
      udp_port: Number.parseInt(transformPort, 10) || undefined,
      tcp_port: Number.parseInt(transformPort, 10) || undefined
    }),
    [transformHostname, transformMaxClients, transformPort]
  );

  const refreshWizardStatus = useCallback(async (activeProjectId: string, options?: { syncActiveStep?: boolean }) => {
    setStatusLoading(true);
    setStatusError(null);
    try {
      const response = await getPathway2WizardStatus(activeProjectId);
      setWizardStatus(response.data);
      setWizardValidationCheckedAt(new Date().toLocaleString());
      if (options?.syncActiveStep !== false) {
        setActiveStep(response.data.wizard.active_step as LocalWizardStepId);
      }
      if (response.data.return_path?.contamination_report.gate_status === "PASS") {
        setCommitCompleted(false);
      }
    } catch (error) {
      setStatusError(error);
    } finally {
      setStatusLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!projectId) {
      return;
    }
    void refreshWizardStatus(projectId);
  }, [projectId, refreshWizardStatus]);

  useEffect(() => {
    if (!projectId) {
      setProjectDetail(null);
      return;
    }
    let cancelled = false;
    const activeProjectId = projectId;
    async function loadProject() {
      try {
        const detail = await getProject(activeProjectId);
        if (!cancelled) {
          setProjectDetail(detail);
          setServerDataPath(resolveServerDataPath(detail));
          const artifact = detail.paths.find((path) => path.path_role === "artifact_extract")?.absolute_path;
          if (artifact) {
            setFxserverPath(`${artifact}\\FXServer.exe`);
          }
        }
      } catch {
        if (!cancelled) {
          setProjectDetail(null);
        }
      }
    }
    void loadProject();
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  const { events: streamEvents, connected: streamConnected } = useProjectStream(projectId, ["server-output", "process-lifecycle"]);
  const serverLines = useMemo(
    () =>
      streamEvents
        .filter((event) => event.topic === "server-output")
        .map((event) => String(event.payload?.line ?? event.payload?.message ?? ""))
        .filter(Boolean)
        .slice(-200),
    [streamEvents]
  );

  useEffect(() => {
    if (!projectId || !processRunId) {
      return;
    }
    let cancelled = false;
    const activeProjectId = projectId;
    const activeRunId = processRunId;
    async function poll() {
      try {
        const status = await getProcessStatus(activeProjectId, activeRunId);
        if (!cancelled) {
          setProcessStatus(status);
        }
      } catch {
        /* ignore transient poll errors */
      }
    }
    void poll();
    const timer = window.setInterval(() => void poll(), 3000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [projectId, processRunId]);

  const wizardSteps: WizardStepItem[] = useMemo(() => {
    if (wizardStatus?.wizard.steps) {
      return wizardStatus.wizard.steps;
    }
    return WIZARD_STEP_DEFS.map((step, index) => ({
      id: step.id,
      label: step.label,
      status: index === 0 ? "active" : "upcoming"
    }));
  }, [wizardStatus]);

  const blockers = wizardStatus?.wizard.blockers ?? {};
  const gates = wizardStatus?.wizard.gates;
  const scorecard = wizardStatus?.structure_scorecard;
  const pathwayState = wizardStatus?.pathway2_state;

  function goToStep(step: LocalWizardStepId) {
    setActiveStep(step);
  }

  async function handlePreviewStart() {
    if (!projectId) {
      return;
    }
    setProcessError(null);
    try {
      const result = await previewStartProcess(projectId, {
        fxserver_path: fxserverPath,
        server_data_path: serverDataPath,
        txadmin_mode: txadminMode
      });
      setProcessPreviewSummary(result.data.summary);
    } catch (error) {
      setProcessError(error);
    }
  }

  async function handleStartProcess() {
    if (!projectId) {
      return;
    }
    setProcessBusy(true);
    setProcessError(null);
    try {
      const result = await startProcess(projectId, {
        fxserver_path: fxserverPath,
        server_data_path: serverDataPath,
        txadmin_mode: txadminMode
      });
      setLastAuditRef(formatAuditRef(result.auditRef) ?? null);
      const runId = String(result.data.process_run_id ?? "");
      if (runId) {
        setProcessRunId(runId);
      }
    } catch (error) {
      setProcessError(error);
    } finally {
      setProcessBusy(false);
    }
  }

  async function handleStopProcess() {
    if (!projectId || !processRunId) {
      return;
    }
    setProcessBusy(true);
    setProcessError(null);
    try {
      await stopProcess(projectId, { process_run_id: processRunId });
    } catch (error) {
      setProcessError(error);
    } finally {
      setProcessBusy(false);
    }
  }

  const processStatusKind: StatusKind = mapProcessState(processStatus?.state);

  return (
    <ViewPage>
      <ViewPageHeader>
        <SectionHeading
          eyebrow="Pathway 2"
          title="Join a team server"
          detail="Guided onboarding: adopt a team repo, normalize overlay structure, substitute dev secrets, tune local config, run under supervision, and return work safely."
        />
        {projectId ? (
          <div className="inline-actions">
            <Badge variant="info">Pathway 2</Badge>
            <Badge variant="neutral">Join team</Badge>
          </div>
        ) : null}
      </ViewPageHeader>

      <ViewPageBody className={projectId ? undefined : "view-page__body--scroll"}>
      {!projectId ? (
        <>
          <PathwayChoice current="join" />
          <div className="view-split view-split--2">
          <Surface>
            <SectionHeading title="Clone or adopt" detail="Provide a local destination and optional remote URL. Atlas clones, imports, and scores the structure." />
            <InputGroup>
              <Field label="Local destination" hint="Clone target or existing server folder (project root).">
                <Input value={rootPath} onChange={(event) => setRootPath(event.target.value)} placeholder="C:\FXServer\team-server" />
              </Field>
              <Field label="Remote URL (optional)" hint="When set, Atlas clones into the destination before import.">
                <Input value={remoteUrl} onChange={(event) => setRemoteUrl(event.target.value)} placeholder="https://github.com/org/fivem-server.git" />
              </Field>
            </InputGroup>
            <CommandPanel
              title="Adopt repository"
              description="Clone (optional), import as an Atlas project, and run config/resource discovery explicitly."
              executeLabel="Adopt repository"
              presentation="guided"
              disabled={!rootPath.trim()}
              onPreview={() => previewAdoptRepository(rootPath.trim(), remoteUrl.trim() || undefined)}
              onDryRun={() => dryRunAdoptRepository(rootPath.trim(), remoteUrl.trim() || undefined)}
              onExecute={() => adoptRepository(rootPath.trim(), remoteUrl.trim() || undefined)}
              onPreviewReady={(response) => {
                const block = response.data.preview.config_validation as ConfigValidationBlock | undefined;
                setAdoptPreviewValidation(block ?? null);
                setAdoptValidationCheckedAt(new Date().toLocaleString());
              }}
              onSuccess={async (response) => {
                const adoptedId = String(response.data.project_id ?? "");
                if (!adoptedId) {
                  return;
                }
                await reloadProjects();
                setProjectId(adoptedId);
              }}
            />
            {rootPath.trim() ? (
              <div style={{ marginTop: "var(--space-4)" }}>
                <ConfigFindingsPanel
                  compact
                  validation={adoptPreviewValidation}
                  showInlineSecretHint
                  lastCheckedAt={adoptValidationCheckedAt}
                />
              </div>
            ) : null}
          </Surface>

          {projects.length > 0 ? (
            <Surface>
              <SectionHeading title="Resume adopted project" detail="Continue where you left off — the wizard reflects existing Pathway 2 state." />
              <div className="inline-actions">
                {projects.map((project) => (
                  <Button key={project.project_id} variant="secondary" onClick={() => setProjectId(project.project_id)}>
                    {project.display_name}
                  </Button>
                ))}
              </div>
            </Surface>
          ) : (
            <Surface kind="card">
              <EmptyState detail="Adopt a repository to begin the join-team wizard." title="No adopted projects yet" />
            </Surface>
          )}
        </div>
        </>
      ) : (
        <ViewWorkspace>
        <Surface className="setup-wizard" kind="panel" padded={false}>
          <WizardStepper steps={wizardSteps} ariaLabel="Join team wizard progress" />

          {wizardStatus && pathwayState ? (
            <div className="setup-wizard__meta">
              <Pathway2StatusBadges
                normalized={pathwayState.normalized}
                secretsSubstituted={pathwayState.secrets_substituted}
                runReady={pathwayState.run_ready}
                devTransformed={pathwayState.dev_transformed}
              />
              {statusLoading ? <Badge variant="neutral">Refreshing status…</Badge> : null}
            </div>
          ) : null}

          <div className="setup-wizard__body">
            {statusLoading && !wizardStatus ? (
              <div className="wizard-step wizard-step--status">
                <LoadingState title="Loading wizard status" detail="Reading Pathway 2 state and guard rails." />
              </div>
            ) : null}
            {statusError && !wizardStatus ? (
              <div className="wizard-step wizard-step--status">
                <ErrorState error={statusError} onRetry={() => projectId && void refreshWizardStatus(projectId)} />
              </div>
            ) : null}

            {wizardStatus ? (
              <>
            {statusError ? (
              <ErrorState error={statusError} onRetry={() => projectId && void refreshWizardStatus(projectId)} />
            ) : null}
            {activeStep === "adopt" ? (
              <section className="wizard-step">
                <div className="wizard-step__content">
                  <ConfigFindingsPanel
                    compact
                    projectId={projectId ?? undefined}
                    validation={wizardStatus.config_validation ?? null}
                    showInlineSecretHint
                    lastCheckedAt={wizardValidationCheckedAt}
                  />
                  <SectionHeading title="Structure scorecard" detail="Atlas must detect a FiveM server before proceeding to normalization." />
                  {scorecard ? <StructureScorecardView compact scorecard={scorecard} /> : null}
                  {wizardStatus?.inline_secrets?.length ? <InlineSecretsReport findings={wizardStatus.inline_secrets} /> : null}
                  {!scorecard?.looks_like_fivem_server && pathwayState?.origin ? (
                    <WizardGateAlert title="Not a detected FiveM server" detail={blockers.normalize ?? "server.cfg and resources must be present."} />
                  ) : null}
                </div>
                <div className="wizard-step__footer">
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={statusLoading}
                    loading={statusLoading}
                    onClick={() => projectId && void refreshWizardStatus(projectId, { syncActiveStep: false })}
                  >
                    Re-run changes
                  </Button>
                  <Button variant="primary" disabled={!gates?.adopt} onClick={() => goToStep("normalize")}>
                    Continue to normalize
                  </Button>
                </div>
              </section>
            ) : null}

            {activeStep === "normalize" ? (
              <section className="wizard-step">
                <div className="wizard-step__content">
                  <SectionHeading
                    title="Normalize base config"
                    detail="Preview-first restructuring: placeholders in server.cfg, endpoints moved to gitignored server.cfg.local."
                  />
                  {blockers.normalize ? <WizardGateAlert title="Blocked" detail={blockers.normalize} /> : null}
                  <CommandPanel
                    title="Apply overlay structure"
                    description="Mutates server.cfg through the command contract. Undo restores the original file byte-for-byte."
                    executeLabel="Apply normalization"
                    presentation="guided"
                    onPreview={() => previewRepoNormalization(projectId)}
                    onDryRun={() => dryRunRepoNormalization(projectId)}
                    onExecute={() => applyRepoNormalization(projectId)}
                    onUndo={(commandExecutionId) => undoPathway2Command(projectId, commandExecutionId)}
                    onSuccess={() => void refreshWizardStatus(projectId)}
                    onUndoSuccess={() => void refreshWizardStatus(projectId)}
                  />
                </div>
                <div className="wizard-step__footer">
                  <Button variant="secondary" onClick={() => goToStep("adopt")}>
                    Back
                  </Button>
                  <Button variant="primary" disabled={!gates?.normalize} onClick={() => goToStep("secrets")}>
                    Continue to dev secrets
                  </Button>
                </div>
              </section>
            ) : null}

            {activeStep === "secrets" ? (
              <section className="wizard-step">
                <div className="wizard-step__content">
                  {wizardStatus.wizard.secrets_step ? (
                    <DevSecretsStepHero guidance={wizardStatus.wizard.secrets_step} />
                  ) : null}
                  {wizardStatus.wizard.secrets_step?.show_substitution_command ? (
                    <>
                      {wizardStatus.substitution_slots?.length ? (
                        <SubstitutionSlotsReport
                          slots={wizardStatus.substitution_slots}
                          unsetDevSlots={wizardStatus.unset_dev_slots ?? []}
                        />
                      ) : null}
                      <CommandPanel
                        title="Apply secret substitution"
                        description="Writes dev values and placeholders into server.cfg.local only. Production secrets stay masked in previews."
                        executeLabel="Apply substitution"
                        presentation="guided"
                        disabled={!pathwayState?.normalized}
                        onPreview={() => previewSecretSubstitution(projectId)}
                        onDryRun={() => dryRunSecretSubstitution(projectId)}
                        onExecute={() => applySecretSubstitution(projectId)}
                        onUndo={(commandExecutionId) => undoPathway2Command(projectId, commandExecutionId)}
                        onSuccess={() => void refreshWizardStatus(projectId)}
                        onUndoSuccess={() => void refreshWizardStatus(projectId)}
                      />
                    </>
                  ) : null}
                  {wizardStatus.wizard.secrets_step?.show_dev_entry_form ? (
                    <>
                      <DevLicenseEntryPanel
                        projectId={projectId}
                        unsetDevSlots={wizardStatus.unset_dev_slots ?? []}
                        onApplied={() => void refreshWizardStatus(projectId)}
                      />
                      <DevSecretEntryForm
                        projectId={projectId}
                        slots={wizardStatus.substitution_slots ?? []}
                        unsetDevSlots={wizardStatus.unset_dev_slots ?? []}
                        onApplied={() => void refreshWizardStatus(projectId)}
                      />
                    </>
                  ) : null}
                </div>
                <div className="wizard-step__footer">
                  <Button variant="secondary" onClick={() => goToStep("normalize")}>
                    Back
                  </Button>
                  <Button variant="primary" disabled={!gates?.secrets} onClick={() => goToStep("tuning")}>
                    Continue to dev tuning
                  </Button>
                </div>
              </section>
            ) : null}

            {activeStep === "tuning" ? (
              <section className="wizard-step">
                <div className="wizard-step__content">
                  <SectionHeading
                    title="Dev config transform"
                    detail="Optional but recommended: hostname, slots, ports, and dev convars in server.cfg.local only."
                  />
                  <InputGroup>
                    <Field label="Dev hostname">
                      <Input value={transformHostname} onChange={(event) => setTransformHostname(event.target.value)} />
                    </Field>
                    <Field label="Max clients">
                      <Input value={transformMaxClients} onChange={(event) => setTransformMaxClients(event.target.value)} />
                    </Field>
                    <Field label="Dev port (UDP/TCP)">
                      <Input value={transformPort} onChange={(event) => setTransformPort(event.target.value)} />
                    </Field>
                  </InputGroup>
                  <CommandPanel
                    title="Apply dev transform"
                    description="Preview shows full non-secret values. onesync uses +set at start when needed (ADR-0027)."
                    executeLabel="Apply dev transform"
                    presentation="guided"
                    onPreview={() => previewDevConfigTransform(projectId, transformOptions)}
                    onDryRun={() => dryRunDevConfigTransform(projectId, transformOptions)}
                    onExecute={() => applyDevConfigTransform(projectId, transformOptions)}
                    onUndo={(commandExecutionId) => undoPathway2Command(projectId, commandExecutionId)}
                    onSuccess={() => void refreshWizardStatus(projectId)}
                    onUndoSuccess={() => void refreshWizardStatus(projectId)}
                  />
                </div>
                <div className="wizard-step__footer">
                  <Button variant="secondary" onClick={() => goToStep("secrets")}>
                    Back
                  </Button>
                  <Button variant="primary" disabled={!pathwayState?.secrets_substituted || !gates?.run} onClick={() => goToStep("run")}>
                    Continue to run
                  </Button>
                </div>
              </section>
            ) : null}

            {activeStep === "run" ? (
              <section className="wizard-step">
                <div className="wizard-step__content">
                  <SectionHeading title="Run locally" detail="Start FXServer under Atlas supervision. Blocked until dev secrets are complete." />
                  {blockers.run || wizardStatus?.run_blocked_reason ? (
                    <WizardGateAlert
                      title="Server not ready to run"
                      detail={blockers.run ?? wizardStatus?.run_blocked_reason ?? "Complete dev secrets first."}
                    />
                  ) : null}
                  <Surface kind="card">
                    <DefinitionGrid
                      items={[
                        ["Project", projectDetail?.display_name ?? projectId],
                        ["Server-data", serverDataPath || "—"],
                        ["FXServer", fxserverPath || "—"],
                        ["Stream", streamConnected ? "Connected" : "Connecting…"]
                      ]}
                    />
                  </Surface>
                  {projectId ? (
                    <DevDatabasePanel
                      projectId={projectId}
                      serverDataPath={serverDataPath}
                      onAuditRef={(auditRef) => setLastAuditRef(auditRef)}
                    />
                  ) : null}
                  <div className="setup-form-grid">
                    <Field label="FXServer executable">
                      <Input value={fxserverPath} onChange={(event) => setFxserverPath(event.target.value)} />
                    </Field>
                    <Field label="Launch mode">
                      <select value={txadminMode ? "txadmin" : "direct"} onChange={(event) => setTxadminMode(event.target.value === "txadmin")}>
                        <option value="direct">Direct (+exec server.cfg)</option>
                        <option value="txadmin">txAdmin mode</option>
                      </select>
                    </Field>
                  </div>
                  {processPreviewSummary ? (
                    <Alert severity="info" title="Start preview">
                      {processPreviewSummary}
                    </Alert>
                  ) : null}
                  {processError ? <ErrorState error={processError} /> : null}
                  {lastAuditRef ? (
                    <Alert severity="info" title="Last audited operation">
                      {lastAuditRef}
                    </Alert>
                  ) : null}
                  <div className="atlas-row">
                    <StatusPill status={processStatusKind}>{processStatus?.state ?? "Not started"}</StatusPill>
                    {processRunId ? <Badge variant="neutral">run {processRunId.slice(0, 8)}</Badge> : null}
                  </div>
                  {serverLines.length > 0 ? (
                    <TechnicalDetails summary="Server output">
                      <pre className="command-json setup-output-log">{serverLines.join("\n")}</pre>
                    </TechnicalDetails>
                  ) : (
                    <p className="muted-copy">Server output appears here after the process starts.</p>
                  )}
                </div>
                <div className="wizard-step__footer">
                  <Button variant="secondary" onClick={() => goToStep("tuning")}>
                    Back
                  </Button>
                  <Button variant="secondary" disabled={!gates?.run} onClick={() => void handlePreviewStart()}>
                    Preview start
                  </Button>
                  <Button loading={processBusy} variant="primary" disabled={!gates?.run} onClick={() => void handleStartProcess()}>
                    Start server
                  </Button>
                  <Button disabled={!processRunId || processBusy} variant="secondary" onClick={() => void handleStopProcess()}>
                    Stop
                  </Button>
                  <Button variant="primary" disabled={!gates?.run} onClick={() => goToStep("return")}>
                    Continue to return work
                  </Button>
                </div>
              </section>
            ) : null}

            {activeStep === "return" ? (
              <section className="wizard-step">
                <div className="wizard-step__content">
                  <SectionHeading
                    title="Return path (safe commit)"
                    detail="Fail-closed secret gate on explicit paths only. Atlas commits locally; you push manually (ADR-0010)."
                  />
                  {blockers.return ? <WizardGateAlert title="Commit blocked" detail={blockers.return} /> : null}
                  <ReturnPathPanel
                    projectId={projectId}
                    initialReturnPath={wizardStatus?.return_path}
                    onStatusChange={() => {
                      setCommitCompleted(true);
                      void refreshWizardStatus(projectId);
                    }}
                  />
                </div>
                <div className="wizard-step__footer">
                  <Button variant="secondary" onClick={() => goToStep("run")}>
                    Back
                  </Button>
                  <Button variant="primary" onClick={() => goToStep("done")}>
                    Finish
                  </Button>
                </div>
              </section>
            ) : null}

            {activeStep === "done" ? (
              <section className="wizard-step">
                <div className="wizard-step__content">
                  <SectionHeading title="You're set up for local team development" detail="Summary of what Atlas prepared." />
                  <Alert severity="success" title="Pathway 2 complete">
                    <ul className="plain-list">
                      <li>Adopted team repo with overlay structure (server.cfg.local is gitignored).</li>
                      <li>Production secrets substituted — your dev values stay local and masked in previews.</li>
                      <li>Server can run locally when dev secrets are filled and the run gate passes.</li>
                      <li>Return path uses a fail-closed commit gate; push your branch manually when ready.</li>
                    </ul>
                  </Alert>
                  {wizardStatus?.return_path?.manual_push_message ? (
                    <p className="muted-text">{wizardStatus.return_path.manual_push_message}</p>
                  ) : null}
                  {commitCompleted ? <Badge variant="info">Local commit recorded</Badge> : null}
                </div>
                <div className="wizard-step__footer">
                  <Button variant="secondary" onClick={() => goToStep("return")}>
                    Back to return work
                  </Button>
                </div>
              </section>
            ) : null}
              </>
            ) : null}
          </div>
        </Surface>
        </ViewWorkspace>
      )}
      </ViewPageBody>
    </ViewPage>
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
