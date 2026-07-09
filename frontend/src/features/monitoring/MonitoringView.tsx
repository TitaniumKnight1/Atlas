import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  createAlert,
  deleteAlert,
  evaluateAlerts,
  getLatestMetrics,
  listAlertEvents,
  listAlerts,
  listMetricSeries,
  queryMetricHistory,
  startCollection,
  stopCollection,
  updateAlert,
  type AlertEvent,
  type MetricSeries,
  type MonitoringAlert
} from "../../api/monitoring";
import {
  Alert,
  Button,
  Field,
  Input,
  ProgressStatus,
  ProjectPicker,
  SectionHeading,
  Select,
  Sparkline,
  StatusPill,
  Surface,
  Tabs,
  TimeSeriesChart,
  Toast,
  ViewPage,
  ViewPageBody,
  ViewPageHeader,
  ViewWorkspace,
  rollupToRangePoints,
  useMonitoringStream,
  type LiveMetricSeries,
  type ProgressStatusPhase
} from "../../components";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { useActiveProjectSelection } from "../../components/useActiveProjects";
import { useBackendStatus } from "../../app/useBackendStatus";
import { consumeMonitoringHandoffProjectId } from "./handoff";

type MonitoringTab = "live" | "history" | "alerts";
type CollectionState = "unknown" | "starting" | "running" | "stopped";
type HistoryWindow = "1h" | "24h" | "7d";
type MetricDotTone = "ok" | "warn" | "error" | "muted";

const HISTORY_WINDOWS: Record<HistoryWindow, { label: string; ms: number; resolution: "raw" | "minute" | "hour" }> = {
  "1h": { label: "Last hour", ms: 60 * 60 * 1000, resolution: "raw" },
  "24h": { label: "Last 24 hours", ms: 24 * 60 * 60 * 1000, resolution: "minute" },
  "7d": { label: "Last 7 days", ms: 7 * 24 * 60 * 60 * 1000, resolution: "hour" }
};

const SERVER_HEALTH_NAMES = new Set([
  "server_fps",
  "player_count",
  "process_state",
  "resource_count",
  "resource_health",
  "resources_started",
  "resources_failed"
]);

function isServerHealthMetric(metric: LiveMetricSeries): boolean {
  const name = metric.metric_name.toLowerCase();
  if (SERVER_HEALTH_NAMES.has(name)) {
    return true;
  }
  if (metric.source_type === "fivem" || metric.source_type === "process" || metric.source_type === "resource") {
    return true;
  }
  return (
    name.includes("fps") ||
    name.includes("player") ||
    name.includes("process") ||
    name.includes("resource") ||
    name.includes("server")
  );
}

function isSystemMetric(metric: LiveMetricSeries): boolean {
  const name = metric.metric_name.toLowerCase();
  if (metric.source_type === "system") {
    return true;
  }
  return name.includes("cpu") || name.includes("memory") || name.includes("disk") || name.includes("ram");
}

function humanizeMetricName(name: string): string {
  return name.replace(/_/g, " ");
}

function deferredHint(metric: LiveMetricSeries): string {
  if (metric.deferred_reason) {
    return metric.deferred_reason;
  }
  const name = metric.metric_name.toLowerCase();
  if (name.includes("fps") || name.includes("player")) {
    return "Needs txAdmin / resource injection";
  }
  if (name.includes("process")) {
    return "Needs a supervised server process";
  }
  return "Not available yet — never fabricated";
}

function formatMetricValue(metric: LiveMetricSeries): string {
  if (metric.quality === "missing") {
    return "Not available";
  }
  if (metric.value_real != null) {
    return `${metric.value_real.toFixed(metric.value_real >= 100 ? 0 : 1)}${metric.unit ? ` ${metric.unit}` : ""}`;
  }
  if (metric.value_text) {
    return metric.value_text;
  }
  return "—";
}

function metricDotTone(metric: LiveMetricSeries): MetricDotTone {
  if (metric.quality === "missing") {
    return "muted";
  }
  const name = metric.metric_name.toLowerCase();
  if (name.includes("error") || name.includes("crash") || name.includes("failed")) {
    return "error";
  }
  if (name.includes("warn")) {
    return "warn";
  }
  return "ok";
}

function sparkTone(metric: LiveMetricSeries): "accent" | "warn" | "danger" | "success" | "muted" {
  if (metric.quality === "missing") {
    return "muted";
  }
  const tone = metricDotTone(metric);
  if (tone === "error") {
    return "danger";
  }
  if (tone === "warn") {
    return "warn";
  }
  if (tone === "ok" && metric.metric_name.toLowerCase().includes("health")) {
    return "success";
  }
  return "accent";
}

function MetricCard({ metric }: { metric: LiveMetricSeries }) {
  const unavailable = metric.quality === "missing";
  const dot = metricDotTone(metric);

  return (
    <article className={["metric-card", unavailable ? "metric-card--unavailable" : ""].filter(Boolean).join(" ")}>
      <div className="metric-card__header">
        <p className="metric-card__label">{humanizeMetricName(metric.metric_name)}</p>
        <span className={`metric-card__status-dot metric-card__status-dot--${dot}`} aria-hidden="true" />
      </div>
      <p className="metric-card__value">{formatMetricValue(metric)}</p>
      {unavailable ? (
        <p className="metric-card__hint">{deferredHint(metric)}</p>
      ) : metric.sparkline.length > 1 ? (
        <div className="metric-card__spark">
          <Sparkline label={`${metric.metric_name} trend`} tone={sparkTone(metric)} values={metric.sparkline} />
        </div>
      ) : (
        <p className="metric-card__hint">Trend builds as samples arrive</p>
      )}
      {!unavailable ? (
        <p className="metric-card__meta">
          {metric.sampled_at ? new Date(metric.sampled_at).toLocaleTimeString() : "—"}
        </p>
      ) : null}
    </article>
  );
}

export function MonitoringView() {
  const backendStatus = useBackendStatus();
  const { resource: projectsResource, projects, selectedProjectId, setSelectedProjectId, removeProject } = useActiveProjectSelection();
  const [activeTab, setActiveTab] = useState<MonitoringTab>("live");
  const [collectionState, setCollectionState] = useState<CollectionState>("unknown");
  const [collectionBusy, setCollectionBusy] = useState(false);
  const [collectionError, setCollectionError] = useState<unknown>(null);
  const [seriesList, setSeriesList] = useState<MetricSeries[]>([]);
  const [baselineMetrics, setBaselineMetrics] = useState<LiveMetricSeries[]>([]);
  const [alertRules, setAlertRules] = useState<MonitoringAlert[]>([]);
  const [persistedEvents, setPersistedEvents] = useState<AlertEvent[]>([]);
  const [historyWindow, setHistoryWindow] = useState<HistoryWindow>("1h");
  const [historySeriesId, setHistorySeriesId] = useState<string>("");
  const [historyPoints, setHistoryPoints] = useState<ReturnType<typeof rollupToRangePoints>>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<unknown>(null);
  const [alertFormError, setAlertFormError] = useState<unknown>(null);
  const [editingAlertId, setEditingAlertId] = useState<string | null>(null);
  const [alertName, setAlertName] = useState("");
  const [alertSeverity, setAlertSeverity] = useState("warn");
  const [alertSeriesId, setAlertSeriesId] = useState("");
  const [alertComparator, setAlertComparator] = useState("gt");
  const [alertThreshold, setAlertThreshold] = useState("80");
  const [alertDuration, setAlertDuration] = useState("0");
  const [alertEnabled, setAlertEnabled] = useState(true);
  const handoffStartedRef = useRef<string | null>(null);

  const { metrics: liveMetrics, alerts: streamAlerts, connected: streamConnected, streamError, lastMetricAt } = useMonitoringStream(selectedProjectId);

  const reloadMetadata = useCallback(async () => {
    if (!selectedProjectId) {
      return;
    }
    const [series, latest, rules, events] = await Promise.all([
      listMetricSeries(selectedProjectId),
      getLatestMetrics(selectedProjectId),
      listAlerts(selectedProjectId),
      listAlertEvents(selectedProjectId)
    ]);
    setSeriesList(series);
    setAlertRules(rules);
    setPersistedEvents(events);
    setHistorySeriesId((current) => current || series[0]?.metric_series_id || "");
    setAlertSeriesId((current) => current || series[0]?.metric_series_id || "");
    setBaselineMetrics(
      latest.map((sample) => ({
        metric_series_id: sample.metric_series_id,
        metric_name: sample.metric_name,
        source_type: sample.source_type,
        unit: sample.unit,
        quality: sample.quality,
        value_real: sample.value_real,
        value_text: sample.value_text,
        sampled_at: sample.sampled_at,
        sparkline: sample.quality !== "missing" && sample.value_real != null ? [sample.value_real] : []
      }))
    );
    if (latest.some((sample) => sample.quality !== "missing")) {
      setCollectionState((current) => (current === "stopped" ? current : "running"));
    }
  }, [selectedProjectId]);

  useEffect(() => {
    if (projectsResource.state !== "ready") {
      return;
    }
    const handoffId = consumeMonitoringHandoffProjectId();
    if (!handoffId) {
      return;
    }
    if (projects.some((project) => project.project_id === handoffId)) {
      setSelectedProjectId(handoffId);
      handoffStartedRef.current = handoffId;
    }
  }, [projects, projectsResource.state, setSelectedProjectId]);

  useEffect(() => {
    void reloadMetadata().catch(() => undefined);
  }, [reloadMetadata]);

  useEffect(() => {
    if (lastMetricAt && collectionState !== "running") {
      setCollectionState("running");
    }
  }, [lastMetricAt, collectionState]);

  const displayMetrics = useMemo(() => {
    const merged = new Map<string, LiveMetricSeries>();
    for (const metric of baselineMetrics) {
      merged.set(metric.metric_series_id, metric);
    }
    for (const [seriesId, metric] of liveMetrics) {
      merged.set(seriesId, metric);
    }
    return [...merged.values()].sort((a, b) => a.metric_name.localeCompare(b.metric_name));
  }, [baselineMetrics, liveMetrics]);

  const serverHealthMetrics = useMemo(() => displayMetrics.filter(isServerHealthMetric), [displayMetrics]);
  const systemMetrics = useMemo(() => {
    const healthIds = new Set(serverHealthMetrics.map((m) => m.metric_series_id));
    return displayMetrics.filter((metric) => isSystemMetric(metric) && !healthIds.has(metric.metric_series_id));
  }, [displayMetrics, serverHealthMetrics]);
  const otherMetrics = useMemo(() => {
    const claimed = new Set([...serverHealthMetrics, ...systemMetrics].map((m) => m.metric_series_id));
    return displayMetrics.filter((metric) => !claimed.has(metric.metric_series_id));
  }, [displayMetrics, serverHealthMetrics, systemMetrics]);

  const liveAlertFeed = useMemo(() => {
    const streamItems = streamAlerts.map((event) => ({
      id: event.alert_event_id,
      name: event.alert_name,
      severity: event.severity,
      status: event.status,
      eventType: event.event_type,
      occurredAt: event.occurred_at
    }));
    const persistedItems = persistedEvents.map((event) => ({
      id: event.alert_event_id,
      name: event.alert_name,
      severity: event.severity,
      status: event.status,
      eventType: event.status === "resolved" ? "AlertResolved" : "AlertFired",
      occurredAt: event.triggered_at
    }));
    const seen = new Set<string>();
    return [...streamItems, ...persistedItems].filter((item) => {
      if (seen.has(item.id)) {
        return false;
      }
      seen.add(item.id);
      return true;
    });
  }, [streamAlerts, persistedEvents]);

  const handleStartCollection = useCallback(async () => {
    if (!selectedProjectId) {
      return;
    }
    setCollectionBusy(true);
    setCollectionError(null);
    setCollectionState("starting");
    try {
      const result = await startCollection(selectedProjectId);
      setCollectionState(result.status === "not_running" ? "stopped" : "running");
      await reloadMetadata();
    } catch (error) {
      setCollectionError(error);
      setCollectionState("stopped");
    } finally {
      setCollectionBusy(false);
    }
  }, [reloadMetadata, selectedProjectId]);

  useEffect(() => {
    if (!selectedProjectId || handoffStartedRef.current !== selectedProjectId) {
      return;
    }
    if (backendStatus.state !== "ready") {
      return;
    }
    handoffStartedRef.current = null;
    void handleStartCollection();
  }, [backendStatus.state, handleStartCollection, selectedProjectId]);

  async function handleStopCollection() {
    if (!selectedProjectId) {
      return;
    }
    setCollectionBusy(true);
    setCollectionError(null);
    try {
      await stopCollection(selectedProjectId);
      setCollectionState("stopped");
    } catch (error) {
      setCollectionError(error);
    } finally {
      setCollectionBusy(false);
    }
  }

  async function loadHistory() {
    if (!selectedProjectId || !historySeriesId) {
      return;
    }
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const windowDef = HISTORY_WINDOWS[historyWindow];
      const endAt = new Date();
      const startAt = new Date(endAt.getTime() - windowDef.ms);
      const response = await queryMetricHistory(
        selectedProjectId,
        startAt.toISOString(),
        endAt.toISOString(),
        historySeriesId,
        windowDef.resolution
      );
      setHistoryPoints(rollupToRangePoints(response.points));
    } catch (error) {
      setHistoryError(error);
      setHistoryPoints([]);
    } finally {
      setHistoryLoading(false);
    }
  }

  useEffect(() => {
    if (activeTab === "history") {
      void loadHistory();
    }
  }, [activeTab, historyWindow, historySeriesId, selectedProjectId]);

  function resetAlertForm() {
    setEditingAlertId(null);
    setAlertName("");
    setAlertSeverity("warn");
    setAlertComparator("gt");
    setAlertThreshold("80");
    setAlertDuration("0");
    setAlertEnabled(true);
    if (seriesList.length > 0) {
      setAlertSeriesId(seriesList[0].metric_series_id);
    }
  }

  function populateAlertForm(rule: MonitoringAlert) {
    setEditingAlertId(rule.monitoring_alert_id);
    setAlertName(rule.name);
    setAlertSeverity(rule.severity);
    setAlertSeriesId(rule.metric_series_id);
    setAlertComparator(rule.condition.comparator);
    setAlertThreshold(String(rule.condition.threshold));
    setAlertDuration(String(rule.condition.duration_seconds ?? 0));
    setAlertEnabled(rule.is_enabled);
  }

  async function handleSaveAlert() {
    if (!selectedProjectId || !alertName.trim() || !alertSeriesId) {
      return;
    }
    setAlertFormError(null);
    const payload = {
      name: alertName.trim(),
      severity: alertSeverity,
      metric_series_id: alertSeriesId,
      comparator: alertComparator,
      threshold: Number.parseFloat(alertThreshold) || 0,
      duration_seconds: Number.parseInt(alertDuration, 10) || 0,
      is_enabled: alertEnabled
    };
    try {
      if (editingAlertId) {
        await updateAlert(selectedProjectId, editingAlertId, payload);
      } else {
        await createAlert(selectedProjectId, payload);
      }
      resetAlertForm();
      await reloadMetadata();
    } catch (error) {
      setAlertFormError(error);
    }
  }

  async function handleDeleteAlert(alertId: string) {
    if (!selectedProjectId) {
      return;
    }
    await deleteAlert(selectedProjectId, alertId);
    if (editingAlertId === alertId) {
      resetAlertForm();
    }
    await reloadMetadata();
  }

  async function handleEvaluateAlerts() {
    if (!selectedProjectId) {
      return;
    }
    await evaluateAlerts(selectedProjectId);
    await reloadMetadata();
  }

  function alertRuntimeStatus(state: string): "running" | "idle" | "crashed" | "pending" {
    if (state === "firing") {
      return "crashed";
    }
    if (state === "pending") {
      return "pending";
    }
    return "idle";
  }

  const progressPhase: ProgressStatusPhase =
    backendStatus.state === "connecting"
      ? "starting"
      : collectionState === "starting"
        ? "starting"
        : collectionState === "running" && displayMetrics.length === 0
          ? "waiting"
          : collectionState === "running"
            ? "live"
            : collectionState === "stopped"
              ? "idle"
              : "idle";

  const progressTitle =
    progressPhase === "starting" && backendStatus.state === "connecting"
      ? "Connecting to backend…"
      : progressPhase === "starting"
        ? "Starting collection…"
        : progressPhase === "waiting"
          ? "Waiting for first samples…"
          : progressPhase === "live"
            ? streamConnected
              ? "Collecting · stream connected"
              : "Collecting · stream reconnecting"
            : "Collection off";

  const progressDetail =
    progressPhase === "starting" && backendStatus.state === "connecting"
      ? "Waiting for the local Atlas backend before metric streams can connect."
      : progressPhase === "starting"
        ? "Collection is starting. Live metrics will appear as soon as the first samples arrive."
        : progressPhase === "waiting"
          ? "Collection is running. Metrics stream about every 5 seconds — first samples are on the way."
          : progressPhase === "live"
            ? "Live health signals for your supervised server. Deferred FiveM metrics stay honest as Not available until wired."
            : "Metric collection is off. Start collection to populate live health — Atlas will not show fake values while waiting.";

  return (
    <ViewPage>
      <ViewPageHeader>
        <SectionHeading
          detail="Verify your server is healthy while you develop. Live stream on metrics/alerts topics; history uses rollups with min/max ranges."
          eyebrow="Operate"
          title="Server health & metrics"
        />
      </ViewPageHeader>

      <ViewPageBody>
        {backendStatus.state === "down" ? (
          <Alert severity="danger" title="Backend unavailable">
            Monitoring requires the local Atlas backend. Charts and live streams will resume when the backend reconnects.
          </Alert>
        ) : null}

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
                <EmptyState detail="Select a project to open the monitoring dashboard." title="No project" />
              ) : (
                <>
                  <ProgressStatus
                    phase={progressPhase}
                    title={progressTitle}
                    detail={progressDetail}
                    hint={
                      progressPhase === "waiting" || progressPhase === "starting"
                        ? "This is working — data is incoming."
                        : progressPhase === "live"
                          ? lastMetricAt
                            ? `Last sample ${new Date(lastMetricAt).toLocaleTimeString()}`
                            : undefined
                          : undefined
                    }
                    statusLabel={progressTitle}
                    action={
                      progressPhase === "idle"
                        ? {
                            label: "Start collection",
                            onClick: () => void handleStartCollection(),
                            loading: collectionBusy,
                            variant: "primary"
                          }
                        : undefined
                    }
                    secondaryAction={
                      progressPhase === "live" || progressPhase === "waiting" || progressPhase === "starting"
                        ? {
                            label: "Stop",
                            onClick: () => void handleStopCollection(),
                            loading: collectionBusy,
                            variant: "secondary"
                          }
                        : undefined
                    }
                  >
                    {collectionError ? <ErrorState error={collectionError} /> : null}
                    {streamError ? (
                      <Toast severity="warn" title="Stream interrupted" onDismiss={() => undefined}>
                        {streamError}
                      </Toast>
                    ) : null}
                  </ProgressStatus>

                  <Tabs
                    activeId={activeTab}
                    ariaLabel="Monitoring views"
                    tabs={[
                      { id: "live", label: "Live metrics" },
                      { id: "history", label: "History" },
                      { id: "alerts", label: "Alerts" }
                    ]}
                    onChange={(id) => setActiveTab(id as MonitoringTab)}
                  />

                  {activeTab === "live" ? (
                    <>
                      {displayMetrics.length === 0 && progressPhase === "idle" ? (
                        <EmptyState
                          detail="Start collection to receive live health signals. Atlas never fabricates deferred metrics."
                          title="No metrics yet"
                        />
                      ) : null}
                      {displayMetrics.length > 0 ? (
                        <div className="metric-dashboard">
                          {serverHealthMetrics.length > 0 ? (
                            <section className="metric-section">
                              <h3 className="metric-section__title">Server health</h3>
                              <div className="metric-card-grid">
                                {serverHealthMetrics.map((metric) => (
                                  <MetricCard key={metric.metric_series_id} metric={metric} />
                                ))}
                              </div>
                            </section>
                          ) : null}
                          {systemMetrics.length > 0 ? (
                            <section className="metric-section">
                              <h3 className="metric-section__title">System</h3>
                              <div className="metric-card-grid">
                                {systemMetrics.map((metric) => (
                                  <MetricCard key={metric.metric_series_id} metric={metric} />
                                ))}
                              </div>
                            </section>
                          ) : null}
                          {otherMetrics.length > 0 ? (
                            <section className="metric-section">
                              <h3 className="metric-section__title">Other</h3>
                              <div className="metric-card-grid">
                                {otherMetrics.map((metric) => (
                                  <MetricCard key={metric.metric_series_id} metric={metric} />
                                ))}
                              </div>
                            </section>
                          ) : null}
                        </div>
                      ) : null}
                    </>
                  ) : null}

                  {activeTab === "history" ? (
                    <Surface kind="card">
                      <SectionHeading
                        detail="Rollups preserve min/max spikes — the chart band shows range, the line shows average."
                        title="Historical metrics"
                      />
                      <div className="setup-form-grid">
                        <Field label="Metric series">
                          <Select value={historySeriesId} onChange={(event) => setHistorySeriesId(event.target.value)}>
                            {seriesList.map((series) => (
                              <option key={series.metric_series_id} value={series.metric_series_id}>
                                {series.metric_name}
                              </option>
                            ))}
                          </Select>
                        </Field>
                        <Field label="Time window">
                          <Select value={historyWindow} onChange={(event) => setHistoryWindow(event.target.value as HistoryWindow)}>
                            {Object.entries(HISTORY_WINDOWS).map(([key, value]) => (
                              <option key={key} value={key}>
                                {value.label} ({value.resolution})
                              </option>
                            ))}
                          </Select>
                        </Field>
                      </div>
                      <div className="setup-step__actions">
                        <Button variant="secondary" onClick={() => void loadHistory()}>
                          Refresh history
                        </Button>
                      </div>
                      {historyLoading ? <LoadingState title="Loading history" detail="Querying M6b rollups." rows={3} /> : null}
                      {historyError ? <ErrorState error={historyError} onRetry={() => void loadHistory()} /> : null}
                      {!historyLoading && historyPoints.length === 0 ? (
                        <EmptyState
                          detail="No rollup points in this window yet. Start collection and wait for rollups, or try a longer window."
                          title="No historical data"
                        />
                      ) : null}
                      {!historyLoading && historyPoints.length > 0 ? (
                        <TimeSeriesChart label="Min/max range with average line" points={historyPoints} tone="info" />
                      ) : null}
                    </Surface>
                  ) : null}

                  {activeTab === "alerts" ? (
                    <div className="workspace-grid">
                      <Surface kind="card">
                        <SectionHeading detail="Rules evaluate against stored metric series. Enable/disable without deleting." title="Alert rules" />
                        <div className="setup-form-grid">
                          <Field label="Name">
                            <Input value={alertName} onChange={(event) => setAlertName(event.target.value)} placeholder="High CPU" />
                          </Field>
                          <Field label="Severity">
                            <Select value={alertSeverity} onChange={(event) => setAlertSeverity(event.target.value)}>
                              <option value="info">info</option>
                              <option value="warn">warn</option>
                              <option value="critical">critical</option>
                            </Select>
                          </Field>
                          <Field label="Metric series">
                            <Select value={alertSeriesId} onChange={(event) => setAlertSeriesId(event.target.value)}>
                              {seriesList.map((series) => (
                                <option key={series.metric_series_id} value={series.metric_series_id}>
                                  {series.metric_name}
                                </option>
                              ))}
                            </Select>
                          </Field>
                          <Field label="Comparator">
                            <Select value={alertComparator} onChange={(event) => setAlertComparator(event.target.value)}>
                              <option value="gt">greater than</option>
                              <option value="gte">greater or equal</option>
                              <option value="lt">less than</option>
                              <option value="lte">less or equal</option>
                              <option value="eq">equal</option>
                            </Select>
                          </Field>
                          <Field label="Threshold">
                            <Input value={alertThreshold} onChange={(event) => setAlertThreshold(event.target.value)} />
                          </Field>
                          <Field label="Duration (seconds)">
                            <Input value={alertDuration} onChange={(event) => setAlertDuration(event.target.value)} />
                          </Field>
                        </div>
                        <label className="atlas-field">
                          <span className="atlas-field__label">Enabled</span>
                          <input checked={alertEnabled} type="checkbox" onChange={(event) => setAlertEnabled(event.target.checked)} />
                        </label>
                        {alertFormError ? <ErrorState error={alertFormError} /> : null}
                        <div className="setup-step__actions">
                          <Button variant="primary" onClick={() => void handleSaveAlert()}>
                            {editingAlertId ? "Update rule" : "Create rule"}
                          </Button>
                          {editingAlertId ? (
                            <Button variant="secondary" onClick={resetAlertForm}>
                              Cancel edit
                            </Button>
                          ) : null}
                          <Button variant="secondary" onClick={() => void handleEvaluateAlerts()}>
                            Evaluate now
                          </Button>
                        </div>
                        <div className="atlas-table-wrap">
                          <table className="atlas-table">
                            <thead>
                              <tr>
                                <th>Name</th>
                                <th>Severity</th>
                                <th>Runtime</th>
                                <th>Enabled</th>
                                <th />
                              </tr>
                            </thead>
                            <tbody>
                              {alertRules.map((rule) => (
                                <tr key={rule.monitoring_alert_id}>
                                  <td>{rule.name}</td>
                                  <td>{rule.severity}</td>
                                  <td>
                                    <StatusPill status={alertRuntimeStatus(rule.runtime_state)}>{rule.runtime_state}</StatusPill>
                                  </td>
                                  <td>{rule.is_enabled ? "yes" : "no"}</td>
                                  <td>
                                    <div className="atlas-row">
                                      <Button size="sm" variant="secondary" onClick={() => populateAlertForm(rule)}>
                                        Edit
                                      </Button>
                                      <Button size="sm" variant="ghost" onClick={() => void handleDeleteAlert(rule.monitoring_alert_id)}>
                                        Delete
                                      </Button>
                                    </div>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </Surface>

                      <Surface kind="card">
                        <SectionHeading
                          detail="AlertFired and AlertResolved events on the guaranteed alerts topic — never silently dropped in the UI."
                          title="Live alert events"
                        />
                        {liveAlertFeed.length === 0 ? (
                          <EmptyState detail="Alert events appear here when rules fire or resolve." title="No alert events yet" />
                        ) : (
                          <div className="alert-feed">
                            {liveAlertFeed.map((event) => (
                              <Alert
                                key={event.id}
                                severity={event.eventType === "AlertResolved" ? "success" : event.severity === "critical" ? "danger" : "warn"}
                                title={`${event.name} — ${event.status}`}
                              >
                                {event.eventType === "AlertFired" ? "Alert fired" : "Alert resolved"} at{" "}
                                {new Date(event.occurredAt).toLocaleString()}
                              </Alert>
                            ))}
                          </div>
                        )}
                      </Surface>
                    </div>
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
