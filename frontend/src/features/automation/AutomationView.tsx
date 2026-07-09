import { useCallback, useEffect, useMemo, useState } from "react";

import { listProjects } from "../../api/project";
import {
  approveAutomationRun,
  countPendingApprovals,
  getGlobalAutomationSettings,
  instantiateRecipe,
  listAutomationRecipes,
  listAutomationRuns,
  listAutomationWorkflows,
  listPendingApprovals,
  listRecipeInstances,
  rejectAutomationRun,
  runAutomationNow,
  setGlobalAutomationEnabled,
  setWorkflowEnabled,
  type AutomationApproval,
  type AutomationRecipe,
  type AutomationRun,
  type AutomationWorkflow,
  type RecipeInstance
} from "../../api/automation";
import {
  Alert,
  ApprovalPrompt,
  Badge,
  Button,
  Dialog,
  Field,
  ProgressBar,
  ProjectPicker,
  SectionHeading,
  StatusPill,
  Surface,
  Table,
  Tabs,
  Textarea,
  Toast,
  Toggle,
  type StatusKind
} from "../../components";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { useActiveProjectSelection } from "../../components/useActiveProjects";
import { useProjectStream } from "../../components/useProjectStream";
import { useBackendStatus } from "../../app/useBackendStatus";

type AutomationTab = "recipes" | "automations" | "approvals" | "runs";

function tierVariant(tier: string): "success" | "warn" | "neutral" {
  if (tier === "approval_gated") {
    return "warn";
  }
  if (tier === "auto") {
    return "success";
  }
  return "neutral";
}

function runStatusKind(status: string): StatusKind {
  if (status === "succeeded" || status === "completed") {
    return "running";
  }
  if (status === "failed") {
    return "crashed";
  }
  if (status === "pending_approval" || status === "running") {
    return "pending";
  }
  return "idle";
}

function stepStatusKind(status: string): StatusKind {
  if (status === "succeeded") {
    return "running";
  }
  if (status === "failed") {
    return "crashed";
  }
  if (status === "pending_approval") {
    return "pending";
  }
  return "idle";
}

function formatTrigger(triggerType: string): string {
  return triggerType.replace(/_/g, " ");
}

function previewSummary(preview: Record<string, unknown> | null): string {
  if (!preview) {
    return "No preview payload from backend.";
  }
  const summary = preview.summary ?? preview.action_type ?? preview.description;
  return summary ? String(summary) : JSON.stringify(preview, null, 2);
}

export function AutomationView() {
  const backendStatus = useBackendStatus();
  const { resource: projectsResource, projects, selectedProjectId, setSelectedProjectId, removeProject } = useActiveProjectSelection();
  const [activeTab, setActiveTab] = useState<AutomationTab>("approvals");
  const [globalEnabled, setGlobalEnabled] = useState(true);
  const [globalBusy, setGlobalBusy] = useState(false);
  const [recipes, setRecipes] = useState<AutomationRecipe[]>([]);
  const [workflows, setWorkflows] = useState<AutomationWorkflow[]>([]);
  const [instances, setInstances] = useState<RecipeInstance[]>([]);
  const [runs, setRuns] = useState<AutomationRun[]>([]);
  const [pending, setPending] = useState<AutomationApproval[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [mutationTick, setMutationTick] = useState(0);

  const [instantiateRecipeKey, setInstantiateRecipeKey] = useState("");
  const [instantiateParams, setInstantiateParams] = useState("{}");
  const [instantiateBusy, setInstantiateBusy] = useState(false);

  const [approvalTarget, setApprovalTarget] = useState<AutomationApproval | null>(null);
  const [approvalAcknowledged, setApprovalAcknowledged] = useState(false);
  const [approvalBusy, setApprovalBusy] = useState(false);

  const [rejectTarget, setRejectTarget] = useState<AutomationApproval | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [rejectBusy, setRejectBusy] = useState(false);

  const [longOpActive, setLongOpActive] = useState(false);

  const { events: streamEvents, connected: streamConnected } = useProjectStream(selectedProjectId, ["op-progress"]);

  useEffect(() => {
    if (pending.length > 0) {
      setActiveTab((tab) => (tab === "recipes" ? "approvals" : tab));
    }
  }, [pending.length]);

  const reload = useCallback(async () => {
    if (!selectedProjectId) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [settings, recipeRows, workflowRows, instanceRows, runRows, pendingRows] = await Promise.all([
        getGlobalAutomationSettings(),
        listAutomationRecipes(),
        listAutomationWorkflows(selectedProjectId),
        listRecipeInstances(selectedProjectId),
        listAutomationRuns(selectedProjectId),
        listPendingApprovals(selectedProjectId)
      ]);
      setGlobalEnabled(settings.global_enabled);
      setRecipes(recipeRows);
      setWorkflows(workflowRows);
      setInstances(instanceRows);
      setRuns(runRows);
      setPending(pendingRows);
      if (!instantiateRecipeKey && recipeRows.length > 0) {
        setInstantiateRecipeKey(recipeRows[0].recipe_key);
      }
      if (!selectedRunId && runRows.length > 0) {
        setSelectedRunId(runRows[0].automation_run_id);
      }
    } catch (caught) {
      setError(caught);
    } finally {
      setLoading(false);
    }
  }, [selectedProjectId, instantiateRecipeKey, selectedRunId]);

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
        message: String(latestProgress.payload.message ?? "Automation in progress…")
      }
    : null;

  useEffect(() => {
    if (opProgress && opProgress.percent >= 100) {
      setLongOpActive(false);
      setMutationTick((value) => value + 1);
    }
  }, [opProgress?.percent]);

  const instanceByWorkflow = useMemo(() => {
    const map = new Map<string, RecipeInstance>();
    for (const instance of instances) {
      map.set(instance.automation_workflow_id, instance);
    }
    return map;
  }, [instances]);

  const recipeByKey = useMemo(() => {
    const map = new Map<string, AutomationRecipe>();
    for (const recipe of recipes) {
      map.set(recipe.recipe_key, recipe);
    }
    return map;
  }, [recipes]);

  const selectedRun = runs.find((run) => run.automation_run_id === selectedRunId) ?? null;

  function bumpMutation() {
    setMutationTick((value) => value + 1);
  }

  async function toggleGlobalEnabled(enabled: boolean) {
    setGlobalBusy(true);
    try {
      const settings = await setGlobalAutomationEnabled(enabled);
      setGlobalEnabled(settings.global_enabled);
      setToast(enabled ? "Global automation enabled." : "Global kill switch engaged — all automations paused.");
      bumpMutation();
    } catch (caught) {
      setError(caught);
    } finally {
      setGlobalBusy(false);
    }
  }

  async function toggleWorkflow(workflowId: string, enabled: boolean) {
    if (!selectedProjectId) {
      return;
    }
    try {
      await setWorkflowEnabled(selectedProjectId, workflowId, enabled);
      bumpMutation();
    } catch (caught) {
      setError(caught);
    }
  }

  async function handleInstantiateRecipe() {
    if (!selectedProjectId || !instantiateRecipeKey) {
      return;
    }
    setInstantiateBusy(true);
    setError(null);
    try {
      let params: Record<string, unknown> = {};
      if (instantiateParams.trim()) {
        params = JSON.parse(instantiateParams) as Record<string, unknown>;
      }
      await instantiateRecipe(selectedProjectId, instantiateRecipeKey, params, true);
      setToast(`Recipe "${instantiateRecipeKey}" instantiated.`);
      bumpMutation();
    } catch (caught) {
      setError(caught);
    } finally {
      setInstantiateBusy(false);
    }
  }

  async function handleRunNow(workflowId: string) {
    if (!selectedProjectId) {
      return;
    }
    setLongOpActive(true);
    try {
      await runAutomationNow(selectedProjectId, workflowId);
      setToast("Automation run started.");
      bumpMutation();
    } catch (caught) {
      setLongOpActive(false);
      setError(caught);
    }
  }

  async function confirmApprove() {
    if (!selectedProjectId || !approvalTarget) {
      return;
    }
    setApprovalBusy(true);
    try {
      await approveAutomationRun(selectedProjectId, approvalTarget.automation_run_id, approvalTarget.automation_approval_id);
      setToast("Approval granted — gated actions will execute.");
      setApprovalTarget(null);
      setApprovalAcknowledged(false);
      bumpMutation();
    } catch (caught) {
      setError(caught);
    } finally {
      setApprovalBusy(false);
    }
  }

  async function confirmReject() {
    if (!selectedProjectId || !rejectTarget) {
      return;
    }
    setRejectBusy(true);
    try {
      await rejectAutomationRun(selectedProjectId, rejectTarget.automation_run_id, rejectTarget.automation_approval_id, rejectReason || null);
      setToast("Approval rejected — no destructive action taken.");
      setRejectTarget(null);
      setRejectReason("");
      bumpMutation();
    } catch (caught) {
      setError(caught);
    } finally {
      setRejectBusy(false);
    }
  }

  const tabs = [
    { id: "approvals", label: pending.length > 0 ? `Approvals (${pending.length})` : "Approvals" },
    { id: "recipes", label: "Recipes" },
    { id: "automations", label: "Automations" },
    { id: "runs", label: "Runs" }
  ];

  if (backendStatus.state !== "ready") {
    return <LoadingState title="Waiting for backend" detail="Automation controls require a connected Atlas backend." />;
  }

  if (projectsResource.state === "loading") {
    return <LoadingState title="Loading projects" detail="Fetching workspace list for automation context." />;
  }

  if (projects.length === 0) {
    return <EmptyState title="No projects yet" detail="Import a project before configuring automation recipes and workflows." />;
  }

  return (
    <div className="atlas-feature">
      {toast ? (
        <Toast severity="success" title="Automation" onDismiss={() => setToast(null)}>
          {toast}
        </Toast>
      ) : null}

      <div className="atlas-row" style={{ justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "var(--space-3)" }}>
        <SectionHeading eyebrow="Operate" title="Automation" detail="Approval-gated recipes, workflow triggers, and run history." />
        <ProjectPicker projects={projects} selectedProjectId={selectedProjectId} onSelect={setSelectedProjectId} onRemove={removeProject} />
      </div>

      <Surface className={globalEnabled ? undefined : "atlas-card--warn"}>
        <div className="atlas-row" style={{ justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <strong>Global kill switch</strong>
            <p className="muted-copy">When disabled, no automation runs — scheduled, event-driven, or manual.</p>
          </div>
          <Toggle checked={globalEnabled} disabled={globalBusy} onChange={(event) => void toggleGlobalEnabled(event.currentTarget.checked)}>
            {globalEnabled ? "Automations enabled" : "All automations paused"}
          </Toggle>
        </div>
        {!globalEnabled ? (
          <Alert severity="warn" title="Kill switch active">
            All automations are paused until you re-enable the global switch.
          </Alert>
        ) : null}
      </Surface>

      {pending.length > 0 ? (
        <Alert severity="warn" title={`${pending.length} pending approval${pending.length === 1 ? "" : "s"}`}>
          Approval-gated automations are waiting for your decision. Review the plan before approving destructive actions.
        </Alert>
      ) : null}

      {longOpActive && opProgress ? (
        <Surface>
          <ProgressBar label={opProgress.message} value={opProgress.percent} />
          {!streamConnected ? <p className="muted-copy">Reconnecting to op-progress stream…</p> : null}
        </Surface>
      ) : null}

      <Tabs activeId={activeTab} ariaLabel="Automation views" tabs={tabs} onChange={(id) => setActiveTab(id as AutomationTab)} />

      {error ? <ErrorState error={error} /> : null}
      {loading ? <LoadingState title="Loading automation data" detail="Fetching recipes, workflows, runs, and pending approvals." /> : null}

      {!loading && activeTab === "recipes" ? (
        <div className="atlas-stack" style={{ gap: "var(--space-4)" }}>
          <Surface>
            <SectionHeading title="Recipe catalog" detail="Built-in safety tiers: AUTO runs immediately; APPROVAL-GATED pauses for your consent." />
            <Table>
              <thead>
                <tr>
                  <th>Recipe</th>
                  <th>Trigger</th>
                  <th>Actions &amp; tiers</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {recipes.map((recipe) => (
                  <tr key={recipe.recipe_key}>
                    <td>
                      <strong>{recipe.name}</strong>
                      <p className="muted-copy">{recipe.description}</p>
                    </td>
                    <td>{formatTrigger(recipe.trigger_type)}</td>
                    <td>
                      <ul className="atlas-stack" style={{ gap: "var(--space-1)", listStyle: "none", padding: 0, margin: 0 }}>
                        {recipe.actions.map((action) => (
                          <li key={`${recipe.recipe_key}-${action.action_type}`} className="atlas-row" style={{ gap: "var(--space-2)" }}>
                            <span>{action.action_type.replace(/_/g, " ")}</span>
                            <Badge variant={tierVariant(action.execution_tier)}>{action.execution_tier === "approval_gated" ? "APPROVAL" : "AUTO"}</Badge>
                            {action.deferred ? <Badge variant="neutral">deferred</Badge> : null}
                          </li>
                        ))}
                      </ul>
                    </td>
                    <td>
                      <Badge variant={recipe.instantiation_status === "available" ? "success" : "warn"}>{recipe.instantiation_status}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Surface>

          <Surface>
            <SectionHeading title="Instantiate recipe" detail="Create a project workflow from a catalog recipe with optional parameters." />
            <div className="atlas-stack" style={{ gap: "var(--space-3)" }}>
              <label className="atlas-field">
                <span>Recipe</span>
                <select value={instantiateRecipeKey} onChange={(event) => setInstantiateRecipeKey(event.target.value)}>
                  {recipes.map((recipe) => (
                    <option key={recipe.recipe_key} value={recipe.recipe_key}>
                      {recipe.name}
                    </option>
                  ))}
                </select>
              </label>
              <Field label="Parameters (JSON)">
                <Textarea value={instantiateParams} onChange={(event) => setInstantiateParams(event.target.value)} rows={4} />
              </Field>
              <Button variant="primary" loading={instantiateBusy} onClick={() => void handleInstantiateRecipe()}>
                Instantiate for project
              </Button>
            </div>
          </Surface>
        </div>
      ) : null}

      {!loading && activeTab === "automations" ? (
        <Surface>
          <SectionHeading
            title="Project automations"
            detail="Enabled workflows and their triggers. Trigger details come from recipe instances — workflow list API does not include trigger metadata."
          />
          {workflows.length === 0 ? (
            <EmptyState title="No automations yet" detail="Instantiate a recipe from the catalog to create your first workflow." />
          ) : (
            <Table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Trigger</th>
                  <th>Enabled</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {workflows.map((workflow) => {
                  const instance = instanceByWorkflow.get(workflow.automation_workflow_id);
                  const recipe = instance ? recipeByKey.get(instance.recipe_key) : undefined;
                  const triggerLabel = recipe ? formatTrigger(recipe.trigger_type) : workflow.description?.replace(/^recipe:/, "") ?? "—";
                  return (
                    <tr key={workflow.automation_workflow_id}>
                      <td>
                        <strong>{workflow.name}</strong>
                        {instance ? <p className="muted-copy">Recipe: {instance.recipe_key}</p> : null}
                      </td>
                      <td>{triggerLabel}</td>
                      <td>
                        <Toggle
                          checked={workflow.is_enabled && globalEnabled}
                          disabled={!globalEnabled}
                          onChange={(event) => void toggleWorkflow(workflow.automation_workflow_id, event.currentTarget.checked)}
                        >
                          {workflow.is_enabled ? "On" : "Off"}
                        </Toggle>
                      </td>
                      <td>
                        <Button variant="secondary" disabled={!globalEnabled || !workflow.is_enabled} onClick={() => void handleRunNow(workflow.automation_workflow_id)}>
                          Run now
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          )}
        </Surface>
      ) : null}

      {!loading && activeTab === "approvals" ? (
        <Surface>
          <SectionHeading title="Pending approval queue" detail="Review the automation plan before approving destructive or gated actions." />
          {pending.length === 0 ? (
            <EmptyState title="No pending approvals" detail="When an approval-gated step triggers, it will appear here with a full plan preview." />
          ) : (
            <Table>
              <thead>
                <tr>
                  <th>Requested</th>
                  <th>Plan preview</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {pending.map((approval) => (
                  <tr key={approval.automation_approval_id}>
                    <td>{new Date(approval.requested_at).toLocaleString()}</td>
                    <td>
                      <pre className="atlas-code-block">{previewSummary(approval.preview_json)}</pre>
                    </td>
                    <td>
                      <div className="atlas-row" style={{ gap: "var(--space-2)" }}>
                        <Button
                          variant="primary"
                          onClick={() => {
                            setApprovalTarget(approval);
                            setApprovalAcknowledged(false);
                          }}
                        >
                          Review &amp; approve
                        </Button>
                        <Button variant="ghost" onClick={() => setRejectTarget(approval)}>
                          Reject
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Surface>
      ) : null}

      {!loading && activeTab === "runs" ? (
        <div className="atlas-stack" style={{ gap: "var(--space-4)" }}>
          <Surface>
            <SectionHeading title="Run history" detail="Stop-and-hold multi-step outcomes — failed or pending steps block later steps." />
            {runs.length === 0 ? (
              <EmptyState title="No runs yet" detail="Trigger a workflow manually or wait for an event-driven recipe to fire." />
            ) : (
              <Table>
                <thead>
                  <tr>
                    <th>Started</th>
                    <th>Trigger</th>
                    <th>Status</th>
                    <th>Summary</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((run) => (
                    <tr
                      key={run.automation_run_id}
                      className={run.automation_run_id === selectedRunId ? "atlas-table__row--selected" : undefined}
                      onClick={() => setSelectedRunId(run.automation_run_id)}
                      style={{ cursor: "pointer" }}
                    >
                      <td>{new Date(run.started_at).toLocaleString()}</td>
                      <td>{formatTrigger(run.trigger_type)}</td>
                      <td>
                        <StatusPill status={runStatusKind(run.status)}>{run.status}</StatusPill>
                      </td>
                      <td>{run.summary ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </Surface>

          {selectedRun ? (
            <Surface>
              <SectionHeading title="Run steps" detail={`Run ${selectedRun.automation_run_id.slice(0, 8)}…`} />
              <ol className="command-panel__steps" style={{ listStyle: "none", padding: 0 }}>
                {selectedRun.steps.map((step) => (
                  <li key={step.automation_run_step_id} className="command-step">
                    <span className="command-step__index">{step.position + 1}</span>
                    <div>
                      <strong>{step.automation_action_id}</strong>
                      <StatusPill status={stepStatusKind(step.status)}>{step.status.replace(/_/g, " ")}</StatusPill>
                      {step.result_json ? <pre className="atlas-code-block">{JSON.stringify(step.result_json, null, 2)}</pre> : null}
                    </div>
                  </li>
                ))}
              </ol>
            </Surface>
          ) : null}
        </div>
      ) : null}

      {approvalTarget ? (
        <ApprovalPrompt
          acknowledged={approvalAcknowledged}
          confirmLabel={approvalBusy ? "Approving…" : "Approve and execute"}
          detail="This approval-gated automation will execute destructive or process-control actions. Review the plan below before confirming."
          title="Approve automation run"
          onAcknowledge={setApprovalAcknowledged}
          onCancel={() => {
            setApprovalTarget(null);
            setApprovalAcknowledged(false);
          }}
          onApprove={() => void confirmApprove()}
        >
          <pre className="atlas-code-block">{JSON.stringify(approvalTarget.preview_json, null, 2)}</pre>
        </ApprovalPrompt>
      ) : null}

      {rejectTarget ? (
        <Dialog
          detail="Rejecting leaves the project unchanged. Optionally provide a reason for the audit trail."
          footer={
            <>
              <Button variant="ghost" onClick={() => setRejectTarget(null)}>
                Cancel
              </Button>
              <Button loading={rejectBusy} variant="secondary" onClick={() => void confirmReject()}>
                Reject approval
              </Button>
            </>
          }
          title="Reject automation approval"
          tone="warn"
        >
          <Textarea value={rejectReason} onChange={(event) => setRejectReason(event.target.value)} rows={3} placeholder="Optional reason for audit trail" />
        </Dialog>
      ) : null}
    </div>
  );
}

/** Poll pending approvals across projects for shell nav badge. */
export function useAutomationNavCount(enabled: boolean): number {
  const [count, setCount] = useState(0);

  useEffect(() => {
    if (!enabled) {
      setCount(0);
      return;
    }
    let cancelled = false;
    async function poll() {
      try {
        const projectRows = await listProjects();
        const activeIds = projectRows.filter((project) => project.status.toLowerCase() === "active").map((project) => project.project_id);
        const total = await countPendingApprovals(activeIds);
        if (!cancelled) {
          setCount(total);
        }
      } catch {
        if (!cancelled) {
          setCount(0);
        }
      }
    }
    void poll();
    const interval = window.setInterval(() => void poll(), 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [enabled]);

  return count;
}
