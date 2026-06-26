import { useState } from "react";

import type { BackendResponse } from "../api/backend";
import { formatAuditRef, type CommandResultData, type DryRunData, type CommandPreviewData } from "../api/project";
import { ErrorState, LoadingState } from "./StateViews";

interface CommandPanelProps {
  title: string;
  description: string;
  previewLabel?: string;
  executeLabel: string;
  disabled?: boolean;
  onPreview: () => Promise<BackendResponse<CommandPreviewData>>;
  onDryRun: () => Promise<BackendResponse<DryRunData>>;
  onExecute: () => Promise<BackendResponse<CommandResultData>>;
  onUndo?: (commandExecutionId: string) => Promise<BackendResponse<CommandResultData>>;
  onSuccess?: (result: BackendResponse<CommandResultData>) => void;
  onUndoSuccess?: (result: BackendResponse<CommandResultData>) => void;
}

type Phase = "idle" | "previewing" | "ready" | "executing" | "success" | "undoing" | "undone" | "error";

export function CommandPanel({
  title,
  description,
  previewLabel = "Preview changes",
  executeLabel,
  disabled,
  onPreview,
  onDryRun,
  onExecute,
  onUndo,
  onSuccess,
  onUndoSuccess
}: CommandPanelProps) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [preview, setPreview] = useState<BackendResponse<CommandPreviewData> | null>(null);
  const [dryRun, setDryRun] = useState<BackendResponse<DryRunData> | null>(null);
  const [result, setResult] = useState<BackendResponse<CommandResultData> | null>(null);
  const [undoResult, setUndoResult] = useState<BackendResponse<CommandResultData> | null>(null);
  const [error, setError] = useState<unknown>(null);

  async function previewCommand() {
    setPhase("previewing");
    setError(null);
    try {
      const previewResult = await onPreview();
      const dryRunResult = await onDryRun();
      setPreview(previewResult);
      setDryRun(dryRunResult);
      setPhase("ready");
    } catch (caught) {
      setError(caught);
      setPhase("error");
    }
  }

  async function executeCommand() {
    setPhase("executing");
    setError(null);
    setUndoResult(null);
    try {
      const executeResult = await onExecute();
      setResult(executeResult);
      setPhase("success");
      onSuccess?.(executeResult);
    } catch (caught) {
      setError(caught);
      setPhase("error");
    }
  }

  async function undoCommand() {
    if (!result?.data.command_execution_id || !onUndo) {
      return;
    }
    setPhase("undoing");
    setError(null);
    try {
      const undoResponse = await onUndo(String(result.data.command_execution_id));
      setUndoResult(undoResponse);
      setPhase("undone");
      onUndoSuccess?.(undoResponse);
    } catch (caught) {
      setError(caught);
      setPhase("error");
    }
  }

  const isBusy = phase === "previewing" || phase === "executing" || phase === "undoing";
  const canUndo = Boolean(onUndo && result?.data.undo_plan && result.data.command_execution_id && phase !== "undone");

  return (
    <section className="command-panel">
      <div className="command-rail" aria-hidden="true">
        <span className={preview ? "command-rail__node command-rail__node--done" : "command-rail__node"} />
        <span className={dryRun ? "command-rail__node command-rail__node--done" : "command-rail__node"} />
        <span className={result ? "command-rail__node command-rail__node--done" : "command-rail__node"} />
      </div>

      <div className="command-panel__body">
        <div className="section-heading">
          <p className="eyebrow">Command rail</p>
          <h2>{title}</h2>
          <p>{description}</p>
        </div>

        <div className="command-panel__actions">
          <button className="button button--secondary" type="button" onClick={previewCommand} disabled={disabled || isBusy}>
            {previewLabel}
          </button>
          <button className="button" type="button" onClick={executeCommand} disabled={disabled || phase !== "ready" || isBusy}>
            {executeLabel}
          </button>
        </div>

        {phase === "previewing" ? <LoadingState title="Previewing command" detail="Validating through the backend without persisting changes." /> : null}
        {phase === "executing" ? <LoadingState title="Executing command" detail="Writing through the single-writer backend path." /> : null}
        {phase === "undoing" ? <LoadingState title="Undoing command" detail="Rehydrating compensation from the audit record and applying it." /> : null}
        {phase === "error" && error ? <ErrorState error={error} /> : null}

        {preview ? (
          <div className="command-result">
            <h3>{preview.data.summary}</h3>
            <DefinitionGrid
              items={[
                ["Command", preview.data.command_type],
                ["Risk", preview.data.risk_level],
                ["Warnings", preview.warnings.join(", ") || "None"]
              ]}
            />
            <pre>{JSON.stringify(preview.data.preview, null, 2)}</pre>
          </div>
        ) : null}

        {dryRun ? (
          <div className="command-result command-result--quiet">
            <h3>Dry-run {dryRun.data.valid ? "passed" : "failed"}</h3>
            <pre>{JSON.stringify(dryRun.data.simulation, null, 2)}</pre>
          </div>
        ) : null}

        {result ? (
          <div className="command-result command-result--success">
            <h3>Imported</h3>
            <DefinitionGrid
              items={[
                ["Execution", String(result.data.command_execution_id)],
                ["Audit", formatAuditRef(result.auditRef) ?? "Not recorded"],
                ["Undo", result.data.undo_plan ? "Undo plan available" : "No undo plan"]
              ]}
            />
            {result.data.undo_plan ? (
              <div className="command-panel__actions">
                <button className="button button--secondary" type="button" onClick={undoCommand} disabled={!canUndo || isBusy}>
                  Undo import
                </button>
                <p className="note">
                  Undo references execution <code>{String(result.data.command_execution_id)}</code>. Atlas rehydrates the
                  compensating action from the stored audit record server-side.
                </p>
              </div>
            ) : null}
          </div>
        ) : null}

        {undoResult ? (
          <div className="command-result command-result--success">
            <h3>Undo completed</h3>
            <DefinitionGrid
              items={[
                ["Execution", String(undoResult.data.command_execution_id)],
                ["Audit", formatAuditRef(undoResult.auditRef) ?? "Not recorded"],
                ["Status", String(undoResult.data.status ?? "archived")]
              ]}
            />
          </div>
        ) : null}
      </div>
    </section>
  );
}

function DefinitionGrid({ items }: { items: Array<[string, string]> }) {
  return (
    <dl className="definition-grid">
      {items.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}
