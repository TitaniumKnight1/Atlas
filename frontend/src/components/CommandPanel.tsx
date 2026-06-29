import { useState } from "react";

import type { BackendResponse } from "../api/backend";
import { formatAuditRef, type CommandResultData, type DryRunData, type CommandPreviewData } from "../api/project";
import { Alert, Badge, Button, type BadgeVariant } from ".";
import { buildCommandSummary, buildTechnicalPayload } from "./commandSummaries";
import { ErrorState, LoadingState } from "./StateViews";
import { TechnicalDetails } from "./TechnicalDetails";

interface CommandPanelProps {
  title: string;
  description: string;
  previewLabel?: string;
  executeLabel: string;
  disabled?: boolean;
  /** guided: human summary + collapsed JSON (wizard). detailed: legacy debug-first layout. */
  presentation?: "guided" | "detailed";
  onPreview: () => Promise<BackendResponse<CommandPreviewData>>;
  onDryRun: () => Promise<BackendResponse<DryRunData>>;
  onExecute: () => Promise<BackendResponse<CommandResultData>>;
  onUndo?: (commandExecutionId: string) => Promise<BackendResponse<CommandResultData>>;
  onSuccess?: (result: BackendResponse<CommandResultData>) => void;
  onUndoSuccess?: (result: BackendResponse<CommandResultData>) => void;
}

type Phase = "idle" | "previewing" | "ready" | "executing" | "success" | "undoing" | "undone" | "error";
type CommandStepStatus = "succeeded" | "failed" | "not-attempted" | "held" | "active";

interface CommandPlanStep {
  label: string;
  detail?: string;
  status: CommandStepStatus;
}

export function CommandPanel({
  title,
  description,
  previewLabel = "Preview changes",
  executeLabel,
  disabled,
  presentation = "detailed",
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
  const guided = presentation === "guided";

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
  const commandSteps = buildCommandSteps({ phase, preview: Boolean(preview), dryRun: Boolean(dryRun), result: Boolean(result), canUndo });
  const planSteps = extractPlanSteps(preview?.data.preview) ?? extractPlanSteps(dryRun?.data.simulation) ?? extractPlanSteps(result?.data);
  const compactPreview = preview ? isCompactPayload(preview.data.preview) : false;
  const allWarnings = [...(preview?.warnings ?? []), ...(dryRun && !dryRun.data.valid ? ["Dry-run validation failed"] : [])];

  return (
    <section className={guided ? "command-panel command-panel--guided" : "command-panel"}>
      <div className="command-panel__head">
        <div className="atlas-row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
          <div className="atlas-section-heading">
            <p className="eyebrow">Command rail</p>
            <h2>{title}</h2>
            <p>{description}</p>
          </div>
          {preview ? <Badge variant={riskToVariant(preview.data.risk_level)}>{preview.data.risk_level} risk</Badge> : null}
        </div>
      </div>

      {!guided ? (
        <div className="command-panel__steps" aria-label="Command progress">
          {commandSteps.map((step) => (
            <CommandStep key={step.label} step={step} />
          ))}
        </div>
      ) : preview || phase !== "idle" ? (
        <div className="command-panel__steps" aria-label="Command progress">
          {commandSteps.map((step) => (
            <CommandStep key={step.label} step={step} />
          ))}
        </div>
      ) : null}

      <div className="command-panel__body">
        <div className="command-panel__actions">
          <Button type="button" variant="secondary" onClick={previewCommand} disabled={disabled || isBusy} loading={phase === "previewing"}>
            {previewLabel}
          </Button>
          <Button
            type="button"
            variant="primary"
            onClick={executeCommand}
            disabled={disabled || phase !== "ready" || isBusy || (dryRun != null && !dryRun.data.valid)}
            loading={phase === "executing"}
          >
            {executeLabel}
          </Button>
        </div>

        {phase === "previewing" ? <LoadingState title="Previewing command" detail="Validating through the backend without persisting changes." /> : null}
        {phase === "executing" ? <LoadingState title="Executing command" detail="Writing through the single-writer backend path." /> : null}
        {phase === "undoing" ? <LoadingState title="Undoing command" detail="Rehydrating compensation from the audit record and applying it." /> : null}
        {phase === "error" && error ? <ErrorState error={error} /> : null}

        {guided && preview ? (
          <GuidedPreviewResult dryRun={dryRun} preview={preview} warnings={allWarnings} />
        ) : null}

        {!guided && preview ? (
          <div className={compactPreview ? "command-result command-result--compact" : "command-result"}>
            <div>
              <h3>{preview.data.summary}</h3>
              <p className="muted-copy">Review what Atlas detected before writing anything.</p>
            </div>
            <DefinitionGrid
              items={[
                ["Command", preview.data.command_type],
                ["Risk", preview.data.risk_level],
                ["Warnings", preview.warnings.join(", ") || "None"]
              ]}
            />
            {!compactPreview ? <pre className="command-json">{JSON.stringify(preview.data.preview, null, 2)}</pre> : null}
          </div>
        ) : null}

        {!guided && planSteps && planSteps.length > 0 ? (
          <div className="command-result command-result--warning">
            <div>
              <h3>Plan steps</h3>
              <p className="muted-copy">Complex commands can stop and hold when a step fails or needs approval.</p>
            </div>
            <div className="command-plan">
              {planSteps.map((step, index) => (
                <div className="command-plan__item" key={`${step.label}-${index}`}>
                  <CommandStep step={step} />
                  <span>
                    <strong>{step.label}</strong>
                    {step.detail ? <span className="muted-copy">{step.detail}</span> : null}
                  </span>
                  <Badge variant={step.status === "failed" ? "danger" : step.status === "held" ? "warn" : step.status === "succeeded" ? "success" : "neutral"}>
                    {formatStepStatus(step.status)}
                  </Badge>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {!guided && dryRun ? (
          <div className={dryRun.data.valid ? "command-result command-result--success" : "command-result command-result--warning"}>
            <h3>Dry-run {dryRun.data.valid ? "passed" : "failed"}</h3>
            <Alert severity={dryRun.data.valid ? "success" : "warn"} title={dryRun.data.valid ? "Safe to execute" : "Hold before execute"}>
              {dryRun.data.valid
                ? "Atlas simulated the command without persisting changes."
                : "Resolve the dry-run findings before executing the command."}
            </Alert>
            <pre className="command-json">{JSON.stringify(dryRun.data.simulation, null, 2)}</pre>
          </div>
        ) : null}

        {result ? (
          <div className="command-result command-result--success">
            <h3>Executed</h3>
            <DefinitionGrid
              items={[
                ["Execution", String(result.data.command_execution_id)],
                ["Audit", formatAuditRef(result.auditRef) ?? "Not recorded"],
                ["Undo", result.data.undo_plan ? "Undo plan available" : "No undo plan"]
              ]}
            />
            {result.data.undo_plan ? (
              <div className="command-panel__actions">
                <Button type="button" variant="secondary" onClick={undoCommand} disabled={!canUndo || isBusy} loading={phase === "undoing"}>
                  Undo
                </Button>
                {!guided ? (
                  <p className="note">
                    Undo references execution <code>{String(result.data.command_execution_id)}</code>. Atlas rehydrates the
                    compensating action from the stored audit record server-side.
                  </p>
                ) : null}
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

function GuidedPreviewResult({
  preview,
  dryRun,
  warnings
}: {
  preview: BackendResponse<CommandPreviewData>;
  dryRun: BackendResponse<DryRunData> | null;
  warnings: string[];
}) {
  const summaryLines = buildCommandSummary({
    preview: preview.data,
    dryRun: dryRun?.data ?? null,
    warnings: preview.warnings
  });
  const blocked = dryRun != null && !dryRun.data.valid;
  const technicalPayload = buildTechnicalPayload(preview.data.preview, dryRun?.data ?? null, warnings);

  return (
    <div className={blocked ? "command-result command-result--warning" : "command-result"}>
      {blocked ? (
        <Alert severity="warn" title="Hold before execute">
          Resolve the dry-run findings before executing this command.
        </Alert>
      ) : dryRun ? (
        <Alert severity="success" title="Safe to execute">
          Atlas simulated this command without persisting changes.
        </Alert>
      ) : null}
      {warnings.length > 0 && !blocked ? (
        <Alert severity="warn" title="Review warnings">
          {warnings.join(" ")}
        </Alert>
      ) : null}
      <ul className="command-summary">
        {summaryLines.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      <TechnicalDetails summary="Show raw command payload">
        <pre className="command-json">{JSON.stringify(technicalPayload, null, 2)}</pre>
      </TechnicalDetails>
    </div>
  );
}

function DefinitionGrid({ items }: { items: Array<[string, string]> }) {
  return <DefinitionGridBase items={items} />;
}

function DefinitionGridBase({ items }: { items: Array<[string, string]> }) {
  return (
    <dl className="atlas-definition-grid">
      {items.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function CommandStep({ step }: { step: CommandPlanStep }) {
  const className =
    step.status === "succeeded"
      ? "command-step command-step--done"
      : step.status === "active"
        ? "command-step command-step--active"
        : step.status === "failed"
          ? "command-step command-step--failed"
          : step.status === "held"
            ? "command-step command-step--held"
            : "command-step";

  return (
    <span className={className}>
      <span className="command-step__mark" aria-hidden="true">
        {step.status === "succeeded" ? "ok" : step.status === "failed" ? "x" : step.status === "held" ? "!" : ""}
      </span>
      {step.label}
    </span>
  );
}

function buildCommandSteps(input: { phase: Phase; preview: boolean; dryRun: boolean; result: boolean; canUndo: boolean }): CommandPlanStep[] {
  return [
    { label: "Preview", status: input.preview ? "succeeded" : input.phase === "previewing" ? "active" : "not-attempted" },
    { label: "Dry-run", status: input.dryRun ? "succeeded" : input.phase === "previewing" ? "active" : "not-attempted" },
    {
      label: "Execute",
      status: input.result ? "succeeded" : input.phase === "executing" ? "active" : input.phase === "ready" ? "held" : "not-attempted"
    },
    {
      label: "Undo",
      status: input.phase === "undone" ? "succeeded" : input.phase === "undoing" ? "active" : input.canUndo ? "held" : "not-attempted"
    }
  ];
}

function riskToVariant(risk: string): BadgeVariant {
  const normalized = risk.toLowerCase();
  if (normalized.includes("high") || normalized.includes("danger")) {
    return "danger";
  }
  if (normalized.includes("medium") || normalized.includes("warn")) {
    return "warn";
  }
  return "info";
}

function isCompactPayload(payload: Record<string, unknown>) {
  const values = Object.values(payload);
  return values.length <= 2 && values.every((value) => value === null || ["string", "number", "boolean"].includes(typeof value));
}

function extractPlanSteps(payload: Record<string, unknown> | undefined | null): CommandPlanStep[] | undefined {
  if (!payload) {
    return undefined;
  }
  const candidates = ["steps", "plan_steps", "rollback_steps", "operations", "plan", "ordered_items", "outcomes"];
  for (const key of candidates) {
    const value = payload[key];
    if (Array.isArray(value)) {
      const steps = value.map(toCommandPlanStep).filter((step): step is CommandPlanStep => Boolean(step));
      if (steps.length > 0) {
        return steps;
      }
    }
  }
  return undefined;
}

function toCommandPlanStep(value: unknown): CommandPlanStep | undefined {
  if (!value || typeof value !== "object") {
    return undefined;
  }
  const record = value as Record<string, unknown>;
  const label = String(record.label ?? record.name ?? record.resource_name ?? record.operation ?? record.action ?? record.step ?? "Step");
  const detailValue = record.detail ?? record.description ?? record.reason ?? record.path;
  const rawStatus = String(record.status ?? record.state ?? "not-attempted").toLowerCase();
  return {
    label,
    detail: detailValue ? String(detailValue) : undefined,
    status: normalizeStepStatus(rawStatus)
  };
}

function normalizeStepStatus(status: string): CommandStepStatus {
  if (["success", "succeeded", "done", "completed", "applied"].includes(status)) {
    return "succeeded";
  }
  if (["failed", "error", "blocked"].includes(status)) {
    return "failed";
  }
  if (["held", "hold", "pending-approval", "pending_approval", "needs-approval", "needs_approval"].includes(status)) {
    return "held";
  }
  if (["running", "active", "executing"].includes(status)) {
    return "active";
  }
  return "not-attempted";
}

function formatStepStatus(status: CommandStepStatus) {
  if (status === "not-attempted") {
    return "not attempted";
  }
  return status;
}
