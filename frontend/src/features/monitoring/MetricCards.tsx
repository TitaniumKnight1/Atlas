import { Sparkline } from "../../components";
import type { LiveMetricSeries } from "../../components";
import {
  buildResourceSummary,
  deferredHint,
  formatMetricDisplay,
  getMetricLabel,
  metricDotTone,
  resourceBreakdown,
  resourceDotTone,
  sparkTone,
  type ResourceSummary
} from "./metricPresentation";

function MetricValue({ metric }: { metric: LiveMetricSeries }) {
  const formatted = formatMetricDisplay(metric);
  if (formatted.unavailable) {
    return <p className="metric-card__value">{formatted.primary}</p>;
  }
  return (
    <p className="metric-card__value-row">
      <span className="metric-card__value">{formatted.primary}</span>
      {formatted.suffix ? <span className="metric-card__value-suffix">{formatted.suffix}</span> : null}
    </p>
  );
}

function MetricSparkline({ metric }: { metric: LiveMetricSeries }) {
  if (metric.sparkline.length >= 1) {
    return (
      <div className="metric-card__spark">
        <Sparkline label={`${getMetricLabel(metric.metric_name)} trend`} tone={sparkTone(metric)} values={metric.sparkline} />
      </div>
    );
  }
  return <p className="metric-card__collecting">collecting…</p>;
}

export function MetricCard({ metric }: { metric: LiveMetricSeries }) {
  const unavailable = metric.quality === "missing";
  const dot = metricDotTone(metric);

  return (
    <article className={["metric-card", unavailable ? "metric-card--unavailable" : ""].filter(Boolean).join(" ")}>
      <div className="metric-card__header">
        <p className="metric-card__label">{getMetricLabel(metric.metric_name)}</p>
        <span className={`metric-card__status-dot metric-card__status-dot--${dot}`} aria-hidden="true" />
      </div>
      <MetricValue metric={metric} />
      {unavailable ? <p className="metric-card__hint">{deferredHint(metric)}</p> : <MetricSparkline metric={metric} />}
      {!unavailable && metric.sampled_at ? (
        <p className="metric-card__meta">{new Date(metric.sampled_at).toLocaleTimeString()}</p>
      ) : null}
    </article>
  );
}

function ResourcesValue({ summary }: { summary: ResourceSummary }) {
  return (
    <p className="metric-card__value-row">
      <span className="metric-card__value">{summary.total}</span>
      <span className="metric-card__value-suffix">loaded</span>
    </p>
  );
}

export function ResourcesMetricCard({ metrics }: { metrics: LiveMetricSeries[] }) {
  const summary = buildResourceSummary(metrics);
  if (!summary) {
    return null;
  }
  const dot = resourceDotTone(summary);
  const breakdown = resourceBreakdown(summary);

  return (
    <article className="metric-card">
      <div className="metric-card__header">
        <p className="metric-card__label">Resources</p>
        <span className={`metric-card__status-dot metric-card__status-dot--${dot}`} aria-hidden="true" />
      </div>
      <ResourcesValue summary={summary} />
      {breakdown ? <p className="metric-card__breakdown">{breakdown}</p> : null}
      {summary.sparkline.length >= 1 ? (
        <div className="metric-card__spark">
          <Sparkline label="Resources trend" tone={dot === "error" ? "danger" : dot === "warn" ? "warn" : "success"} values={summary.sparkline} />
        </div>
      ) : (
        <p className="metric-card__collecting">collecting…</p>
      )}
      {summary.sampledAt ? <p className="metric-card__meta">{new Date(summary.sampledAt).toLocaleTimeString()}</p> : null}
    </article>
  );
}
