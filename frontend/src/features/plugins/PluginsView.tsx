import { useCallback, useEffect, useMemo, useState } from "react";

import { listProjects, type ProjectSummary } from "../../api/project";
import {
  getPluginSettings,
  grantPluginCapabilities,
  listPluginCapabilities,
  listPluginCapabilityCalls,
  listPluginContributions,
  listPlugins,
  revokePluginCapability,
  runPluginRuntime,
  setGlobalPluginEnabled,
  setPluginEnabled,
  stopPluginRuntime,
  type CapabilityCall,
  type PluginCapabilities,
  type PluginContribution,
  type PluginRegistration,
  type PluginRuntime,
  type PluginSettings
} from "../../api/plugin";
import {
  Alert,
  Badge,
  Button,
  ConsentDialog,
  ProjectPicker,
  SectionHeading,
  StatusPill,
  Surface,
  Table,
  Tabs,
  Toast,
  Toggle,
  type CapabilityRequest,
  type StatusKind
} from "../../components";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { useAsyncTask } from "../../components/useAsyncTask";
import { useBackendStatus } from "../../app/useBackendStatus";

type PluginTab = "registry" | "trust" | "runtime" | "contributions";

function trustStatusKind(status: string): StatusKind {
  if (status === "trusted" || status === "granted") {
    return "running";
  }
  if (status === "pending_consent" || status === "pending") {
    return "pending";
  }
  if (status === "revoked" || status === "denied") {
    return "crashed";
  }
  return "idle";
}

function runtimeStatusKind(status: string): StatusKind {
  if (status === "running") {
    return "running";
  }
  if (status === "failed" || status === "crashed" || status === "timed_out") {
    return "crashed";
  }
  if (status === "starting" || status === "stopping") {
    return "pending";
  }
  return "idle";
}

function capabilityScope(capability: string): CapabilityRequest["scope"] {
  const upper = capability.toUpperCase();
  if (upper.includes("READ") || upper.includes("RENDER")) {
    return "read";
  }
  if (upper.includes("INVOKE") || upper.includes("WRITE") || upper.includes("MUTATE")) {
    return "write";
  }
  return "trust";
}

function toCapabilityRequests(capabilities: string[]): CapabilityRequest[] {
  return capabilities.map((capability) => ({
    icon: "cap",
    label: capability.replace(/_/g, " "),
    scope: capabilityScope(capability)
  }));
}

export function PluginsView() {
  const backendStatus = useBackendStatus();
  const { resource: projectsResource } = useAsyncTask<ProjectSummary[]>(listProjects, []);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [settings, setSettings] = useState<PluginSettings | null>(null);
  const [plugins, setPlugins] = useState<PluginRegistration[]>([]);
  const [selectedPluginId, setSelectedPluginId] = useState<string | null>(null);
  const [capabilities, setCapabilities] = useState<PluginCapabilities | null>(null);
  const [capabilityCalls, setCapabilityCalls] = useState<CapabilityCall[]>([]);
  const [allContributions, setAllContributions] = useState<PluginContribution[]>([]);
  const [lastRuntime, setLastRuntime] = useState<PluginRuntime | null>(null);
  const [activeTab, setActiveTab] = useState<PluginTab>("registry");
  const [globalBusy, setGlobalBusy] = useState(false);
  const [runtimeBusy, setRuntimeBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [toast, setToast] = useState<string | null>(null);

  const [consentOpen, setConsentOpen] = useState(false);
  const [trustAcknowledged, setTrustAcknowledged] = useState(false);
  const [pendingGrantCaps, setPendingGrantCaps] = useState<string[]>([]);

  const projects = projectsResource.state === "ready" ? projectsResource.data : [];
  const selectedProject = projects.find((project) => project.project_id === selectedProjectId) ?? null;
  const selectedPlugin = plugins.find((plugin) => plugin.plugin_id === selectedPluginId) ?? null;

  useEffect(() => {
    if (!selectedProjectId && projects.length > 0) {
      setSelectedProjectId(projects[0].project_id);
    }
  }, [projects, selectedProjectId]);

  const reloadGlobal = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [pluginSettings, pluginRows] = await Promise.all([getPluginSettings(), listPlugins()]);
      setSettings(pluginSettings);
      setPlugins(pluginRows);
      if (!selectedPluginId && pluginRows.length > 0) {
        setSelectedPluginId(pluginRows[0].plugin_id);
      }
    } catch (caught) {
      setError(caught);
    } finally {
      setLoading(false);
    }
  }, [selectedPluginId]);

  useEffect(() => {
    void reloadGlobal();
  }, [reloadGlobal]);

  const reloadProjectScoped = useCallback(async () => {
    if (!selectedProjectId || !selectedPluginId) {
      setCapabilities(null);
      setCapabilityCalls([]);
      setAllContributions([]);
      return;
    }
    try {
      const [caps, calls, contribs] = await Promise.all([
        listPluginCapabilities(selectedProjectId, selectedPluginId),
        listPluginCapabilityCalls(selectedProjectId, selectedPluginId),
        listPluginContributions(selectedProjectId)
      ]);
      setCapabilities(caps);
      setCapabilityCalls(calls);
      setAllContributions(contribs);
    } catch (caught) {
      setError(caught);
    }
  }, [selectedProjectId, selectedPluginId]);

  useEffect(() => {
    void reloadProjectScoped();
  }, [reloadProjectScoped]);

  const ungrantedCapabilities = useMemo(() => {
    if (!capabilities) {
      return [];
    }
    const granted = new Set(capabilities.granted_capabilities);
    return capabilities.requested_capabilities.filter((cap) => !granted.has(cap));
  }, [capabilities]);

  async function toggleGlobalEnabled(enabled: boolean) {
    setGlobalBusy(true);
    try {
      await setGlobalPluginEnabled(enabled);
      await reloadGlobal();
      await reloadProjectScoped();
      setToast(enabled ? "Global plugins enabled." : "Global plugin kill switch engaged.");
    } catch (caught) {
      setError(caught);
    } finally {
      setGlobalBusy(false);
    }
  }

  async function togglePluginEnabled(enabled: boolean) {
    if (!selectedPluginId) {
      return;
    }
    try {
      await setPluginEnabled(selectedPluginId, enabled);
      await reloadGlobal();
      setToast(enabled ? "Plugin enabled." : "Plugin disabled.");
    } catch (caught) {
      setError(caught);
    }
  }

  function openGrantConsent(capsToGrant: string[]) {
    setPendingGrantCaps(capsToGrant);
    setTrustAcknowledged(false);
    setConsentOpen(true);
  }

  async function confirmGrant() {
    if (!selectedProjectId || !selectedPluginId || !settings || pendingGrantCaps.length === 0) {
      return;
    }
    try {
      await grantPluginCapabilities(selectedProjectId, selectedPluginId, pendingGrantCaps, {
        user_confirmed: true,
        consent_model: settings.consent_model,
        acknowledged_warning: settings.trust_warning
      });
      setConsentOpen(false);
      setPendingGrantCaps([]);
      await reloadGlobal();
      await reloadProjectScoped();
      setToast("Capabilities granted with explicit consent.");
    } catch (caught) {
      setError(caught);
    }
  }

  async function handleRevoke(capability: string) {
    if (!selectedProjectId || !selectedPluginId) {
      return;
    }
    try {
      await revokePluginCapability(selectedProjectId, selectedPluginId, capability);
      await reloadProjectScoped();
      setToast(`Revoked ${capability}.`);
    } catch (caught) {
      setError(caught);
    }
  }

  async function handleStartRuntime() {
    if (!selectedProjectId || !selectedPluginId) {
      return;
    }
    setRuntimeBusy(true);
    try {
      const runtime = await runPluginRuntime(selectedProjectId, selectedPluginId, "normal");
      setLastRuntime(runtime);
      await reloadProjectScoped();
      setToast("Plugin runtime finished.");
    } catch (caught) {
      setError(caught);
    } finally {
      setRuntimeBusy(false);
    }
  }

  async function handleStopRuntime() {
    if (!selectedProjectId || !selectedPluginId || !lastRuntime?.runtime_id) {
      return;
    }
    setRuntimeBusy(true);
    try {
      const runtime = await stopPluginRuntime(selectedProjectId, selectedPluginId, lastRuntime.runtime_id);
      setLastRuntime(runtime);
      setToast("Plugin runtime stopped.");
    } catch (caught) {
      setError(caught);
    } finally {
      setRuntimeBusy(false);
    }
  }

  if (backendStatus.state !== "ready") {
    return <LoadingState title="Waiting for backend" detail="Plugin controls require a connected Atlas backend." />;
  }

  if (projectsResource.state === "loading") {
    return <LoadingState title="Loading projects" detail="Fetching workspace list for plugin context." />;
  }

  if (projects.length === 0) {
    return <EmptyState title="No projects yet" detail="Import a project before granting plugin capabilities." />;
  }

  return (
    <div className="atlas-feature">
      {toast ? (
        <Toast severity="info" title="Plugins" onDismiss={() => setToast(null)}>
          {toast}
        </Toast>
      ) : null}

      <div className="atlas-row" style={{ justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "var(--space-3)" }}>
        <SectionHeading eyebrow="Operate" title="Plugins" detail="Untrusted code with explicit consent, subprocess isolation, and capability audit." />
        <ProjectPicker projects={projects} selectedProjectId={selectedProjectId} onSelect={setSelectedProjectId} />
      </div>

      <Surface>
        <div className="atlas-row" style={{ justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <strong>Global plugin kill switch</strong>
            <p className="muted-copy">When disabled, no plugin runs or contributes — regardless of per-plugin enable state.</p>
          </div>
          <Toggle
            checked={settings?.global_enabled ?? false}
            disabled={globalBusy || !settings}
            onChange={(event) => void toggleGlobalEnabled(event.currentTarget.checked)}
          >
            {settings?.global_enabled ? "Plugins enabled" : "All plugins paused"}
          </Toggle>
        </div>
        {settings && !settings.global_enabled ? (
          <Alert severity="warn" title="Kill switch active">
            All plugin runtime and contributions are paused until you re-enable the global switch.
          </Alert>
        ) : null}
      </Surface>

      {error ? <ErrorState error={error} /> : null}

      <Tabs
        activeId={activeTab}
        ariaLabel="Plugin views"
        tabs={[
          { id: "registry", label: "Registry" },
          { id: "trust", label: "Capabilities" },
          { id: "runtime", label: "Runtime" },
          { id: "contributions", label: "Contributions" }
        ]}
        onChange={(id) => setActiveTab(id as PluginTab)}
      />

      {loading ? <LoadingState title="Loading plugins" detail="Reading registry and global settings." /> : null}

      {!loading && activeTab === "registry" ? (
        <Surface>
          <SectionHeading title="Installed plugins" detail="Version, author, trust status, and per-plugin enable state." />
          {plugins.length === 0 ? (
            <EmptyState title="No plugins registered" detail="Plugins appear here after registration through the backend registry API." />
          ) : (
            <Table>
              <thead>
                <tr>
                  <th>Plugin</th>
                  <th>Version</th>
                  <th>Trust</th>
                  <th>Enabled</th>
                </tr>
              </thead>
              <tbody>
                {plugins.map((plugin) => (
                  <tr
                    key={plugin.plugin_id}
                    className={plugin.plugin_id === selectedPluginId ? "atlas-table__row--selected" : undefined}
                    style={{ cursor: "pointer" }}
                    onClick={() => setSelectedPluginId(plugin.plugin_id)}
                  >
                    <td>
                      <strong>{plugin.name}</strong>
                      <p className="muted-copy">{plugin.author}</p>
                    </td>
                    <td>{plugin.version}</td>
                    <td>
                      <StatusPill status={trustStatusKind(plugin.trust_status)}>{plugin.trust_status}</StatusPill>
                    </td>
                    <td>
                      <Badge variant={plugin.is_enabled ? "success" : "neutral"}>{plugin.is_enabled ? "On" : "Off"}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
          {selectedPlugin ? (
            <div className="atlas-row" style={{ gap: "var(--space-2)", marginTop: "var(--space-3)" }}>
              <Button
                disabled={!settings?.global_enabled}
                variant="secondary"
                onClick={() => void togglePluginEnabled(!selectedPlugin.is_enabled)}
              >
                {selectedPlugin.is_enabled ? "Disable plugin" : "Enable plugin"}
              </Button>
            </div>
          ) : null}
        </Surface>
      ) : null}

      {!loading && activeTab === "trust" && selectedPlugin && capabilities && settings ? (
        <div className="atlas-stack" style={{ gap: "var(--space-4)" }}>
          <Surface>
            <SectionHeading title={`Capabilities — ${selectedPlugin.name}`} detail="Requested vs granted. Nothing is granted without explicit consent." />
            <Table>
              <thead>
                <tr>
                  <th>Capability</th>
                  <th>Requested</th>
                  <th>Granted</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {capabilities.requested_capabilities.map((capability) => {
                  const granted = capabilities.granted_capabilities.includes(capability);
                  return (
                    <tr key={capability}>
                      <td>{capability}</td>
                      <td>
                        <Badge variant="info">yes</Badge>
                      </td>
                      <td>
                        <Badge variant={granted ? "success" : "neutral"}>{granted ? "yes" : "no"}</Badge>
                      </td>
                      <td>
                        {granted ? (
                          <Button variant="ghost" onClick={() => void handleRevoke(capability)}>
                            Revoke
                          </Button>
                        ) : (
                          <Button variant="secondary" onClick={() => openGrantConsent([capability])}>
                            Grant…
                          </Button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
            {ungrantedCapabilities.length > 1 ? (
              <Button style={{ marginTop: "var(--space-3)" }} variant="primary" onClick={() => openGrantConsent(ungrantedCapabilities)}>
                Grant all pending capabilities…
              </Button>
            ) : null}
          </Surface>
        </div>
      ) : null}

      {!loading && activeTab === "runtime" && selectedPlugin ? (
        <Surface>
          <SectionHeading title="Plugin runtime" detail="Start/stop subprocess host and inspect the latest runtime record." />
          <div className="atlas-row" style={{ gap: "var(--space-2)" }}>
            <Button disabled={!settings?.global_enabled || !selectedPlugin.is_enabled} loading={runtimeBusy} variant="primary" onClick={() => void handleStartRuntime()}>
              Run plugin
            </Button>
            {lastRuntime?.status === "running" ? (
              <Button loading={runtimeBusy} variant="secondary" onClick={() => void handleStopRuntime()}>
                Stop runtime
              </Button>
            ) : null}
          </div>
          {lastRuntime ? (
            <Table>
              <thead>
                <tr>
                  <th>Runtime</th>
                  <th>Status</th>
                  <th>PID</th>
                  <th>Started</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>
                    <code>{lastRuntime.runtime_id.slice(0, 8)}…</code>
                  </td>
                  <td>
                    <StatusPill status={runtimeStatusKind(lastRuntime.status)}>{lastRuntime.status}</StatusPill>
                  </td>
                  <td>{lastRuntime.pid ?? "—"}</td>
                  <td>{new Date(lastRuntime.started_at).toLocaleString()}</td>
                </tr>
              </tbody>
            </Table>
          ) : (
            <EmptyState title="No runtime yet" detail="Run the plugin to create a subprocess runtime record." />
          )}

          <SectionHeading title="Capability call audit log" detail="Which capability was requested, granted or denied, and the outcome." />
          {capabilityCalls.length === 0 ? (
            <EmptyState title="No capability calls yet" detail="Calls appear when the plugin host mediates capability requests." />
          ) : (
            <Table>
              <thead>
                <tr>
                  <th>When</th>
                  <th>Capability</th>
                  <th>Decision</th>
                  <th>Outcome</th>
                </tr>
              </thead>
              <tbody>
                {capabilityCalls.map((call) => (
                  <tr key={call.call_id}>
                    <td>{new Date(call.occurred_at).toLocaleString()}</td>
                    <td>{call.capability}</td>
                    <td>
                      <Badge variant={call.decision === "granted" ? "success" : "warn"}>{call.decision}</Badge>
                    </td>
                    <td>{call.outcome}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Surface>
      ) : null}

      {!loading && activeTab === "contributions" ? (
        <Surface>
          <SectionHeading title="Plugin contributions" detail="Contribution points reflect live enable state — kill switch, revoke, or disable turns them off." />
          {allContributions.length === 0 ? (
            <EmptyState title="No contributions" detail="Register manifest contributions for plugins in this project." />
          ) : (
            <Table>
              <thead>
                <tr>
                  <th>Plugin</th>
                  <th>Point</th>
                  <th>Identifier</th>
                  <th>Required capability</th>
                  <th>Live enabled</th>
                </tr>
              </thead>
              <tbody>
                {allContributions.map((contribution) => {
                  const plugin = plugins.find((item) => item.plugin_id === contribution.plugin_id);
                  return (
                    <tr key={contribution.contribution_id}>
                      <td>{plugin?.name ?? contribution.plugin_id.slice(0, 8)}</td>
                      <td>{contribution.contribution_point}</td>
                      <td>{contribution.identifier}</td>
                      <td>{contribution.required_capability}</td>
                      <td>
                        <Badge variant={contribution.live_enabled ? "success" : "neutral"}>{contribution.live_enabled ? "Yes" : "No"}</Badge>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          )}
        </Surface>
      ) : null}

      {consentOpen && selectedPlugin && selectedProject && settings ? (
        <ConsentDialog
          capabilities={toCapabilityRequests(pendingGrantCaps)}
          pluginName={selectedPlugin.name}
          projectName={selectedProject.display_name}
          trustAcknowledged={trustAcknowledged}
          trustWarning={settings.trust_warning}
          onDeny={() => {
            setConsentOpen(false);
            setPendingGrantCaps([]);
          }}
          onGrant={() => void confirmGrant()}
          onTrustAcknowledge={setTrustAcknowledged}
        />
      ) : null}
    </div>
  );
}
