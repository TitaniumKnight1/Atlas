import { useEffect, useMemo, useState } from "react";

import {
  adoptRepository,
  applySafeReturnCommit,
  applyDevSecret,
  applyDevConfigTransform,
  applyRepoNormalization,
  applySecretSubstitution,
  dryRunAdoptRepository,
  dryRunDevConfigTransform,
  dryRunRepoNormalization,
  dryRunSafeReturnCommit,
  dryRunSecretSubstitution,
  getPathway2Status,
  getReturnPathStatus,
  previewAdoptRepository,
  previewDevConfigTransform,
  previewRepoNormalization,
  previewSafeReturnCommit,
  previewSecretSubstitution,
  type ContaminationReport,
  type ReturnPathStatus,
  undoPathway2Command,
  type InlineSecretFinding,
  type Pathway2Status,
  type StructureScorecard,
  type SubstitutionSlotPreview
} from "../../api/pathway2";
import { createBranch } from "../../api/git";
import { listProjects, type ProjectSummary } from "../../api/project";
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
  Surface
} from "../../components";
import { CommandPanel } from "../../components/CommandPanel";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { useAsyncTask } from "../../components/useAsyncTask";

type AdoptPhase = "input" | "adopted";

export function AdoptView() {
  const { resource: projectsResource } = useAsyncTask<ProjectSummary[]>(listProjects, []);
  const [phase, setPhase] = useState<AdoptPhase>("input");
  const [rootPath, setRootPath] = useState("");
  const [remoteUrl, setRemoteUrl] = useState("");
  const [projectId, setProjectId] = useState<string | null>(null);
  const [status, setStatus] = useState<Pathway2Status | null>(null);
  const [statusError, setStatusError] = useState<unknown>(null);
  const [statusLoading, setStatusLoading] = useState(false);

  const [transformHostname, setTransformHostname] = useState("[DEV] Atlas Local Server");
  const [transformMaxClients, setTransformMaxClients] = useState("8");
  const [transformPort, setTransformPort] = useState("30121");

  const transformOptions = useMemo(
    () => ({
      hostname: transformHostname.trim() || undefined,
      max_clients: Number.parseInt(transformMaxClients, 10) || undefined,
      udp_port: Number.parseInt(transformPort, 10) || undefined,
      tcp_port: Number.parseInt(transformPort, 10) || undefined
    }),
    [transformHostname, transformMaxClients, transformPort]
  );

  const projects = projectsResource.state === "ready" ? projectsResource.data : [];

  useEffect(() => {
    if (!projectId) {
      return;
    }
    let cancelled = false;
    const activeProjectId = projectId;
    async function loadStatus() {
      setStatusLoading(true);
      setStatusError(null);
      try {
        const response = await getPathway2Status(activeProjectId);
        if (!cancelled) {
          setStatus(response.data);
        }
      } catch (error) {
        if (!cancelled) {
          setStatusError(error);
        }
      } finally {
        if (!cancelled) {
          setStatusLoading(false);
        }
      }
    }
    void loadStatus();
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  const scorecard = status?.structure_scorecard;

  async function refreshStatus(activeProjectId: string) {
    const response = await getPathway2Status(activeProjectId);
    setStatus(response.data);
  }

  return (
    <div className="feature-stack">
      <SectionHeading
        title="Adopt team server"
        detail="Clone or import an existing FiveM repository, normalize the overlay structure, and substitute dev secrets locally."
      />

      {phase === "input" ? (
        <Surface>
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
            disabled={!rootPath.trim()}
            onPreview={() => previewAdoptRepository(rootPath.trim(), remoteUrl.trim() || undefined)}
            onDryRun={() => dryRunAdoptRepository(rootPath.trim(), remoteUrl.trim() || undefined)}
            onExecute={() => adoptRepository(rootPath.trim(), remoteUrl.trim() || undefined)}
            onSuccess={(response) => {
              const adoptedId = String(response.data.project_id ?? "");
              if (adoptedId) {
                setProjectId(adoptedId);
                setPhase("adopted");
              }
            }}
          />
        </Surface>
      ) : null}

      {phase === "adopted" && projectId ? (
        <>
          <Surface>
            <div className="inline-actions">
              <StatusPill status="running">Pathway 2 adopt</StatusPill>
              {status?.pathway2_state.normalized ? <Badge variant="info">Normalized</Badge> : <Badge variant="neutral">Not normalized</Badge>}
              {status?.pathway2_state.secrets_substituted ? <Badge variant="info">Secrets substituted</Badge> : null}
              {status?.pathway2_state.run_ready ? <Badge variant="info">Run ready</Badge> : null}
              {status?.pathway2_state.dev_transformed ? <Badge variant="info">Dev transformed</Badge> : null}
            </div>
            {statusLoading ? <LoadingState title="Loading adopt status" detail="Refreshing structure scorecard and secret report." /> : null}
            {statusError ? <ErrorState error={statusError} /> : null}
            {scorecard ? <StructureScorecardView scorecard={scorecard} /> : null}
            {status?.inline_secrets?.length ? <InlineSecretsReport findings={status.inline_secrets} /> : null}
            {status?.run_blocked_reason ? (
              <EmptyState title="Server not ready to run" detail={status.run_blocked_reason} />
            ) : null}
          </Surface>

          <Surface>
            <SectionHeading
              title="Normalize base config"
              detail="Preview-first restructuring: placeholders in server.cfg, endpoints moved to gitignored server.cfg.local, exec trailer appended."
            />
            <CommandPanel
              title="Apply overlay structure"
              description="Mutates server.cfg through the command contract. Undo restores the original file byte-for-byte."
              executeLabel="Apply normalization"
              onPreview={() => previewRepoNormalization(projectId)}
              onDryRun={() => dryRunRepoNormalization(projectId)}
              onExecute={() => applyRepoNormalization(projectId)}
              onUndo={(commandExecutionId) => undoPathway2Command(projectId, commandExecutionId)}
              onSuccess={() => void refreshStatus(projectId)}
              onUndoSuccess={() => void refreshStatus(projectId)}
            />
          </Surface>

          {status?.pathway2_state.normalized ? (
            <Surface>
              <SectionHeading
                title="Substitute dev secrets"
                detail="Hybrid model: Atlas fills safe local defaults (DB, ports); you supply dev-only keys; prod integrations get optional placeholders."
              />
              {status.substitution_slots?.length ? (
                <SubstitutionSlotsReport slots={status.substitution_slots} unsetDevSlots={status.unset_dev_slots ?? []} />
              ) : null}
              <CommandPanel
                title="Apply secret substitution"
                description="Writes dev values and placeholders into server.cfg.local only. Production secrets stay masked in previews."
                executeLabel="Apply substitution"
                onPreview={() => previewSecretSubstitution(projectId)}
                onDryRun={() => dryRunSecretSubstitution(projectId)}
                onExecute={() => applySecretSubstitution(projectId)}
                onUndo={(commandExecutionId) => undoPathway2Command(projectId, commandExecutionId)}
                onSuccess={() => void refreshStatus(projectId)}
                onUndoSuccess={() => void refreshStatus(projectId)}
              />
              {status.pathway2_state.secrets_substituted && (status.unset_dev_slots?.length ?? 0) > 0 ? (
                <DevSecretEntryForm
                  projectId={projectId}
                  slots={status.substitution_slots ?? []}
                  unsetDevSlots={status.unset_dev_slots ?? []}
                  onApplied={() => void refreshStatus(projectId)}
                />
              ) : null}
            </Surface>
          ) : null}

          {status?.pathway2_state.secrets_substituted ? (
            <Surface>
              <SectionHeading
                title="Apply dev config transform"
                detail="Non-secret dev tuning: hostname, slots, ports, and dev convars written to server.cfg.local only."
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
                onPreview={() => previewDevConfigTransform(projectId, transformOptions)}
                onDryRun={() => dryRunDevConfigTransform(projectId, transformOptions)}
                onExecute={() => applyDevConfigTransform(projectId, transformOptions)}
                onUndo={(commandExecutionId) => undoPathway2Command(projectId, commandExecutionId)}
                onSuccess={() => void refreshStatus(projectId)}
                onUndoSuccess={() => void refreshStatus(projectId)}
              />
            </Surface>
          ) : null}

          {status?.pathway2_state.origin ? (
            <ReturnPathSection projectId={projectId} />
          ) : null}
        </>
      ) : null}

      {projects.length > 0 && phase === "input" ? (
        <Surface>
          <SectionHeading title="Resume adopted project" detail="Pick an existing workspace to continue normalization." />
          <div className="inline-actions">
            {projects.map((project) => (
              <Button
                key={project.project_id}
                variant="secondary"
                onClick={() => {
                  setProjectId(project.project_id);
                  setPhase("adopted");
                }}
              >
                {project.display_name}
              </Button>
            ))}
          </div>
        </Surface>
      ) : null}
    </div>
  );
}

function StructureScorecardView({ scorecard }: { scorecard: StructureScorecard }) {
  const rows = useMemo(
    () =>
      Object.entries(scorecard.checks).map(([key, value]) => ({
        key,
        label: key.replace(/_/g, " "),
        present: value.present
      })),
    [scorecard]
  );

  return (
    <div className="stack-gap-md">
      <DefinitionGrid
        items={[
          ["FiveM server", scorecard.looks_like_fivem_server ? "Yes" : "No"],
          ["Confidence", scorecard.confidence],
          ["Score", scorecard.score],
          ["server.cfg", scorecard.server_cfg_path ?? "Not found"],
          ["Git remote", scorecard.git_remote_redacted ?? "Not discovered"],
          ["Resources", scorecard.resource_count?.toString() ?? "—"]
        ]}
      />
      <div className="scorecard-grid">
        {rows.map((row) => (
          <CellStack key={row.key} title={row.label} detail={row.present ? "Present" : "Missing"} />
        ))}
      </div>
    </div>
  );
}

function InlineSecretsReport({ findings }: { findings: InlineSecretFinding[] }) {
  return (
    <div className="stack-gap-sm">
      <SectionHeading title="Inline secrets (masked)" detail="Production-shaped values detected in tracked config. Normalization will placeholderize these." />
      <ul className="plain-list">
        {findings.map((finding, index) => (
          <li key={`${finding.path}:${finding.line}:${index}`}>
            <code>
              {finding.path}:{finding.line}
            </code>{" "}
            — {finding.secret_type}: {finding.redacted_preview}
          </li>
        ))}
      </ul>
    </div>
  );
}

function SubstitutionSlotsReport({
  slots,
  unsetDevSlots
}: {
  slots: SubstitutionSlotPreview[];
  unsetDevSlots: string[];
}) {
  return (
    <div className="stack-gap-sm">
      <SectionHeading title="Substitution plan" detail="Production values are masked; replacements show what will land in server.cfg.local." />
      <ul className="plain-list">
        {slots.map((slot) => (
          <li key={slot.slot_id}>
            <code>{slot.convar_key ?? slot.slot_id}</code> — {slot.handling_class.replace(/_/g, " ")} — source {slot.masked_source}
            {unsetDevSlots.includes(slot.slot_id) ? " (needs your dev value)" : null}
            <div className="muted-text">
              <code>{slot.replacement_line}</code>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function DevSecretEntryForm({
  projectId,
  slots,
  unsetDevSlots,
  onApplied
}: {
  projectId: string;
  slots: SubstitutionSlotPreview[];
  unsetDevSlots: string[];
  onApplied: () => void;
}) {
  const pending = slots.filter((slot) => unsetDevSlots.includes(slot.slot_id));
  const [values, setValues] = useState<Record<string, string>>({});
  const [savingSlot, setSavingSlot] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);

  async function saveSlot(slotId: string) {
    const value = values[slotId]?.trim();
    if (!value) {
      return;
    }
    setSavingSlot(slotId);
    setError(null);
    try {
      await applyDevSecret(projectId, slotId, value);
      setValues((current) => {
        const next = { ...current };
        delete next[slotId];
        return next;
      });
      onApplied();
    } catch (nextError) {
      setError(nextError);
    } finally {
      setSavingSlot(null);
    }
  }

  return (
    <div className="stack-gap-md">
      <SectionHeading title="Enter dev secrets" detail="Your dev license key and similar values stay local and are masked in previews." />
      {error ? <ErrorState error={error} /> : null}
      {pending.map((slot) => (
        <InputGroup key={slot.slot_id}>
          <Field label={slot.convar_key ?? slot.slot_id} hint={`Handling: ${slot.handling_class.replace(/_/g, " ")}`}>
            <div className="inline-actions">
              <Input
                type="password"
                value={values[slot.slot_id] ?? ""}
                onChange={(event) => setValues((current) => ({ ...current, [slot.slot_id]: event.target.value }))}
                placeholder="Your dev-only value"
              />
              <Button variant="secondary" disabled={!values[slot.slot_id]?.trim() || savingSlot === slot.slot_id} onClick={() => void saveSlot(slot.slot_id)}>
                {savingSlot === slot.slot_id ? "Saving…" : "Save to overlay"}
              </Button>
            </div>
          </Field>
        </InputGroup>
      ))}
    </div>
  );
}

function ReturnPathSection({ projectId }: { projectId: string }) {
  const [returnStatus, setReturnStatus] = useState<ReturnPathStatus | null>(null);
  const [statusError, setStatusError] = useState<unknown>(null);
  const [branchName, setBranchName] = useState("feature/atlas-dev");
  const [commitMessage, setCommitMessage] = useState("Pathway 2 dev work");
  const [creatingBranch, setCreatingBranch] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setStatusError(null);
      try {
        const response = await getReturnPathStatus(projectId);
        if (!cancelled) {
          setReturnStatus(response.data);
        }
      } catch (error) {
        if (!cancelled) {
          setStatusError(error);
        }
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  const commitRequest = useMemo(
    () =>
      returnStatus
        ? {
            git_repository_id: returnStatus.git_repository_id,
            message: commitMessage,
            paths: returnStatus.default_commit_paths
          }
        : null,
    [returnStatus, commitMessage]
  );

  async function createFeatureBranch() {
    if (!returnStatus || !branchName.trim()) {
      return;
    }
    setCreatingBranch(true);
    try {
      await createBranch(projectId, returnStatus.git_repository_id, branchName.trim());
      const response = await getReturnPathStatus(projectId, returnStatus.git_repository_id);
      setReturnStatus(response.data);
    } finally {
      setCreatingBranch(false);
    }
  }

  return (
    <Surface>
      <SectionHeading
        title="Return path (safe commit)"
        detail="Fail-closed secret gate on explicit paths only. Atlas commits locally; you push manually (ADR-0010)."
      />
      {statusError ? <ErrorState error={statusError} /> : null}
      {returnStatus ? (
        <>
          <DefinitionGrid
            items={[
              ["Branch", returnStatus.branch_name ?? "detached"],
              ["Git repo", returnStatus.git_repository_id],
              ["Overlay gitignored", returnStatus.gitignore_contains_overlay ? "Yes" : "No"],
              ["Gate", returnStatus.contamination_report.gate_status]
            ]}
          />
          <ContaminationReportView report={returnStatus.contamination_report} />
          <InputGroup>
            <Field label="Feature branch">
              <div className="inline-actions">
                <Input value={branchName} onChange={(event) => setBranchName(event.target.value)} />
                <Button variant="secondary" disabled={creatingBranch} onClick={() => void createFeatureBranch()}>
                  {creatingBranch ? "Creating…" : "Create branch"}
                </Button>
              </div>
            </Field>
            <Field label="Commit message">
              <Input value={commitMessage} onChange={(event) => setCommitMessage(event.target.value)} />
            </Field>
          </InputGroup>
          {commitRequest ? (
            <CommandPanel
              title="Safe return commit"
              description={returnStatus.manual_push_message}
              executeLabel="Commit locally"
              onPreview={() => previewSafeReturnCommit(projectId, commitRequest)}
              onDryRun={() => dryRunSafeReturnCommit(projectId, commitRequest)}
              onExecute={() => applySafeReturnCommit(projectId, commitRequest)}
              onUndo={(commandExecutionId) => undoPathway2Command(projectId, commandExecutionId)}
              onSuccess={async () => {
                const response = await getReturnPathStatus(projectId, returnStatus.git_repository_id);
                setReturnStatus(response.data);
              }}
            />
          ) : null}
        </>
      ) : (
        <LoadingState title="Loading return-path status" detail="Discovering git repository and running contamination scan." />
      )}
    </Surface>
  );
}

function ContaminationReportView({ report }: { report: ContaminationReport }) {
  return (
    <div className="stack-gap-sm">
      <ul className="plain-list">
        {report.summary_lines.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      {report.findings.length ? (
        <ul className="plain-list">
          {report.findings.map((finding, index) => (
            <li key={`${finding.path}:${finding.line}:${index}`}>
              <code>{finding.path}:{finding.line}</code> — {finding.secret_type}: {finding.redacted_preview}
            </li>
          ))}
        </ul>
      ) : null}
      <p className="muted-text">{report.push_seam}</p>
    </div>
  );
}
