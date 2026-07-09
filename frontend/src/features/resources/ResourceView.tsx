import { useCallback, useEffect, useMemo, useState } from "react";

import {
  deleteResource,
  dryRunDeleteResource,
  dryRunInstallResource,
  dryRunRollbackBatch,
  dryRunSetEnabledState,
  getDependencyGraph,
  getSafeStartOrder,
  installResource,
  listResources,
  previewDeleteResource,
  previewInstallResource,
  previewRollbackBatch,
  previewSetEnabledState,
  previewUpdateResource,
  rollbackResources,
  setEnabledState,
  updateResource,
  type DependencyGraph,
  type ResourceSummary
} from "../../api/resources";
import {
  Alert,
  Button,
  DependencyGraphView,
  Field,
  Input,
  ProgressBar,
  ProjectPicker,
  SectionHeading,
  StatusPill,
  Surface,
  Tabs,
  type StatusKind,
  ViewPage,
  ViewPageBody,
  ViewPageHeader,
  ViewWorkspace
} from "../../components";
import { CommandPanel } from "../../components/CommandPanel";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { useActiveProjectSelection } from "../../components/useActiveProjects";
import { useProjectStream } from "../../components/useProjectStream";

type ResourceTab = "inventory" | "graph" | "lifecycle" | "rollback";

export function ResourceView() {
  const { resource: projectsResource, projects, selectedProjectId, setSelectedProjectId, removeProject } = useActiveProjectSelection();
  const [activeTab, setActiveTab] = useState<ResourceTab>("inventory");
  const [resources, setResources] = useState<ResourceSummary[]>([]);
  const [graph, setGraph] = useState<DependencyGraph | null>(null);
  const [selectedResourceId, setSelectedResourceId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [mutationTick, setMutationTick] = useState(0);
  const [installSourceType, setInstallSourceType] = useState("local_path");
  const [installSourceUri, setInstallSourceUri] = useState("");
  const [installName, setInstallName] = useState("");
  const [updateSourceUri, setUpdateSourceUri] = useState("");
  const [rollbackIds, setRollbackIds] = useState("");
  const [longOpActive, setLongOpActive] = useState(false);

  const selectedResource = resources.find((resource) => resource.resource_id === selectedResourceId) ?? null;
  const { events: streamEvents, connected: streamConnected } = useProjectStream(selectedProjectId, ["op-progress"]);

  const reload = useCallback(async () => {
    if (!selectedProjectId) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [resourceRows, graphData] = await Promise.all([listResources(selectedProjectId), getDependencyGraph(selectedProjectId)]);
      setResources(resourceRows);
      setGraph(graphData);
      if (!selectedResourceId && resourceRows.length > 0) {
        setSelectedResourceId(resourceRows[0].resource_id);
      }
    } catch (caught) {
      setError(caught);
    } finally {
      setLoading(false);
    }
  }, [selectedProjectId, selectedResourceId]);

  useEffect(() => {
    void reload();
  }, [reload, mutationTick]);

  const latestProgress = useMemo(() => {
    const events = streamEvents.filter((event) => event.topic === "op-progress" && event.event_type === "OperationProgress");
    return events.length > 0 ? events[events.length - 1] : undefined;
  }, [streamEvents]);

  const downloadProgress = latestProgress
    ? {
        bytesReceived: Number(latestProgress.payload.bytes_received ?? 0),
        totalBytes: Number(latestProgress.payload.total_bytes ?? 0),
        message: String(latestProgress.payload.message ?? "Working…")
      }
    : null;

  function bumpMutation() {
    setMutationTick((value) => value + 1);
  }

  function resourceStatusKind(resource: ResourceSummary): StatusKind {
    if (resource.enabled_state === "enabled") {
      return "running";
    }
    if (resource.enabled_state === "disabled") {
      return "idle";
    }
    return "pending";
  }

  const rollbackRequest = {
    resource_ids: rollbackIds
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean)
  };

  return (
    <ViewPage>
      <ViewPageHeader>
        <SectionHeading
          detail="Inventory, dependency graph, lifecycle commands, and batch rollback — all through the backend command rail with graph-safety warnings."
          eyebrow="Resource manager"
          title="Install, enable, and reason about resources"
        />
      </ViewPageHeader>

      <ViewPageBody>
      <ViewWorkspace>
      <Surface className="project-layout" kind="panel" padded={false}>
        <ProjectPicker
          loading={projectsResource.state === "loading"}
          projects={projects}
          selectedProjectId={selectedProjectId}
          onSelect={setSelectedProjectId}
          onRemove={removeProject}
        />

        <section className="project-main">
          {!selectedProjectId ? (
            <EmptyState detail="Select a project to manage resources." title="No project" />
          ) : (
            <>
              <Tabs
                activeId={activeTab}
                ariaLabel="Resource views"
                tabs={[
                  { id: "inventory", label: "Inventory" },
                  { id: "graph", label: "Dependency graph" },
                  { id: "lifecycle", label: "Lifecycle" },
                  { id: "rollback", label: "Rollback" }
                ]}
                onChange={(id) => setActiveTab(id as ResourceTab)}
              />

              {loading ? <LoadingState title="Loading resources" detail="Reading inventory and dependency graph." /> : null}
              {error ? <ErrorState error={error} onRetry={() => bumpMutation()} /> : null}

              {activeTab === "inventory" && !loading ? (
                <Surface kind="card">
                  <SectionHeading detail="Dense inventory with enabled state. Health and dependency satisfaction come from graph queries." title="Resources" />
                  {resources.length === 0 ? (
                    <EmptyState detail="Scan or install resources to populate the inventory." title="No resources yet" />
                  ) : (
                    <div className="atlas-table-wrap">
                      <table className="atlas-table">
                        <thead>
                          <tr>
                            <th>Name</th>
                            <th>Type</th>
                            <th>State</th>
                            <th>Order</th>
                            <th>Path</th>
                          </tr>
                        </thead>
                        <tbody>
                          {resources.map((resource) => (
                            <tr
                              className={resource.resource_id === selectedResourceId ? "atlas-table__row--active" : undefined}
                              key={resource.resource_id}
                              onClick={() => setSelectedResourceId(resource.resource_id)}
                              style={{ cursor: "pointer" }}
                            >
                              <td>{resource.resource_name}</td>
                              <td>{resource.resource_type}</td>
                              <td>
                                <StatusPill status={resourceStatusKind(resource)}>{resource.enabled_state}</StatusPill>
                              </td>
                              <td>{resource.startup_order ?? "—"}</td>
                              <td className="muted-copy">{resource.relative_path}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </Surface>
              ) : null}

              {activeTab === "graph" && graph ? (
                <Surface kind="card">
                  <DependencyGraphView
                    edges={graph.edges}
                    findings={graph.findings}
                    isHealthy={graph.is_healthy}
                    nodes={graph.nodes}
                    selectedNode={selectedResource?.resource_name ?? null}
                    topologicalOrder={graph.topological_order}
                    onSelectNode={(node) => {
                      const match = resources.find((resource) => resource.resource_name === node);
                      if (match) {
                        setSelectedResourceId(match.resource_id);
                      }
                    }}
                  />
                  <SafeOrderPanel projectId={selectedProjectId} />
                </Surface>
              ) : null}

              {activeTab === "lifecycle" && selectedProjectId ? (
                <div className="workspace-grid">
                  <Surface kind="card">
                    <SectionHeading detail="Install writes resource files and may update server.cfg ensure lines." title="Install resource" />
                    <div className="setup-form-grid">
                      <Field label="Source type">
                        <Input value={installSourceType} onChange={(event) => setInstallSourceType(event.target.value)} />
                      </Field>
                      <Field label="Source URI">
                        <Input value={installSourceUri} onChange={(event) => setInstallSourceUri(event.target.value)} placeholder="local path or git URL" />
                      </Field>
                      <Field label="Resource name (optional)">
                        <Input value={installName} onChange={(event) => setInstallName(event.target.value)} />
                      </Field>
                    </div>
                    {(longOpActive || downloadProgress) && (
                      <ProgressBar
                        indeterminate={!downloadProgress?.totalBytes}
                        label={
                          downloadProgress
                            ? `${downloadProgress.message} — ${downloadProgress.bytesReceived}${downloadProgress.totalBytes ? ` / ${downloadProgress.totalBytes}` : ""} bytes`
                            : "Waiting for op-progress events…"
                        }
                        max={downloadProgress?.totalBytes ?? 100}
                        value={downloadProgress?.bytesReceived ?? 0}
                      />
                    )}
                    {!streamConnected ? (
                      <Alert severity="warn" title="SSE disconnected">
                        Live install progress requires an active op-progress stream.
                      </Alert>
                    ) : null}
                    <CommandPanel
                      description="Preview install paths and server.cfg diff, dry-run validation, then install."
                      disabled={!installSourceUri.trim()}
                      executeLabel="Install"
                      title="Install resource"
                      onDryRun={() =>
                        dryRunInstallResource(selectedProjectId, {
                          source_type: installSourceType,
                          source_uri: installSourceUri,
                          resource_name: installName || null
                        })
                      }
                      onExecute={async () => {
                        setLongOpActive(true);
                        try {
                          return await installResource(selectedProjectId, {
                            source_type: installSourceType,
                            source_uri: installSourceUri,
                            resource_name: installName || null
                          });
                        } finally {
                          setLongOpActive(false);
                        }
                      }}
                      onPreview={() =>
                        previewInstallResource(selectedProjectId, {
                          source_type: installSourceType,
                          source_uri: installSourceUri,
                          resource_name: installName || null
                        })
                      }
                      onSuccess={() => bumpMutation()}
                    />
                  </Surface>

                  {selectedResource ? (
                    <Surface kind="card">
                      <SectionHeading detail={`Selected: ${selectedResource.resource_name}`} title="Resource lifecycle" />
                      <Alert severity="info" title="Graph safety">
                        Disable and delete are blocked when enabled dependents exist. Preview warnings come from the backend graph — Atlas does not
                        reimplement safety checks in the UI.
                      </Alert>
                      <Field label="Update source URI">
                        <Input value={updateSourceUri} onChange={(event) => setUpdateSourceUri(event.target.value)} />
                      </Field>
                      <CommandPanel
                        description="Update resource content from a new source."
                        disabled={!updateSourceUri.trim()}
                        executeLabel="Update"
                        title="Update resource"
                        onDryRun={async () => ({
                          data: { command_type: "PlanUpdateResource", valid: true, simulation: {} },
                          warnings: []
                        })}
                        onExecute={() =>
                          updateResource(selectedProjectId, selectedResource.resource_id, {
                            source_type: installSourceType,
                            source_uri: updateSourceUri
                          })
                        }
                        onPreview={() =>
                          previewUpdateResource(selectedProjectId, selectedResource.resource_id, {
                            source_type: installSourceType,
                            source_uri: updateSourceUri
                          })
                        }
                        onSuccess={() => bumpMutation()}
                      />
                      <CommandPanel
                        description={selectedResource.enabled_state === "enabled" ? "Disable resource (may be blocked by dependents)." : "Enable resource."}
                        executeLabel={selectedResource.enabled_state === "enabled" ? "Disable" : "Enable"}
                        title="Set enabled state"
                        onDryRun={() => dryRunSetEnabledState(selectedProjectId, selectedResource.resource_id, selectedResource.enabled_state !== "enabled")}
                        onExecute={() =>
                          setEnabledState(selectedProjectId, selectedResource.resource_id, selectedResource.enabled_state !== "enabled")
                        }
                        onPreview={() =>
                          previewSetEnabledState(selectedProjectId, selectedResource.resource_id, selectedResource.enabled_state !== "enabled")
                        }
                        onSuccess={() => bumpMutation()}
                      />
                      <CommandPanel
                        description="Delete removes resource files and updates server.cfg. Blocked when enabled dependents exist."
                        executeLabel="Delete"
                        title="Delete resource"
                        onDryRun={() => dryRunDeleteResource(selectedProjectId, selectedResource.resource_id)}
                        onExecute={() => deleteResource(selectedProjectId, selectedResource.resource_id)}
                        onPreview={() => previewDeleteResource(selectedProjectId, selectedResource.resource_id)}
                        onSuccess={() => bumpMutation()}
                      />
                    </Surface>
                  ) : (
                    <EmptyState detail="Select a resource from inventory to update, enable, disable, or delete." title="No resource selected" />
                  )}
                </div>
              ) : null}

              {activeTab === "rollback" && selectedProjectId ? (
                <Surface kind="card">
                  <SectionHeading
                    detail="Multi-resource rollback runs in dependency order with stop-and-hold on failure. Preview shows ordered plan and reversibility warnings."
                    title="Batch rollback"
                  />
                  <Field hint="Comma-separated resource IDs. Leave empty to roll back all undoable resources." label="Resource IDs">
                    <Input value={rollbackIds} onChange={(event) => setRollbackIds(event.target.value)} placeholder="id1, id2" />
                  </Field>
                  {(longOpActive || downloadProgress) && (
                    <ProgressBar
                      indeterminate={!downloadProgress?.totalBytes}
                      label={downloadProgress?.message ?? "Rollback in progress…"}
                      max={downloadProgress?.totalBytes ?? 100}
                      value={downloadProgress?.bytesReceived ?? 0}
                    />
                  )}
                  <CommandPanel
                    description="Preview ordered rollback plan, validate, then execute with stop-and-hold outcomes."
                    executeLabel="Execute rollback"
                    title="Rollback resources"
                    onDryRun={() => dryRunRollbackBatch(selectedProjectId, rollbackRequest)}
                    onExecute={async () => {
                      setLongOpActive(true);
                      try {
                        return await rollbackResources(selectedProjectId, rollbackRequest);
                      } finally {
                        setLongOpActive(false);
                      }
                    }}
                    onPreview={() => previewRollbackBatch(selectedProjectId, rollbackRequest)}
                    onSuccess={() => bumpMutation()}
                  />
                </Surface>
              ) : null}
            </>
          )}
        </section>
      </Surface>
      </ViewWorkspace>
      </ViewPageBody>
    </ViewPage>
  );
}

function SafeOrderPanel({ projectId }: { projectId: string }) {
  const [order, setOrder] = useState<string[] | null>(null);
  const [findings, setFindings] = useState<{ message: string }[]>([]);

  useEffect(() => {
    void getSafeStartOrder(projectId).then((result) => {
      setOrder(result.order);
      setFindings(result.findings);
    });
  }, [projectId]);

  return (
    <div className="atlas-stack">
      <p className="eyebrow">Safe start order</p>
      {order ? (
        <p>{order.join(" → ")}</p>
      ) : (
        <Alert severity="warn" title="Order unavailable">
          {findings.map((finding) => finding.message).join(" ") || "Graph has blocking findings."}
        </Alert>
      )}
    </div>
  );
}
