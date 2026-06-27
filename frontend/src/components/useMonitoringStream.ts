import { useEffect, useRef, useState } from "react";

import { connectProjectStream, type ProjectStreamEvent } from "../api/stream";

export interface MetricSamplePayload {
  metric_series_id: string;
  metric_name: string;
  source_type: string;
  source_ref: string | null;
  unit: string | null;
  value_type: string;
  value_real: number | null;
  value_text: string | null;
  quality: string;
  sampled_at: string;
  deferred_reason?: string | null;
}

export interface LiveMetricSeries {
  metric_series_id: string;
  metric_name: string;
  source_type: string;
  unit: string | null;
  quality: string;
  value_real: number | null;
  value_text: string | null;
  deferred_reason?: string | null;
  sampled_at: string;
  sparkline: number[];
}

export interface LiveAlertEvent {
  alert_event_id: string;
  event_type: "AlertFired" | "AlertResolved";
  monitoring_alert_id: string;
  alert_name: string;
  severity: string;
  status: string;
  occurred_at: string;
  payload: Record<string, unknown>;
}

const MAX_SPARKLINE_POINTS = 60;
const BATCH_MS = 250;
const MAX_ALERT_EVENTS = 200;

export function useMonitoringStream(projectId: string | null) {
  const [metrics, setMetrics] = useState<Map<string, LiveMetricSeries>>(new Map());
  const [alerts, setAlerts] = useState<LiveAlertEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [lastMetricAt, setLastMetricAt] = useState<string | null>(null);

  const metricsRef = useRef<Map<string, LiveMetricSeries>>(new Map());
  const pendingMetricsRef = useRef<Map<string, MetricSamplePayload>>(new Map());
  const pendingAlertsRef = useRef<LiveAlertEvent[]>([]);
  const alertIdsRef = useRef<Set<string>>(new Set());
  const flushTimerRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    metricsRef.current = new Map();
    pendingMetricsRef.current = new Map();
    pendingAlertsRef.current = [];
    alertIdsRef.current = new Set();
    setMetrics(new Map());
    setAlerts([]);
    setLastMetricAt(null);
    setStreamError(null);
  }, [projectId]);

  useEffect(() => {
    function flushPending() {
      let metricsChanged = false;
      for (const sample of pendingMetricsRef.current.values()) {
        const existing = metricsRef.current.get(sample.metric_series_id);
        const numeric = sample.value_real;
        const sparkline =
          sample.quality !== "missing" && numeric != null
            ? [...(existing?.sparkline ?? []), numeric].slice(-MAX_SPARKLINE_POINTS)
            : existing?.sparkline ?? [];
        metricsRef.current.set(sample.metric_series_id, {
          metric_series_id: sample.metric_series_id,
          metric_name: sample.metric_name,
          source_type: sample.source_type,
          unit: sample.unit,
          quality: sample.quality,
          value_real: sample.value_real,
          value_text: sample.value_text,
          deferred_reason: sample.deferred_reason,
          sampled_at: sample.sampled_at,
          sparkline
        });
        metricsChanged = true;
        setLastMetricAt(sample.sampled_at);
      }
      pendingMetricsRef.current.clear();

      if (metricsChanged) {
        setMetrics(new Map(metricsRef.current));
      }

      if (pendingAlertsRef.current.length > 0) {
        setAlerts((current) => [...pendingAlertsRef.current, ...current].slice(0, MAX_ALERT_EVENTS));
        pendingAlertsRef.current = [];
      }
    }

    flushTimerRef.current = window.setInterval(flushPending, BATCH_MS);
    return () => {
      if (flushTimerRef.current !== undefined) {
        window.clearInterval(flushTimerRef.current);
      }
      flushPending();
    };
  }, [projectId]);

  useEffect(() => {
    if (!projectId) {
      setConnected(false);
      return;
    }

    let cancelled = false;
    let disconnect: (() => void) | undefined;

    void connectProjectStream({
      projectId,
      topics: ["metrics", "alerts"],
      onEvent: (event: ProjectStreamEvent) => {
        if (cancelled) {
          return;
        }
        setConnected(true);
        setStreamError(null);

        if (event.topic === "metrics" && event.event_type === "MetricSample") {
          const payload = event.payload as unknown as MetricSamplePayload;
          if (payload.metric_series_id) {
            pendingMetricsRef.current.set(payload.metric_series_id, payload);
          }
          return;
        }

        if (event.topic === "alerts") {
          const alertEventId = String(event.payload.alert_event_id ?? "");
          if (!alertEventId || alertIdsRef.current.has(alertEventId)) {
            return;
          }
          alertIdsRef.current.add(alertEventId);
          pendingAlertsRef.current.unshift({
            alert_event_id: alertEventId,
            event_type: event.event_type === "AlertResolved" ? "AlertResolved" : "AlertFired",
            monitoring_alert_id: String(event.payload.monitoring_alert_id ?? ""),
            alert_name: String(event.payload.alert_name ?? "Alert"),
            severity: String(event.payload.severity ?? "warn"),
            status: String(event.payload.status ?? (event.event_type === "AlertResolved" ? "resolved" : "triggered")),
            occurred_at: event.occurred_at,
            payload: event.payload
          });
        }
      },
      onError: () => {
        if (!cancelled) {
          setConnected(false);
          setStreamError("Monitoring stream disconnected — live metrics and alerts may lag until reconnect.");
        }
      }
    }).then((close) => {
      disconnect = close;
    });

    return () => {
      cancelled = true;
      disconnect?.();
      setConnected(false);
    };
  }, [projectId]);

  return { metrics, alerts, connected, streamError, lastMetricAt };
}
