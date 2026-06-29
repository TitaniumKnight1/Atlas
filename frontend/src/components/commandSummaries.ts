import type { CommandPreviewData, DryRunData } from "../api/project";

export interface CommandSummaryInput {
  preview: CommandPreviewData;
  dryRun?: DryRunData | null;
  warnings?: string[];
}

/** Human-readable bullets for guided command panels — must stay accurate to structured preview data. */
export function buildCommandSummary({ preview, dryRun, warnings = [] }: CommandSummaryInput): string[] {
  const payload = preview.preview;
  const lines: string[] = [];

  switch (preview.command_type) {
    case "AdoptRepository":
      lines.push(...summarizeAdopt(payload, preview.summary));
      break;
    case "PlanRepoNormalization":
      lines.push(...summarizeNormalization(payload, preview.summary));
      break;
    case "PlanSecretSubstitution":
      lines.push(...summarizeSecretSubstitution(payload, preview.summary));
      break;
    case "PlanDevConfigTransform":
      lines.push(...summarizeDevTransform(payload, preview.summary));
      break;
    case "PlanSafeReturnCommit":
      lines.push(...summarizeSafeReturnCommit(payload, preview.summary));
      break;
    case "ProvisionDevDatabase":
      lines.push(...summarizeProvisionDevDatabase(payload, preview.summary));
      break;
    default:
      lines.push(preview.summary);
      break;
  }

  if (dryRun) {
    lines.push(
      dryRun.valid
        ? "Dry-run passed — Atlas simulated this command without persisting changes."
        : "Dry-run blocked — resolve findings before executing."
    );
  }

  for (const warning of warnings) {
    if (warning.trim()) {
      lines.push(`Warning: ${warning}`);
    }
  }

  return lines;
}

export function buildTechnicalPayload(
  preview: Record<string, unknown>,
  dryRun: DryRunData | null | undefined,
  warnings: string[]
): Record<string, unknown> {
  const technical: Record<string, unknown> = { preview };
  if (dryRun && !payloadsEquivalent(preview, dryRun.simulation)) {
    technical.dry_run = dryRun;
  }
  if (warnings.length > 0) {
    technical.warnings = warnings;
  }
  return technical;
}

function summarizeAdopt(payload: Record<string, unknown>, fallback: string): string[] {
  const scorecard = payload.structure_scorecard as Record<string, unknown> | undefined;
  if (!scorecard) {
    return [fallback];
  }
  const checks = (scorecard.checks as Record<string, { present: boolean }>) ?? {};
  const present = Object.entries(checks)
    .filter(([, value]) => value.present)
    .map(([key]) => key.replace(/_/g, " "));
  const missing = Object.entries(checks)
    .filter(([, value]) => !value.present)
    .map(([key]) => key.replace(/_/g, " "));
  const lines = [
    scorecard.looks_like_fivem_server
      ? `Atlas detected a FiveM server (confidence: ${String(scorecard.confidence)}).`
      : "Atlas did not confidently detect a FiveM server layout yet."
  ];
  if (present.length) {
    lines.push(`Found: ${present.join(", ")}.`);
  }
  if (missing.length) {
    lines.push(`Missing: ${missing.join(", ")}.`);
  }
  if (scorecard.resource_count != null) {
    lines.push(`Resources scanned: ${String(scorecard.resource_count)}.`);
  }
  if (payload.remote_url) {
    lines.push(`Remote: ${String(payload.remote_url)}.`);
  }
  return lines;
}

function summarizeNormalization(payload: Record<string, unknown>, fallback: string): string[] {
  const meta = payload.normalization as Record<string, unknown> | undefined;
  const inlineSecrets = Array.isArray(payload.inline_secrets) ? payload.inline_secrets : [];
  const endpointsMoved = Array.isArray(meta?.endpoints_moved) ? meta.endpoints_moved.length : 0;
  const secretsCount = Number(meta?.secrets_placeholderized ?? 0);
  const overlayPath = String(payload.overlay_path ?? "server.cfg.local");
  const lines = [fallback];
  if (endpointsMoved > 0) {
    lines.push(`Move ${endpointsMoved} endpoint line(s) to ${overlayPath}.`);
  }
  if (secretsCount > 0) {
    lines.push(`Replace ${secretsCount} inline secret(s) with placeholders in server.cfg.`);
  }
  if (inlineSecrets.length > 0) {
    lines.push(`${inlineSecrets.length} inline secret(s) flagged for substitution in the next step.`);
  }
  lines.push("Append exec trailer for the gitignored overlay if missing. Undo restores server.cfg byte-for-byte.");
  return lines;
}

function summarizeSecretSubstitution(payload: Record<string, unknown>, fallback: string): string[] {
  const slots = Array.isArray(payload.slots) ? payload.slots : [];
  const substitution = payload.substitution as Record<string, unknown> | undefined;
  const lines = [fallback, `Apply ${slots.length} substitution slot(s) to the overlay.`];
  const devRequired = slots.filter((slot) => {
    const record = slot as Record<string, unknown>;
    return String(record.handling_class ?? "").includes("dev");
  }).length;
  if (devRequired > 0) {
    lines.push(`${devRequired} slot(s) may need your dev-only values before running.`);
  }
  if (substitution?.auto_filled != null) {
    lines.push(`Atlas auto-fills ${String(substitution.auto_filled)} safe local default(s).`);
  }
  return lines;
}

function summarizeDevTransform(payload: Record<string, unknown>, fallback: string): string[] {
  const transform = payload.transform as Record<string, unknown> | undefined;
  const lines = [fallback];
  if (transform?.hostname) {
    lines.push(`Hostname → ${String(transform.hostname)}.`);
  }
  if (transform?.max_clients != null) {
    lines.push(`Max clients → ${String(transform.max_clients)}.`);
  }
  if (transform?.udp_port != null || transform?.tcp_port != null) {
    lines.push(`Ports → UDP ${String(transform.udp_port ?? "—")}, TCP ${String(transform.tcp_port ?? "—")}.`);
  }
  const plusSet = Array.isArray(payload.plus_set_overrides) ? payload.plus_set_overrides : [];
  if (plusSet.length > 0) {
    lines.push(`${plusSet.length} launch override(s) via +set when needed.`);
  }
  lines.push("Changes land in server.cfg.local only — tracked server.cfg stays normalized.");
  return lines;
}

function summarizeSafeReturnCommit(payload: Record<string, unknown>, fallback: string): string[] {
  const report = payload.contamination_report as Record<string, unknown> | undefined;
  const paths = Array.isArray(payload.paths) ? payload.paths : [];
  const lines = [fallback, `Commit ${paths.length} explicit path(s) on a feature branch.`];
  if (report) {
    const gate = String(report.gate_status ?? "UNKNOWN");
    const allowed = Boolean(report.allowed);
    lines.push(
      allowed
        ? `Secret gate: ${gate} — safe to commit locally.`
        : `Secret gate: ${gate} — commit blocked until contamination is resolved.`
    );
    const summaryLines = Array.isArray(report.summary_lines) ? report.summary_lines : [];
    for (const line of summaryLines.slice(0, 2)) {
      lines.push(String(line));
    }
  }
  lines.push("Atlas commits locally; you push manually when ready.");
  return lines;
}

function summarizeProvisionDevDatabase(payload: Record<string, unknown>, fallback: string): string[] {
  const plan = payload.plan as Record<string, unknown> | undefined;
  const portCheck = payload.port_check as Record<string, unknown> | undefined;
  const lines = [fallback];
  if (plan) {
    lines.push(`Container: ${String(plan.container_name ?? "atlas-dev-mysql")} on port ${String(plan.port ?? "3306")}.`);
  }
  if (payload.docker_state) {
    lines.push(`Docker: ${String(payload.docker_state)}.`);
  }
  if (portCheck && portCheck.available === false) {
    lines.push(`Port check failed: ${String(portCheck.message ?? "port unavailable")}.`);
  }
  return lines;
}

function payloadsEquivalent(a: Record<string, unknown>, b: Record<string, unknown> | undefined): boolean {
  if (!b) {
    return false;
  }
  try {
    return JSON.stringify(a) === JSON.stringify(b);
  } catch {
    return false;
  }
}
