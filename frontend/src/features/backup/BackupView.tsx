import { useCallback, useEffect, useMemo, useState } from "react";

import {
  createBackupPlan,
  updateBackupPlan,
  evaluateRetention,
  executeRestore,
  getBackupRun,
  listBackupPlans,
  listBackupRuns,
  previewRestore,
  runBackup,
  undoRestore,
  type BackupPlan,
  type BackupRun,
  type RestorePreview,
  type RestoreResult
} from "../../api/backup";
import type { BackendResponse } from "../../api/backend";
import {
  Alert,
  ApprovalPrompt,
  Badge,
  Button,
  Field,
  Input,
  ProgressBar,
  ProjectPicker,
  SectionHeading,
  Select,
  StatusPill,
  Surface,
  Table,
  Tabs,
  Toast,
  type StatusKind
} from "../../components";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { useActiveProjectSelection } from "../../components/useActiveProjects";
import { useProjectStream } from "../../components/useProjectStream";
import { useBackendStatus } from "../../app/useBackendStatus";

type BackupTab = "backups" | "restore" | "retention";

function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null || bytes <= 0) {
    return "—";
  }
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function backupStatusKind(status: string): StatusKind {
  if (status === "succeeded") {
    return "running";
  }
  if (status === "failed") {
    return "crashed";
  }
  if (status === "running") {
    return "pending";
  }
  return "idle";
}

function consistencyWarning(run: BackupRun): string | null {
  const manifest = run.manifest_json;
  if (!manifest || typeof manifest !== "object") {
    return null;
  }
  const consistency = (manifest as Record<string, unknown>).consistency;
  if (!consistency || typeof consistency !== "object") {
    return null;
  }
  const warning = (consistency as Record<string, unknown>).warning;
  return warning ? String(warning) : null;
}

export function BackupView() {
  const backendStatus = useBackendStatus();
  const { resource: projectsResource, projects, selectedProjectId, setSelectedProjectId, removeProject } = useActiveProjectSelection();
  const [activeTab, setActiveTab] = useState<BackupTab>("backups");
  const [plans, setPlans] = useState<BackupPlan[]>([]);
  const [runs, setRuns] = useState<BackupRun[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [toast, setToast] = useState<{ title: string; detail?: string; severity?: "info" | "success" | "warn" } | null>(null);
  const [mutationTick, setMutationTick] = useState(0);

  const [selectedPlanId, setSelectedPlanId] = useState<string>("");
  const [createBusy, setCreateBusy] = useState(false);
  const [createWarnings, setCreateWarnings] = useState<string[]>([]);

  const [restoreBackupId, setRestoreBackupId] = useState<string>("");
  const [restorePreview, setRestorePreview] = useState<BackendResponse<RestorePreview> | null>(null);
  const [restorePreviewBusy, setRestorePreviewBusy] = useState(false);
  const [restoreConfirmOpen, setRestoreConfirmOpen] = useState(false);
  const [restoreAcknowledged, setRestoreAcknowledged] = useState(false);
  const [restoreBusy, setRestoreBusy] = useState(false);
  const [lastRestore, setLastRestore] = useState<RestoreResult | null>(null);
  const [undoBusy, setUndoBusy] = useState(false);
  const [forceDestructive, setForceDestructive] = useState(false);

  const [retentionKeepCount, setRetentionKeepCount] = useState("5");
  const [retentionKeepDays, setRetentionKeepDays] = useState("30");
  const [retentionPlanName, setRetentionPlanName] = useState("Default retention");
  const [retentionBusy, setRetentionBusy] = useState(false);
  const [retentionResult, setRetentionResult] = useState<{ pruned: string[]; skipped: string[]; evaluated: number } | null>(null);

  const [longOpActive, setLongOpActive] = useState(false);

  const { events: streamEvents, connected: streamConnected } = useProjectStream(selectedProjectId, ["op-progress"]);

  const reload = useCallback(async () => {
    if (!selectedProjectId) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [planRows, runRows] = await Promise.all([listBackupPlans(selectedProjectId), listBackupRuns(selectedProjectId)]);
      setPlans(planRows);
      setRuns(runRows);
      if (!selectedPlanId && planRows.length > 0) {
        setSelectedPlanId(planRows[0].backup_plan_id);
      }
      const succeeded = runRows.filter((run) => run.status === "succeeded");
      if (!restoreBackupId && succeeded.length > 0) {
        setRestoreBackupId(succeeded[0].backup_run_id);
      }
    } catch (caught) {
      setError(caught);
    } finally {
      setLoading(false);
    }
  }, [selectedProjectId, selectedPlanId, restoreBackupId]);

  useEffect(() => {
    void reload();
  }, [reload, mutationTick]);

  const latestProgress = useMemo(() => {
    const events = streamEvents.filter((event) => event.topic === "op-progress" && event.event_type === "OperationProgress");
    return events.length > 0 ? events[events.length - 1] : undefined;
  }, [streamEvents]);

  const opProgress = latestProgress
    ? {
        percent: Number(latestProgress.payload.percent ?? latestProgress.payload.progress ?? 0),
        message: String(latestProgress.payload.message ?? "Backup operation in progress…")
      }
    : null;

  useEffect(() => {
    if (opProgress && opProgress.percent >= 100) {
      setLongOpActive(false);
      setMutationTick((value) => value + 1);
    }
  }, [opProgress?.percent]);

  const succeededBackups = runs.filter((run) => run.status === "succeeded");
  const primaryPlan = plans[0] ?? null;
  const notCleanlyReversible = restorePreview?.data.requires_pre_restore_snapshot === false || lastRestore?.undo_available === false;

  function bumpMutation() {
    setMutationTick((value) => value + 1);
  }

  async function handleCreateBackup() {
    if (!selectedProjectId) {
      return;
    }
    setCreateBusy(true);
    setCreateWarnings([]);
    setLongOpActive(true);
    setError(null);
    try {
      const response = await runBackup(selectedProjectId, selectedPlanId || null);
      const warnings = [...response.warnings];
      const detail = await getBackupRun(selectedProjectId, response.data.backup_run_id);
      const consistency = consistencyWarning(detail);
      if (consistency) {
        warnings.push(consistency);
      }
      setCreateWarnings(warnings);
      setToast({
        title: "Backup started",
        detail: warnings.length > 0 ? warnings.join(" ") : "Capture running — watch op-progress below.",
        severity: warnings.length > 0 ? "warn" : "success"
      });
      bumpMutation();
    } catch (caught) {
      setLongOpActive(false);
      setError(caught);
    } finally {
      setCreateBusy(false);
    }
  }

  async function handleRestorePreview() {
    if (!selectedProjectId || !restoreBackupId) {
      return;
    }
    setRestorePreviewBusy(true);
    setRestorePreview(null);
    setError(null);
    try {
      const preview = await previewRestore(selectedProjectId, restoreBackupId);
      setRestorePreview(preview);
      setActiveTab("restore");
    } catch (caught) {
      setError(caught);
    } finally {
      setRestorePreviewBusy(false);
    }
  }

  async function handleRestoreExecute() {
    if (!selectedProjectId || !restoreBackupId) {
      return;
    }
    setRestoreBusy(true);
    setLongOpActive(true);
    setError(null);
    try {
      const result = await executeRestore(selectedProjectId, restoreBackupId, forceDestructive || notCleanlyReversible);
      setLastRestore(result);
      setRestoreConfirmOpen(false);
      setRestoreAcknowledged(false);
      setToast({
        title: "Restore executing",
        detail: result.undo_available === false ? "Undo may not be available — pre-restore snapshot failed." : "Pre-restore snapshot captured; undo is available.",
        severity: result.undo_available === false ? "warn" : "success"
      });
      bumpMutation();
    } catch (caught) {
      setLongOpActive(false);
      setError(caught);
    } finally {
      setRestoreBusy(false);
    }
  }

  async function handleRestoreUndo() {
    if (!selectedProjectId || !lastRestore?.restore_run_id) {
      return;
    }
    setUndoBusy(true);
    try {
      await undoRestore(selectedProjectId, lastRestore.restore_run_id);
      setToast({ title: "Restore undone", detail: "Project returned to pre-restore snapshot.", severity: "success" });
      setLastRestore(null);
      bumpMutation();
    } catch (caught) {
      setError(caught);
    } finally {
      setUndoBusy(false);
    }
  }

  async function handleCreateRetentionPlan() {
    if (!selectedProjectId) {
      return;
    }
    setRetentionBusy(true);
    setError(null);
    try {
      if (selectedPlanId || primaryPlan?.backup_plan_id) {
        const planId = selectedPlanId || primaryPlan?.backup_plan_id;
        await updateBackupPlan(selectedProjectId, planId!, {
          retention_policy: {
            keep_count: Number(retentionKeepCount) || undefined,
            keep_days: Number(retentionKeepDays) || undefined
          },
          is_enabled: true
        });
        setToast({ title: "Retention plan updated", detail: "Existing plan updated with new policy.", severity: "info" });
      } else {
        await createBackupPlan(selectedProjectId, {
          name: retentionPlanName,
          backup_scope: "full_project",
          retention_policy: {
            keep_count: Number(retentionKeepCount) || undefined,
            keep_days: Number(retentionKeepDays) || undefined
          },
          is_enabled: true
        });
        setToast({ title: "Retention plan created", detail: "New plan added with updated policy.", severity: "info" });
      }
      bumpMutation();
    } catch (caught) {
      setError(caught);
    } finally {
      setRetentionBusy(false);
    }
  }

  async function handleEvaluateRetention() {
    if (!selectedProjectId) {
      return;
    }
    setRetentionBusy(true);
    try {
      const result = await evaluateRetention(selectedProjectId, selectedPlanId || primaryPlan?.backup_plan_id || null);
      setRetentionResult(result);
      setToast({
        title: "Retention evaluated",
        detail: result.skipped.length > 0 ? `Skipped ${result.skipped.length} backup(s) — last-backup guard.` : "Evaluation complete.",
        severity: result.skipped.length > 0 ? "warn" : "info"
      });
    } catch (caught) {
      setError(caught);
    } finally {
      setRetentionBusy(false);
    }
  }

  if (backendStatus.state !== "ready") {
    return <LoadingState title="Waiting for backend" detail="Backup controls require a connected Atlas backend." />;
  }

  if (projectsResource.state === "loading") {
    return <LoadingState title="Loading projects" detail="Fetching workspace list for backup context." />;
  }

  if (projects.length === 0) {
    return <EmptyState title="No projects yet" detail="Import a project before creating backups or configuring retention." />;
  }

  return (
    <div className="atlas-feature">
      {toast ? (
        <Toast severity={toast.severity ?? "info"} title={toast.title} onDismiss={() => setToast(null)}>
          {toast.detail ?? ""}
        </Toast>
      ) : null}

      <div className="atlas-row" style={{ justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "var(--space-3)" }}>
        <SectionHeading eyebrow="Operate" title="Backup" detail="On-demand capture, destructive restore with undo, and retention policy." />
        <ProjectPicker projects={projects} selectedProjectId={selectedProjectId} onSelect={setSelectedProjectId} onRemove={removeProject} />
      </div>

      {longOpActive && opProgress ? (
        <Surface>
          <ProgressBar label={opProgress.message} value={opProgress.percent} />
          {!streamConnected ? <p className="muted-copy">Reconnecting to op-progress stream…</p> : null}
        </Surface>
      ) : null}

      <Tabs
        activeId={activeTab}
        ariaLabel="Backup views"
        tabs={[
          { id: "backups", label: "Backups" },
          { id: "restore", label: "Restore" },
          { id: "retention", label: "Retention" }
        ]}
        onChange={(id) => setActiveTab(id as BackupTab)}
      />

      {error ? <ErrorState error={error} /> : null}
      {loading ? <LoadingState title="Loading backup data" detail="Fetching plans and backup runs." /> : null}

      {!loading && activeTab === "backups" ? (
        <div className="atlas-stack" style={{ gap: "var(--space-4)" }}>
          <Surface>
            <SectionHeading title="On-demand backup" detail="Backups taken while the server is running may be best-effort — the backend surfaces consistency warnings honestly." />
            <div className="atlas-stack" style={{ gap: "var(--space-3)" }}>
              <Field hint="Optional — uses default scope when empty." label="Backup plan">
                <Select value={selectedPlanId} onChange={(event) => setSelectedPlanId(event.target.value)}>
                  <option value="">Default (no plan)</option>
                  {plans.map((plan) => (
                    <option key={plan.backup_plan_id} value={plan.backup_plan_id}>
                      {plan.name}
                    </option>
                  ))}
                </Select>
              </Field>
              <Button loading={createBusy} variant="primary" onClick={() => void handleCreateBackup()}>
                Create backup now
              </Button>
              {createWarnings.length > 0 ? (
                <Alert severity="warn" title="Consistency warning">
                  {createWarnings.join(" ")}
                </Alert>
              ) : null}
            </div>
          </Surface>

          <Surface>
            <SectionHeading title="Backup history" detail="Size, timestamp, scope, and checksum for each capture." />
            {runs.length === 0 ? (
              <EmptyState title="No backups yet" detail="Create your first on-demand backup to protect project state." />
            ) : (
              <Table>
                <thead>
                  <tr>
                    <th>Timestamp</th>
                    <th>Status</th>
                    <th>Size</th>
                    <th>Scope</th>
                    <th>Checksum</th>
                    <th>Consistency</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((run) => {
                    const plan = plans.find((item) => item.backup_plan_id === run.backup_plan_id);
                    const warning = consistencyWarning(run);
                    return (
                      <tr key={run.backup_run_id}>
                        <td>{new Date(run.started_at).toLocaleString()}</td>
                        <td>
                          <StatusPill status={backupStatusKind(run.status)}>{run.status}</StatusPill>
                        </td>
                        <td>{formatBytes(run.total_bytes)}</td>
                        <td>{plan?.backup_scope ?? "—"}</td>
                        <td>
                          <code>{run.content_hash ? `${run.content_hash.slice(0, 12)}…` : "—"}</code>
                        </td>
                        <td>
                          {warning ? <Badge variant="warn">best_effort</Badge> : <Badge variant="success">consistent</Badge>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </Table>
            )}
          </Surface>
        </div>
      ) : null}

      {!loading && activeTab === "restore" ? (
        <div className="atlas-stack" style={{ gap: "var(--space-4)" }}>
          <Surface>
            <SectionHeading
              title="Restore preview"
              detail="Your current project state will be overwritten. Atlas snapshots pre-restore state so you can undo when the snapshot succeeds."
            />
            <div className="atlas-stack" style={{ gap: "var(--space-3)" }}>
              <Field label="Backup to restore">
                <Select value={restoreBackupId} onChange={(event) => setRestoreBackupId(event.target.value)}>
                  {succeededBackups.length === 0 ? <option value="">No succeeded backups</option> : null}
                  {succeededBackups.map((run) => (
                    <option key={run.backup_run_id} value={run.backup_run_id}>
                      {new Date(run.started_at).toLocaleString()} — {formatBytes(run.total_bytes)}
                    </option>
                  ))}
                </Select>
              </Field>
              <Button disabled={!restoreBackupId} loading={restorePreviewBusy} variant="secondary" onClick={() => void handleRestorePreview()}>
                Preview overwrite
              </Button>
            </div>
          </Surface>

          {restorePreview ? (
            <Surface>
              <SectionHeading title="Overwrite summary" detail={`${restorePreview.data.overwrite_paths.length} path(s) will be replaced.`} />
              {restorePreview.warnings.length > 0 ? (
                <Alert severity="warn" title="Restore warnings">
                  {restorePreview.warnings.join(" ")}
                </Alert>
              ) : null}
              {notCleanlyReversible ? (
                <Alert severity="danger" title="Not cleanly reversible">
                  Pre-restore snapshot may fail. You must explicitly confirm destructive restore — undo may be unavailable.
                </Alert>
              ) : null}
              <pre className="atlas-code-block" style={{ maxHeight: "240px", overflow: "auto" }}>
                {(restorePreview.data.overwrite_paths.slice(0, 50).join("\n") || "No paths returned.") +
                  (restorePreview.data.overwrite_paths.length > 50 ? `\n… and ${restorePreview.data.overwrite_paths.length - 50} more` : "")}
              </pre>
              <div className="atlas-row" style={{ gap: "var(--space-2)", marginTop: "var(--space-3)" }}>
                <Button
                  variant="danger"
                  onClick={() => {
                    setRestoreConfirmOpen(true);
                    setRestoreAcknowledged(false);
                    setForceDestructive(notCleanlyReversible);
                  }}
                >
                  Review &amp; execute restore
                </Button>
                {lastRestore?.restore_run_id && lastRestore.undo_available !== false ? (
                  <Button loading={undoBusy} variant="secondary" onClick={() => void handleRestoreUndo()}>
                    Undo last restore
                  </Button>
                ) : null}
              </div>
            </Surface>
          ) : null}
        </div>
      ) : null}

      {!loading && activeTab === "retention" ? (
        <div className="atlas-stack" style={{ gap: "var(--space-4)" }}>
          <Surface>
            <SectionHeading
              title="Current retention policies"
              detail="Review and update existing backup plans."
            />
            {plans.length === 0 ? (
              <EmptyState title="No backup plans" detail="Create a plan below to define retention keep count and days." />
            ) : (
              <Table>
                <thead>
                  <tr>
                    <th>Plan</th>
                    <th>Keep count</th>
                    <th>Keep days</th>
                    <th>Enabled</th>
                  </tr>
                </thead>
                <tbody>
                  {plans.map((plan) => (
                    <tr key={plan.backup_plan_id}>
                      <td>{plan.name}</td>
                      <td>{plan.retention_policy?.keep_count ?? "—"}</td>
                      <td>{plan.retention_policy?.keep_days ?? "—"}</td>
                      <td>
                        <Badge variant={plan.is_enabled ? "success" : "neutral"}>{plan.is_enabled ? "Yes" : "No"}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </Surface>

          <Surface>
            <SectionHeading title="Update or Create plan" detail="The last-backup guard prevents silently pruning the only remaining backup during evaluate." />
            <div className="atlas-stack" style={{ gap: "var(--space-3)" }}>
              <Field label="Plan name">
                <Input value={retentionPlanName} onChange={(event) => setRetentionPlanName(event.target.value)} />
              </Field>
              <div className="atlas-row" style={{ gap: "var(--space-3)" }}>
                <Field label="Keep count">
                  <Input type="number" min={1} value={retentionKeepCount} onChange={(event) => setRetentionKeepCount(event.target.value)} />
                </Field>
                <Field label="Keep days">
                  <Input type="number" min={1} value={retentionKeepDays} onChange={(event) => setRetentionKeepDays(event.target.value)} />
                </Field>
              </div>
              <div className="atlas-row" style={{ gap: "var(--space-2)" }}>
                <Button loading={retentionBusy} variant="primary" onClick={() => void handleCreateRetentionPlan()}>
                  {selectedPlanId || primaryPlan?.backup_plan_id ? "Update plan" : "Create plan"}
                </Button>
                <Button loading={retentionBusy} variant="secondary" onClick={() => void handleEvaluateRetention()}>
                  Evaluate retention now
                </Button>
              </div>
              {retentionResult ? (
                <Alert severity={retentionResult.skipped.length > 0 ? "warn" : "info"} title="Last evaluation">
                  Evaluated {retentionResult.evaluated} backup(s). Pruned: {retentionResult.pruned.length}. Skipped (last-backup guard):{" "}
                  {retentionResult.skipped.length}.
                </Alert>
              ) : null}
            </div>
          </Surface>
        </div>
      ) : null}

      {restoreConfirmOpen ? (
        <ApprovalPrompt
          acknowledged={restoreAcknowledged}
          confirmLabel={restoreBusy ? "Restoring…" : "Overwrite and restore"}
          detail="This will overwrite your current project files with backup contents. A pre-restore snapshot is taken when possible so you can undo."
          title="Confirm destructive restore"
          onAcknowledge={setRestoreAcknowledged}
          onCancel={() => {
            setRestoreConfirmOpen(false);
            setRestoreAcknowledged(false);
          }}
          onApprove={() => void handleRestoreExecute()}
        >
          {restorePreview ? (
            <>
              <p>
                <strong>{restorePreview.data.overwrite_paths.length}</strong> paths under <code>{restorePreview.data.project_root}</code> will be overwritten.
              </p>
              {restorePreview.warnings.map((warning) => (
                <Alert key={warning} severity="warn" title="Warning">
                  {warning}
                </Alert>
              ))}
              {notCleanlyReversible ? (
                <Alert severity="danger" title="Undo may be unavailable">
                  Snapshot capture failed or is not guaranteed. Proceed only if you accept potential irreversibility.
                </Alert>
              ) : null}
            </>
          ) : null}
        </ApprovalPrompt>
      ) : null}
    </div>
  );
}
