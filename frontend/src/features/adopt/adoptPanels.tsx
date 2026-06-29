import { useEffect, useMemo, useState } from "react";

import {
  applyDevSecret,
  applySafeReturnCommit,
  dryRunDevSecret,
  dryRunSafeReturnCommit,
  getReturnPathStatus,
  previewDevSecret,
  previewSafeReturnCommit,
  undoPathway2Command,
  type ContaminationReport,
  type InlineSecretFinding,
  type ReturnPathStatus,
  type StructureScorecard,
  type SubstitutionSlotPreview
} from "../../api/pathway2";
import { createBranch } from "../../api/git";
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
  TechnicalDetails,
  Alert
} from "../../components";
import type { SecretsStepGuidance } from "../../api/pathway2";
import { CommandPanel } from "../../components/CommandPanel";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { KEYMASTER_URL, openExternalUrl } from "../../lib/openExternal";

const DEV_LICENSE_PLACEHOLDER = "DEV_LICENSE_KEY_SET_ME";
const LICENSE_SLOT_ID = "sv_licenseKey";

function licenseKeyPending(unsetDevSlots: string[]): boolean {
  return unsetDevSlots.includes(DEV_LICENSE_PLACEHOLDER) || unsetDevSlots.includes(LICENSE_SLOT_ID);
}

export function StructureScorecardView({ scorecard, compact = false }: { scorecard: StructureScorecard; compact?: boolean }) {
  const rows = useMemo(
    () =>
      Object.entries(scorecard.checks).map(([key, value]) => ({
        key,
        label: key.replace(/_/g, " "),
        present: value.present
      })),
    [scorecard]
  );

  if (compact) {
    return (
      <div className="stack-gap-sm">
        <p className="muted-copy">
          {scorecard.looks_like_fivem_server
            ? `FiveM server detected (${scorecard.confidence} confidence, score ${scorecard.score}).`
            : "FiveM server not confidently detected yet."}
        </p>
        <div className="inline-actions">
          {rows.map((row) => (
            <Badge key={row.key} variant={row.present ? "info" : "neutral"}>
              {row.label}: {row.present ? "yes" : "no"}
            </Badge>
          ))}
        </div>
      </div>
    );
  }

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

export function InlineSecretsReport({ findings }: { findings: InlineSecretFinding[] }) {
  const list = (
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
  );

  return (
    <div className="stack-gap-sm">
      <SectionHeading title="Inline secrets (masked)" detail="Production-shaped values detected in tracked config. Normalization will placeholderize these." />
      {findings.length > 3 ? (
        <TechnicalDetails summary={`${findings.length} inline secrets detected`}>{list}</TechnicalDetails>
      ) : (
        list
      )}
    </div>
  );
}

export function SubstitutionSlotsReport({
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

export function DevLicenseEntryPanel({
  projectId,
  unsetDevSlots,
  onApplied
}: {
  projectId: string;
  unsetDevSlots: string[];
  onApplied: () => void;
}) {
  const [licenseKey, setLicenseKey] = useState("");
  const [showLicenseKey, setShowLicenseKey] = useState(false);
  const showForm = licenseKeyPending(unsetDevSlots);
  const formatWarning = !licenseKey.trim() || licenseKey.trim().startsWith("cfxk_") ? null : (
    <Alert severity="warn" title="Unusual key format">
      Dev license keys usually start with cfxk_. Continue only if you are sure this value is correct.
    </Alert>
  );

  if (!showForm) {
    return (
      <Alert severity="success" title="Dev license set">
        Your personal dev license is saved in server.cfg.local (gitignored). Previews and audit logs show a masked value only.
      </Alert>
    );
  }

  return (
    <div className="stack-gap-md">
      <SectionHeading
        title="Dev license key"
        detail="Paste your Cfx.re dev license below. Atlas writes it to server.cfg.local only — never to tracked server.cfg."
      />
      {formatWarning}
      <InputGroup>
        <Field label="Cfx.re dev license key" hint="Starts with cfxk_; stored locally in the gitignored overlay.">
          <div className="inline-actions">
            <Input
              type={showLicenseKey ? "text" : "password"}
              autoComplete="off"
              spellCheck={false}
              value={licenseKey}
              onChange={(event) => setLicenseKey(event.target.value)}
              placeholder="cfxk_…"
            />
            <Button type="button" variant="secondary" onClick={() => setShowLicenseKey((current) => !current)}>
              {showLicenseKey ? "Hide" : "Show"}
            </Button>
          </div>
        </Field>
      </InputGroup>
      <CommandPanel
        title="Save dev license to overlay"
        description="Preview shows a masked diff. Apply writes server.cfg.local; undo restores the placeholder."
        executeLabel="Save to overlay"
        presentation="guided"
        disabled={!licenseKey.trim()}
        onPreview={() => previewDevSecret(projectId, LICENSE_SLOT_ID, licenseKey.trim())}
        onDryRun={() => dryRunDevSecret(projectId, LICENSE_SLOT_ID, licenseKey.trim())}
        onExecute={() => applyDevSecret(projectId, LICENSE_SLOT_ID, licenseKey.trim())}
        onUndo={(commandExecutionId) => undoPathway2Command(projectId, commandExecutionId)}
        onSuccess={() => {
          setLicenseKey("");
          onApplied();
        }}
        onUndoSuccess={() => onApplied()}
      />
    </div>
  );
}

export function DevSecretEntryForm({
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
  const pending = slots.filter(
    (slot) =>
      slot.slot_id !== LICENSE_SLOT_ID &&
      unsetDevSlots.some((marker) => slot.replacement_line.includes(marker) || slot.slot_id === marker)
  );
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

export function ContaminationReportView({ report }: { report: ContaminationReport }) {
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
              <code>
                {finding.path}:{finding.line}
              </code>{" "}
              — {finding.secret_type}: {finding.redacted_preview}
            </li>
          ))}
        </ul>
      ) : null}
      <p className="muted-text">{report.push_seam}</p>
    </div>
  );
}

export function ReturnPathPanel({
  projectId,
  initialReturnPath,
  onStatusChange
}: {
  projectId: string;
  initialReturnPath?: ReturnPathStatus | null;
  onStatusChange?: () => void;
}) {
  const [returnStatus, setReturnStatus] = useState<ReturnPathStatus | null>(initialReturnPath ?? null);
  const [statusError, setStatusError] = useState<unknown>(null);
  const [branchName, setBranchName] = useState("feature/atlas-dev");
  const [commitMessage, setCommitMessage] = useState("Atlas: overlay-safe config normalization");
  const [creatingBranch, setCreatingBranch] = useState(false);

  useEffect(() => {
    if (initialReturnPath) {
      setReturnStatus(initialReturnPath);
      return;
    }
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
  }, [projectId, initialReturnPath]);

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

  const commitBlocked = returnStatus?.contamination_report.allowed === false;
  const commitBlockReason =
    returnStatus?.contamination_report.findings[0] != null
      ? `Remove the secret in ${returnStatus.contamination_report.findings[0].path}:${returnStatus.contamination_report.findings[0].line} before committing.`
      : returnStatus?.contamination_report.summary_lines[0];

  async function createFeatureBranch() {
    if (!returnStatus || !branchName.trim()) {
      return;
    }
    setCreatingBranch(true);
    try {
      await createBranch(projectId, returnStatus.git_repository_id, branchName.trim());
      const response = await getReturnPathStatus(projectId, returnStatus.git_repository_id);
      setReturnStatus(response.data);
      onStatusChange?.();
    } finally {
      setCreatingBranch(false);
    }
  }

  return (
    <>
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
          {commitBlocked && commitBlockReason ? (
            <EmptyState title="Commit blocked" detail={commitBlockReason} />
          ) : null}
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
              presentation="guided"
              disabled={commitBlocked}
              onPreview={() => previewSafeReturnCommit(projectId, commitRequest)}
              onDryRun={() => dryRunSafeReturnCommit(projectId, commitRequest)}
              onExecute={() => applySafeReturnCommit(projectId, commitRequest)}
              onSuccess={async () => {
                const response = await getReturnPathStatus(projectId, returnStatus.git_repository_id);
                setReturnStatus(response.data);
                onStatusChange?.();
              }}
            />
          ) : null}
        </>
      ) : (
        <LoadingState title="Loading return-path status" detail="Discovering git repository and running contamination scan." />
      )}
    </>
  );
}

export function Pathway2StatusBadges({
  normalized,
  secretsSubstituted,
  runReady,
  devTransformed
}: {
  normalized: boolean;
  secretsSubstituted: boolean;
  runReady: boolean;
  devTransformed: boolean;
}) {
  return (
    <div className="inline-actions">
      <StatusPill status="running">Pathway 2</StatusPill>
      {normalized ? <Badge variant="info">Normalized</Badge> : <Badge variant="neutral">Not normalized</Badge>}
      {secretsSubstituted ? <Badge variant="info">Secrets substituted</Badge> : null}
      {runReady ? <Badge variant="info">Run ready</Badge> : null}
      {devTransformed ? <Badge variant="info">Dev transformed</Badge> : null}
    </div>
  );
}

export function DevSecretsStepHero({ guidance }: { guidance: SecretsStepGuidance }) {
  const variant =
    guidance.phase === "ready"
      ? "success"
      : guidance.phase === "apply_substitution"
        ? "info"
        : guidance.phase === "set_dev_license"
          ? "warn"
          : "info";

  return (
    <Alert severity={variant} title={guidance.title}>
      <p>{guidance.detail}</p>
      {guidance.phase === "set_dev_license" ? (
        <p className="muted-copy" style={{ marginTop: "var(--space-2)" }}>
          <Button variant="ghost" size="sm" onClick={() => void openExternalUrl(KEYMASTER_URL)}>
            Get a dev license key from the Cfx.re Keymaster ↗
          </Button>{" "}
          Keys start with <code>cfxk_</code>.
        </p>
      ) : null}
      <p className="muted-copy" style={{ marginTop: "var(--space-2)" }}>
        Next: {guidance.primary_action}
      </p>
    </Alert>
  );
}

export function WizardGateAlert({ title, detail }: { title: string; detail: string }) {
  return <EmptyState title={title} detail={detail} />;
}
