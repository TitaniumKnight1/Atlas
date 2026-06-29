import { useCallback, useEffect, useMemo, useState } from "react";

import { listProjects, type ProjectSummary } from "../../api/project";
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
  Badge,
  Button,
  Field,
  Input,
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
  type LiveMetricSeries
} from "../../components";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { useAsyncTask } from "../../components/useAsyncTask";
import { useBackendStatus } from "../../app/useBackendStatus";

type MonitoringTab = "live" | "history" | "alerts";
type CollectionState = "unknown" | "running" | "stopped";
type HistoryWindow = "1h" | "24h" | "7d";

const HISTORY_WINDOWS: Record<HistoryWindow, { label: string; ms: number; resolution: "raw" | "minute" | "hour" }> = {
  "1h": { label: "Last hour", ms: 60 * 60 * 1000, resolution: "raw" },
  "24h": { label: "Last 24 hours", ms: 24 * 60 * 60 * 1000, resolution: "minute" },
  "7d": { label: "Last 7 days", ms: 7 * 24 * 60 * 60 * 1000, resolution: "hour" }
};

export function MonitoringView() {
  const backendStatus = useBackendStatus();
  const { resource: projectsResource } = useAsyncTask<ProjectSummary[]>(listProjects, []);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
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

  const projects = projectsResource.state === "ready" ? projectsResource.data : [];
  const { metrics: liveMetrics, alerts: streamAlerts, connected: streamConnected, streamError, lastMetricAt } = useMonitoringStream(selectedProjectId);

  useEffect(() => {
    if (!selectedProjectId && projects.length > 0) {
      setSelectedProjectId(projects[0].project_id);
    }
  }, [projects, selectedProjectId]);

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
  }, [selectedProjectId]);

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

  async function handleStartCollection() {
    if (!selectedProjectId) {
      return;
    }
    setCollectionBusy(true);
    setCollectionError(null);
    try {
      const result = await startCollection(selectedProjectId);
      setCollectionState(result.status === "not_running" ? "stopped" : "running");
      await reloadMetadata();
    } catch (error) {
      setCollectionError(error);
    } finally {
      setCollectionBusy(false);
    }
  }

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

  function metricTone(metric: LiveMetricSeries): "accent" | "warn" | "danger" | "success" {
    if (metric.quality === "missing") {
      return "warn";
    }
    if (metric.metric_name.includes("error") || metric.metric_name.includes("crash")) {
      return "danger";
    }
    if (metric.metric_name.includes("health")) {
      return "success";
    }
    return "accent";
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

  const collectionLabel =
    collectionState === "running"
      ? "Collecting"
      : collectionState === "stopped"
        ? "Stopped"
        : "Unknown";

  return (
    <ViewPage>
      <ViewPageHeader>
        <SectionHeading
          detail="Live metrics stream on the coalesce-tolerant metrics topic; alert events on the guaranteed alerts topic. Historical views use M6b rollups with min/max ranges."
          eyebrow="Monitoring"
          title="Watch health, metrics, and runtime signals"
        />
      </ViewPageHeader>

      <ViewPageBody>
      {backendStatus.state === "connecting" ? (
        <LoadingState detail="Waiting for the local backend before subscribing to metric streams." title="Backend connecting" />
      ) : null}
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
        />

        <section className="project-main">
          {!selectedProjectId ? (
            <EmptyState detail="Select a project to open the monitoring dashboard." title="No project" />
          ) : (
            <>
              <Surface kind="card">
                <div className="atlas-row" style={{ justifyContent: "space-between" }}>
                  <div>
                    <p className="eyebrow">Collection</p>
                    <div className="atlas-row">
                      <StatusPill status={collectionState === "running" ? "running" : collectionState === "stopped" ? "idle" : "pending"}>
                        {collectionLabel}
                      </StatusPill>
                      <StatusPill status={streamConnected ? "running" : "pending"}>
                        Stream {streamConnected ? "connected" : "connecting"}
                      </StatusPill>
                    </div>
                  </div>
                  <div className="setup-step__actions">
                    <Button loading={collectionBusy} variant="primary" onClick={() => void handleStartCollection()}>
                      Start collection
                    </Button>
                    <Button disabled={collectionBusy} variant="secondary" onClick={() => void handleStopCollection()}>
                      Stop collection
                    </Button>
                  </div>
                </div>
                {collectionState !== "running" ? (
                  <Alert severity="info" title="Collection not running">
                    Metric collection is off. Start collection to populate live sparklines and historical rollups — the dashboard will not show fake
                    values while waiting.
                  </Alert>
                ) : null}
                {collectionError ? <ErrorState error={collectionError} /> : null}
                {streamError ? (
                  <Toast severity="warn" title="Stream interrupted" onDismiss={() => undefined}>
                    {streamError}
                  </Toast>
                ) : null}
              </Surface>

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
                  {collectionState !== "running" && displayMetrics.length === 0 ? (
                    <EmptyState
                      detail="Start metric collection to receive live MetricSample events on the metrics SSE topic."
                      title="Collection not started"
                    />
                  ) : null}
                  {collectionState === "running" && displayMetrics.length === 0 ? (
                    <LoadingState detail="Waiting for the first MetricSample on the metrics stream." title="No data yet" rows={3} />
                  ) : null}
                  {displayMetrics.length > 0 ? (
                    <div className="metric-card-grid">
                      {displayMetrics.map((metric) => (
                        <article className="metric-card" key={metric.metric_series_id}>
                          <div className="atlas-row" style={{ justifyContent: "space-between" }}>
                            <div>
                              <p className="eyebrow">{metric.source_type}</p>
                              <h3>{metric.metric_name}</h3>
                            </div>
                            {metric.quality === "missing" ? (
                              <Badge variant="warn">Not available</Badge>
                            ) : (
                              <Badge variant="neutral">{metric.quality}</Badge>
                            )}
                          </div>
                          <p className="metric-card__value">{formatMetricValue(metric)}</p>
                          {metric.quality === "missing" ? (
                            <p className="muted-copy">{metric.deferred_reason ?? "Deferred in M6a — not fabricated in the UI."}</p>
                          ) : metric.sparkline.length > 1 ? (
                            <Sparkline label={`${metric.metric_name} trend`} tone={metricTone(metric)} values={metric.sparkline} />
                          ) : (
                            <p className="muted-copy">Trend builds as coalesced samples arrive.</p>
                          )}
                          <small className="muted-copy">Updated {metric.sampled_at ? new Date(metric.sampled_at).toLocaleTimeString() : "—"}</small>
                        </article>
                      ))}
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
                            {event.eventType === "AlertFired" ? "Alert fired" : "Alert resolved"} at {new Date(event.occurredAt).toLocaleString()}
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
