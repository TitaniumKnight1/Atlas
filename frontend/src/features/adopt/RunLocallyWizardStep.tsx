import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { formatAuditRef } from "../../api/project";
import {
  detectFxserver,
  getProcessStatus,
  resolveServerWorkingDirectory,
  startProcess,
  stopProcess,
  validateFxserverPath,
  type ProcessStatus
} from "../../api/setup";
import type { Pathway2WizardStatus } from "../../api/pathway2";
import type { ProjectDetail } from "../../api/project";
import {
  Alert,
  Badge,
  Button,
  Field,
  Input,
  SectionHeading,
  StatusPill,
  TechnicalDetails,
  type StatusKind
} from "../../components";
import { DevDatabasePanel } from "./DevDatabasePanel";
import { WizardGateAlert } from "./adoptPanels";
import { FIVEM_SERVER_ARTIFACTS_URL, pickExecutableFile, pickFolder } from "../../lib/nativeDialog";
import { openExternalUrl } from "../../lib/openExternal";
import { humanizeProcessStartError } from "../../lib/processErrors";
import { useProjectStream } from "../../components/useProjectStream";

type LadderPhase = "detecting" | "found" | "locate" | "install";

export function RunLocallyWizardStep({
  projectId,
  projectDetail,
  wizardStatus,
  serverDataPath,
  onServerDataPathChange,
  onRefresh,
  onBack,
  onContinue
}: {
  projectId: string;
  projectDetail: ProjectDetail | null;
  wizardStatus: Pathway2WizardStatus;
  serverDataPath: string;
  onServerDataPathChange: (path: string) => void;
  onRefresh: () => void;
  onBack: () => void;
  onContinue: () => void;
}) {
  const [fxserverPath, setFxserverPath] = useState("");
  const [fxserverValidated, setFxserverValidated] = useState(false);
  const [ladderPhase, setLadderPhase] = useState<LadderPhase>("detecting");
  const [txadminMode, setTxadminMode] = useState(false);
  const [processRunId, setProcessRunId] = useState<string | null>(null);
  const [processStatus, setProcessStatus] = useState<ProcessStatus | null>(null);
  const [processBusy, setProcessBusy] = useState(false);
  const [processError, setProcessError] = useState<{ title: string; detail: string; raw?: string } | null>(null);
  const [lastAuditRef, setLastAuditRef] = useState<string | null>(null);
  const [pickerBusy, setPickerBusy] = useState(false);

  const secretsReady = Boolean(wizardStatus.wizard.gates.run);
  const blockers = wizardStatus.wizard.blockers;
  const pathwayState = wizardStatus.pathway2_state;
  const serverStartedPersisted = Boolean(pathwayState.server_started);

  const applyValidatedPath = useCallback(async (candidate: string) => {
    const response = await validateFxserverPath(projectId, candidate);
    if (response.data.valid && response.data.resolved_path) {
      setFxserverPath(response.data.resolved_path);
      setFxserverValidated(true);
      setLadderPhase("found");
      setProcessError(null);
      return true;
    }
    setFxserverValidated(false);
    setProcessError({
      title: "Invalid FXServer path",
      detail: response.data.message ?? "Select FXServer.exe from your FiveM server artifact folder."
    });
    return false;
  }, [projectId]);

  useEffect(() => {
    let cancelled = false;
    async function autoDetect() {
      setLadderPhase("detecting");
      try {
        const artifact = projectDetail?.paths.find((path) => path.path_role === "artifact_extract")?.absolute_path;
        if (artifact) {
          const candidate = `${artifact}\\FXServer.exe`;
          const valid = await applyValidatedPath(candidate);
          if (!cancelled && valid) {
            return;
          }
        }
        const response = await detectFxserver(projectId);
        if (cancelled) {
          return;
        }
        if (response.data.found && response.data.detected_path) {
          await applyValidatedPath(response.data.detected_path);
          return;
        }
        setLadderPhase("locate");
      } catch {
        if (!cancelled) {
          setLadderPhase("locate");
        }
      }
    }
    void autoDetect();
    return () => {
      cancelled = true;
    };
  }, [projectId, projectDetail, applyValidatedPath]);

  const { events: streamEvents } = useProjectStream(projectId, ["server-output", "process-lifecycle"]);
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
    if (!processRunId) {
      return;
    }
    let cancelled = false;
    const activeRunId = processRunId;
    async function poll() {
      try {
        const status = await getProcessStatus(projectId, activeRunId);
        if (!cancelled) {
          setProcessStatus(status);
          if (status.state === "running") {
            onRefresh();
          }
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
  }, [projectId, processRunId, onRefresh]);

  const processStatusKind: StatusKind = mapProcessState(processStatus?.state);
  const serverRunning = processStatus?.state === "running";
  const canContinue = serverStartedPersisted || serverRunning;
  const canStart = secretsReady && fxserverValidated && Boolean(fxserverPath.trim()) && Boolean(serverDataPath.trim());

  useEffect(() => {
    if (!projectId || !secretsReady) {
      return;
    }
    let cancelled = false;
    async function loadWorkingDirectory() {
      try {
        const response = await resolveServerWorkingDirectory(projectId);
        if (!cancelled && response.data.working_directory) {
          onServerDataPathChange(response.data.working_directory);
        }
      } catch {
        /* leave empty — user can browse; never invent server-data */
      }
    }
    void loadWorkingDirectory();
    return () => {
      cancelled = true;
    };
  }, [projectId, secretsReady, onServerDataPathChange]);

  async function handleLocateFxserver() {
    setPickerBusy(true);
    setProcessError(null);
    try {
      const picked = await pickExecutableFile("Locate FXServer.exe");
      if (!picked) {
        return;
      }
      await applyValidatedPath(picked);
    } finally {
      setPickerBusy(false);
    }
  }

  async function handleBrowseServerData() {
    setPickerBusy(true);
    try {
      const picked = await pickFolder("Choose folder containing server.cfg");
      if (picked) {
        onServerDataPathChange(picked);
      }
    } finally {
      setPickerBusy(false);
    }
  }

  async function handleStartProcess() {
    if (!canStart) {
      setProcessError({
        title: "Not ready to start",
        detail: !fxserverValidated ? "Locate FXServer.exe before starting." : "Complete the path fields above."
      });
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
      onRefresh();
    } catch (error) {
      setProcessError(humanizeProcessStartError(error));
    } finally {
      setProcessBusy(false);
    }
  }

  async function handleStopProcess() {
    if (!processRunId) {
      return;
    }
    setProcessBusy(true);
    setProcessError(null);
    try {
      await stopProcess(projectId, { process_run_id: processRunId });
    } catch (error) {
      setProcessError(humanizeProcessStartError(error));
    } finally {
      setProcessBusy(false);
    }
  }

  const runGateMessage =
    blockers.run && !secretsReady
      ? blockers.run
      : wizardStatus.run_blocked_reason && !secretsReady
        ? wizardStatus.run_blocked_reason
        : null;

  return (
    <section className="wizard-step">
      <div className="wizard-step__content">
        <SectionHeading
          title="Run locally"
          detail="Start FXServer once to confirm your local setup works. This step is required before you continue."
        />

        {runGateMessage ? <WizardGateAlert title="Complete dev secrets first" detail={runGateMessage} /> : null}

        {!secretsReady ? null : (
          <>
            {ladderPhase === "detecting" ? (
              <Alert severity="info" title="Looking for FXServer">
                Checking common install locations for FXServer.exe…
              </Alert>
            ) : null}

            {ladderPhase === "found" ? (
              <SurfaceCard>
                <Alert severity="success" title="FXServer found">
                  <code>{fxserverPath}</code>
                </Alert>
                <div className="setup-step__actions">
                  <Button type="button" variant="secondary" disabled={pickerBusy} onClick={() => void handleLocateFxserver()}>
                    Choose a different FXServer.exe
                  </Button>
                </div>
              </SurfaceCard>
            ) : null}

            {ladderPhase === "locate" ? (
              <SurfaceCard>
                <p className="muted-copy">
                  We couldn&apos;t find FXServer automatically. If you&apos;ve already downloaded the FiveM server artifact, locate{" "}
                  <strong>FXServer.exe</strong> (not your server-data folder).
                </p>
                <div className="setup-step__actions">
                  <Button type="button" variant="primary" loading={pickerBusy} onClick={() => void handleLocateFxserver()}>
                    Locate FXServer.exe
                  </Button>
                  <Button type="button" variant="secondary" onClick={() => setLadderPhase("install")}>
                    I don&apos;t have FXServer yet
                  </Button>
                </div>
              </SurfaceCard>
            ) : null}

            {ladderPhase === "install" ? (
              <SurfaceCard>
                <ol className="plain-list">
                  <li>
                    Download the latest recommended <strong>server.7z</strong> build from the{" "}
                    <button type="button" className="link-button" onClick={() => void openExternalUrl(FIVEM_SERVER_ARTIFACTS_URL)}>
                      FiveM artifacts server
                    </button>
                    .
                  </li>
                  <li>Extract the archive to a folder on your PC.</li>
                  <li>
                    Use <strong>Locate FXServer.exe</strong> and point at the extracted <code>FXServer.exe</code> file.
                  </li>
                </ol>
                <div className="setup-step__actions">
                  <Button type="button" variant="primary" loading={pickerBusy} onClick={() => void handleLocateFxserver()}>
                    Locate FXServer.exe
                  </Button>
                  <Button type="button" variant="secondary" onClick={() => setLadderPhase("locate")}>
                    Back
                  </Button>
                </div>
              </SurfaceCard>
            ) : null}

            {ladderPhase === "found" ? (
              <>
                <Field
                  label="Server working folder"
                  hint="Folder containing your tracked server.cfg — usually the project root for team repos like PrevailRP."
                >
                  <div className="inline-actions">
                    <Input value={serverDataPath} readOnly placeholder="Resolving from tracked server.cfg…" />
                    <Button type="button" variant="secondary" disabled={pickerBusy} onClick={() => void handleBrowseServerData()}>
                      Browse…
                    </Button>
                  </div>
                </Field>

                <TechnicalDetails summary="Launch options">
                  <Field label="Launch mode">
                    <select value={txadminMode ? "txadmin" : "direct"} onChange={(event) => setTxadminMode(event.target.value === "txadmin")}>
                      <option value="direct">Direct (+exec server.cfg)</option>
                      <option value="txadmin">txAdmin mode</option>
                    </select>
                  </Field>
                </TechnicalDetails>

                {processError ? (
                  <Alert severity="warn" title={processError.title}>
                    {processError.detail}
                    {processError.raw && processError.raw !== processError.detail ? (
                      <TechnicalDetails summary="Technical details">
                        <pre className="command-json">{processError.raw}</pre>
                      </TechnicalDetails>
                    ) : null}
                  </Alert>
                ) : null}

                <div className="setup-step__actions">
                  <Button loading={processBusy} variant="primary" disabled={!canStart} onClick={() => void handleStartProcess()}>
                    Start server
                  </Button>
                  <Button disabled={!processRunId || processBusy} variant="secondary" onClick={() => void handleStopProcess()}>
                    Stop
                  </Button>
                </div>

                <div className="atlas-row">
                  <StatusPill status={processStatusKind}>{processStatus?.state ?? "Not started"}</StatusPill>
                  {processRunId ? <Badge variant="neutral">run {processRunId.slice(0, 8)}</Badge> : null}
                  {serverRunning ? <Badge variant="success">Server running</Badge> : null}
                </div>

                {serverLines.length > 0 ? (
                  <TechnicalDetails summary="Server output">
                    <pre className="command-json setup-output-log">{serverLines.join("\n")}</pre>
                  </TechnicalDetails>
                ) : (
                  <p className="muted-copy">Server output appears here after the process starts.</p>
                )}

                {lastAuditRef ? (
                  <TechnicalDetails summary="Last audited operation">
                    <p className="muted-copy">{lastAuditRef}</p>
                  </TechnicalDetails>
                ) : null}

                {!canContinue ? (
                  <Alert severity="info" title="Next step">
                    Start your server to continue — this confirms your local setup works.
                  </Alert>
                ) : (
                  <Alert severity="success" title="Ready to continue">
                    FXServer started successfully. You can finish setup and open server monitoring.
                  </Alert>
                )}
              </>
            ) : null}

            <DevDatabasePanel compact projectId={projectId} serverDataPath={serverDataPath} onAuditRef={(auditRef) => setLastAuditRef(auditRef)} />
          </>
        )}
      </div>
      <div className="wizard-step__footer">
        <Button variant="secondary" onClick={onBack}>
          Back
        </Button>
        <Button variant="primary" disabled={!canContinue} onClick={onContinue}>
          Continue to finish setup
        </Button>
      </div>
    </section>
  );
}

function SurfaceCard({ children }: { children: ReactNode }) {
  return <div className="atlas-card atlas-pad">{children}</div>;
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
