import { useMemo, useState } from "react";

import type { ConfigFinding, ConfigValidationBlock } from "../../api/configValidation";
import { findingTypeLabel, formatFindingLocation } from "../../api/configValidation";
import {
  previewCommentOutDanglingEnsure,
  dryRunCommentOutDanglingEnsure,
  applyCommentOutDanglingEnsure,
  previewRewriteAbsolutePath,
  dryRunRewriteAbsolutePath,
  applyRewriteAbsolutePath
} from "../../api/configRemediation";
import { undoCommandExecution } from "../../api/project";
import { Alert, Badge, Button, SectionHeading, Surface } from "../../components";
import { CommandPanel } from "../../components/CommandPanel";

interface ConfigFindingsPanelProps {
  validation: ConfigValidationBlock | null | undefined;
  projectId?: string;
  compact?: boolean;
  showInlineSecretHint?: boolean;
  lastCheckedAt?: string | null;
}

export function ConfigValidationSummaryBar({
  validation,
  onCopied
}: {
  validation: ConfigValidationBlock | null | undefined;
  onCopied?: (label: string) => void;
}) {
  const findings = validation?.findings ?? [];
  const errorCount = findings.filter((item) => item.severity === "error").length;
  const warningCount = findings.filter((item) => item.severity === "warning").length;
  const hasValidated = validation?.status === "validated";
  const skipped = validation?.status === "skipped_no_server_cfg";
  const notRun = !validation || validation.status === "not_run";

  async function copyPrompt() {
    const text = validation?.all_issues_prompt;
    if (!text) {
      return;
    }
    await navigator.clipboard.writeText(text);
    onCopied?.("llm");
  }

  if (notRun) {
    return null;
  }

  if (skipped) {
    return (
      <div className="config-validation-bar">
        <Badge variant="warn">No server.cfg</Badge>
        <span className="muted-copy">Structural validation skipped.</span>
      </div>
    );
  }

  if (hasValidated && findings.length === 0) {
    return (
      <div className="config-validation-bar">
        <Badge variant="success">Config clean</Badge>
        <span className="muted-copy">No structural issues found.</span>
      </div>
    );
  }

  return (
    <div className="config-validation-bar">
      <div className="inline-actions">
        {errorCount > 0 ? (
          <Badge variant="danger">
            {errorCount} error{errorCount === 1 ? "" : "s"}
          </Badge>
        ) : null}
        {warningCount > 0 ? (
          <Badge variant="warn">
            {warningCount} warning{warningCount === 1 ? "" : "s"}
          </Badge>
        ) : null}
        <span className="muted-copy">
          {validation?.finding_count ?? findings.length} structural issue{(validation?.finding_count ?? findings.length) === 1 ? "" : "s"}
        </span>
      </div>
      {validation?.all_issues_prompt ? (
        <Button type="button" size="sm" variant="secondary" onClick={() => void copyPrompt()}>
          Copy for LLM
        </Button>
      ) : null}
    </div>
  );
}

export function ConfigFindingsPanel({
  validation,
  projectId,
  compact = false,
  showInlineSecretHint = true,
  lastCheckedAt
}: ConfigFindingsPanelProps) {
  const [copyStatus, setCopyStatus] = useState<string | null>(null);

  const findings = validation?.findings ?? [];
  const hasValidated = validation?.status === "validated";
  const skipped = validation?.status === "skipped_no_server_cfg";
  const notRun = !validation || validation.status === "not_run";

  async function copyText(label: string, text: string) {
    await navigator.clipboard.writeText(text);
    setCopyStatus(label);
    window.setTimeout(() => setCopyStatus(null), 2000);
  }

  return (
    <div className="stack-gap-md config-findings-panel">
      <ConfigValidationSummaryBar validation={validation} onCopied={() => setCopyStatus("llm")} />
      {lastCheckedAt ? <p className="muted-copy">Last checked {lastCheckedAt}</p> : null}
      {copyStatus ? (
        <p className="muted-copy">{copyStatus === "llm" ? "Copied LLM fix prompt to clipboard." : "Copied fix prompt."}</p>
      ) : null}

      {notRun ? (
        <Alert severity="info" title="Config not yet validated">
          Run Preview changes to scan server.cfg for structural issues (dangling ensures, missing manifests, absolute paths, inline secrets).
          After fixing files on disk, use Re-run changes to refresh.
        </Alert>
      ) : null}

      {skipped ? (
        <Alert severity="warn" title="Structural validation skipped">
          No server.cfg found at this path — Atlas could not run structural validation.
        </Alert>
      ) : null}

      {hasValidated && findings.length === 0 ? (
        <Alert severity="success" title="No structural issues found">
          Atlas validated server.cfg and resources/ — no dangling references, missing manifests, absolute paths, or inline secrets detected.
        </Alert>
      ) : null}

      {hasValidated && findings.length > 0 ? (
        <>
          {!compact ? (
            <SectionHeading
              title="Config findings"
              detail="Structural problems in server.cfg and resources/. Secrets are masked everywhere."
            />
          ) : null}
          <div className="config-findings-grid">
            {findings.map((finding) => (
              <ConfigFindingCard
                key={finding.finding_id}
                finding={finding}
                fixPrompt={validation?.fix_prompts?.[finding.finding_id]}
                projectId={projectId}
                showInlineSecretHint={showInlineSecretHint}
                onCopyPrompt={(text) => void copyText(finding.finding_id, text)}
              />
            ))}
          </div>
        </>
      ) : null}
    </div>
  );
}

function ConfigFindingCard({
  finding,
  fixPrompt,
  projectId,
  showInlineSecretHint,
  onCopyPrompt
}: {
  finding: ConfigFinding;
  fixPrompt?: string;
  projectId?: string;
  showInlineSecretHint: boolean;
  onCopyPrompt: (text: string) => void;
}) {
  const severityVariant = finding.severity === "error" ? "danger" : finding.severity === "warning" ? "warn" : "neutral";

  return (
    <Surface kind="card" className="config-finding-card">
      <div className="atlas-row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
        <div className="stack-gap-sm">
          <div className="inline-actions">
            <Badge variant={severityVariant}>{finding.severity}</Badge>
            <Badge variant="info">{findingTypeLabel(finding.type)}</Badge>
          </div>
          <p>
            <code>{formatFindingLocation(finding)}</code>
          </p>
          <p>{finding.message}</p>
          {finding.type === "INLINE_SECRET" && showInlineSecretHint ? (
            <p className="muted-copy">Use the Join-team adopt flow (P2-2 substitution) to relocate secrets — Atlas does not auto-rewrite secrets on Import.</p>
          ) : null}
        </div>
      </div>
      <div className="inline-actions" style={{ marginTop: "var(--space-3)" }}>
        {fixPrompt ? (
          <Button type="button" variant="secondary" size="sm" onClick={() => onCopyPrompt(fixPrompt)}>
            Copy for LLM
          </Button>
        ) : null}
        {projectId && finding.remediation.auto_fix_available && finding.remediation.auto_fix_kind === "comment_out_ensure" ? (
          <RemediationCommandPanel
            title="Comment out dangling ensure"
            description="Reversible: comments out the broken ensure/start line so the server can boot."
            findingId={finding.finding_id}
            onPreview={() => previewCommentOutDanglingEnsure(projectId, finding.finding_id)}
            onDryRun={() => dryRunCommentOutDanglingEnsure(projectId, finding.finding_id)}
            onExecute={() => applyCommentOutDanglingEnsure(projectId, finding.finding_id)}
            onUndo={(commandExecutionId) => undoCommandExecution(commandExecutionId)}
          />
        ) : null}
        {projectId && finding.remediation.auto_fix_available && finding.remediation.auto_fix_kind === "rewrite_absolute_path" ? (
          <RemediationCommandPanel
            title="Rewrite absolute path"
            description="Preview the portable path rewrite and confirm before applying. Undo restores the original line."
            findingId={finding.finding_id}
            onPreview={() => previewRewriteAbsolutePath(projectId, finding.finding_id)}
            onDryRun={() => dryRunRewriteAbsolutePath(projectId, finding.finding_id)}
            onExecute={() => applyRewriteAbsolutePath(projectId, finding.finding_id)}
            onUndo={(commandExecutionId) => undoCommandExecution(commandExecutionId)}
          />
        ) : null}
      </div>
    </Surface>
  );
}

function RemediationCommandPanel({
  title,
  description,
  findingId,
  onPreview,
  onDryRun,
  onExecute,
  onUndo
}: {
  title: string;
  description: string;
  findingId: string;
  onPreview: () => ReturnType<typeof previewCommentOutDanglingEnsure>;
  onDryRun: () => ReturnType<typeof dryRunCommentOutDanglingEnsure>;
  onExecute: () => ReturnType<typeof applyCommentOutDanglingEnsure>;
  onUndo: (commandExecutionId: string) => ReturnType<typeof undoCommandExecution>;
}) {
  return (
    <div className="config-remediation-panel">
      <CommandPanel
        presentation="guided"
        title={title}
        description={description}
        previewLabel="Preview safe fix"
        executeLabel="Apply safe fix"
        onPreview={onPreview}
        onDryRun={onDryRun}
        onExecute={onExecute}
        onUndo={onUndo}
      />
      <span className="muted-copy" hidden>
        {findingId}
      </span>
    </div>
  );
}
