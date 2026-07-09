import type { LiveMetricSeries } from "../../components";

export type MetricDotTone = "ok" | "warn" | "error" | "muted";

const METRIC_LABELS: Record<string, string> = {
  cpu_used_percent: "CPU",
  memory_used_percent: "Memory",
  disk_used_percent: "Disk used",
  disk_free_gb: "Disk free",
  player_count: "Players",
  server_fps: "Server FPS",
  process_state: "Process",
  process_up: "Process up",
  process_pid: "Process PID",
  process_memory_mb: "Process memory",
  process_exit_code: "Exit code",
  resource_count: "Resources"
};

const RESOURCE_HEALTH_COUNTS = new Set([
  "resource_health_healthy_count",
  "resource_health_warning_count",
  "resource_health_error_count",
  "resource_health_unknown_count"
]);

export interface FormattedMetricValue {
  primary: string;
  suffix?: string;
  unavailable?: boolean;
}

export interface ResourceSummary {
  total: number;
  healthy: number;
  warning: number;
  error: number;
  unknown: number;
  sparkline: number[];
  sampledAt: string | null;
}

export function getMetricLabel(metricName: string): string {
  const key = metricName.toLowerCase();
  if (METRIC_LABELS[key]) {
    return METRIC_LABELS[key];
  }
  if (RESOURCE_HEALTH_COUNTS.has(key)) {
    return "Resources";
  }
  return metricName
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function isFoldedResourceMetric(metricName: string): boolean {
  const key = metricName.toLowerCase();
  return key === "resource_count" || RESOURCE_HEALTH_COUNTS.has(key);
}

export function buildResourceSummary(metrics: LiveMetricSeries[]): ResourceSummary | null {
  const countMetric = metrics.find((metric) => metric.metric_name.toLowerCase() === "resource_count");
  if (!countMetric) {
    return null;
  }
  const readCount = (name: string) => {
    const metric = metrics.find((item) => item.metric_name.toLowerCase() === name);
    if (metric?.value_real == null) {
      return 0;
    }
    return Math.round(metric.value_real);
  };
  return {
    total: countMetric.value_real != null ? Math.round(countMetric.value_real) : 0,
    healthy: readCount("resource_health_healthy_count"),
    warning: readCount("resource_health_warning_count"),
    error: readCount("resource_health_error_count"),
    unknown: readCount("resource_health_unknown_count"),
    sparkline: countMetric.sparkline,
    sampledAt: countMetric.sampled_at
  };
}

export function resourceDotTone(summary: ResourceSummary): MetricDotTone {
  if (summary.error > 0) {
    return "error";
  }
  if (summary.warning > 0) {
    return "warn";
  }
  if (summary.unknown > 0 && summary.healthy === 0) {
    return "muted";
  }
  return "ok";
}

export function resourceBreakdown(summary: ResourceSummary): string {
  const parts: string[] = [];
  if (summary.healthy > 0) {
    parts.push(`${summary.healthy} healthy`);
  }
  if (summary.warning > 0) {
    parts.push(`${summary.warning} warning${summary.warning === 1 ? "" : "s"}`);
  }
  if (summary.error > 0) {
    parts.push(`${summary.error} error${summary.error === 1 ? "" : "s"}`);
  }
  if (summary.unknown > 0) {
    parts.push(`${summary.unknown} unknown`);
  }
  return parts.join(" · ");
}

function isPercentMetric(metricName: string, unit?: string | null): boolean {
  const name = metricName.toLowerCase();
  return name.endsWith("_percent") || unit === "percent";
}

function isCountMetric(metricName: string, unit?: string | null): boolean {
  const name = metricName.toLowerCase();
  return unit === "count" || name.endsWith("_count");
}

function isGigabyteMetric(metricName: string, unit?: string | null): boolean {
  const name = metricName.toLowerCase();
  return name.includes("disk_free") || unit === "gigabytes" || unit === "gb";
}

function isFpsMetric(metricName: string, unit?: string | null): boolean {
  const name = metricName.toLowerCase();
  return name.includes("fps") || unit === "fps";
}

function formatNumber(value: number, decimals: number): string {
  const fixed = value.toFixed(decimals);
  if (decimals > 0) {
    return fixed.replace(/\.0+$/, "");
  }
  return fixed;
}

export function formatMetricDisplay(metric: LiveMetricSeries): FormattedMetricValue {
  if (metric.quality === "missing") {
    return { primary: "Not available", unavailable: true };
  }
  if (metric.value_text) {
    return { primary: metric.value_text };
  }
  if (metric.value_real == null) {
    return { primary: "—" };
  }

  const value = metric.value_real;
  const name = metric.metric_name.toLowerCase();

  if (isPercentMetric(name, metric.unit)) {
    return { primary: formatNumber(value, 1), suffix: "%" };
  }
  if (isCountMetric(name, metric.unit)) {
    return { primary: String(Math.round(value)) };
  }
  if (isGigabyteMetric(name, metric.unit)) {
    const primary = value >= 100 ? String(Math.round(value)) : formatNumber(value, 1);
    return { primary, suffix: "GB" };
  }
  if (isFpsMetric(name, metric.unit)) {
    return { primary: String(Math.round(value)), suffix: "fps" };
  }
  if (name.includes("memory_mb") || metric.unit === "megabytes") {
    return { primary: formatNumber(value, value >= 100 ? 0 : 1), suffix: "MB" };
  }

  const decimals = Number.isInteger(value) ? 0 : 1;
  return { primary: formatNumber(value, decimals) };
}

export function formatHistoryAxisValue(metricName: string, unit: string | null | undefined, value: number): string {
  const fakeMetric: LiveMetricSeries = {
    metric_series_id: "",
    metric_name: metricName,
    source_type: "",
    unit: unit ?? null,
    quality: "good",
    value_real: value,
    value_text: null,
    sampled_at: "",
    sparkline: []
  };
  const formatted = formatMetricDisplay(fakeMetric);
  return formatted.suffix ? `${formatted.primary}${formatted.suffix}` : formatted.primary;
}

export function deferredHint(metric: LiveMetricSeries): string {
  if (metric.deferred_reason) {
    const reason = metric.deferred_reason.toLowerCase();
    if (reason.includes("txadmin") || reason.includes("fivem")) {
      return "Needs txAdmin connection";
    }
    if (reason.includes("process")) {
      return "Needs a supervised server process";
    }
    return metric.deferred_reason;
  }
  const name = metric.metric_name.toLowerCase();
  if (name.includes("fps") || name.includes("player")) {
    return "Needs txAdmin connection";
  }
  if (name.includes("process")) {
    return "Needs a supervised server process";
  }
  return "Waiting for first sample";
}

export function metricDotTone(metric: LiveMetricSeries): MetricDotTone {
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

export function sparkTone(metric: LiveMetricSeries): "accent" | "warn" | "danger" | "success" | "muted" {
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
