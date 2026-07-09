type TimeSeriesTone = "accent" | "info" | "success" | "warn" | "danger";

export interface TimeSeriesRangePoint {
  label?: string;
  min: number;
  max: number;
  avg: number;
}

interface TimeSeriesChartProps {
  points: TimeSeriesRangePoint[];
  tone?: TimeSeriesTone;
  label?: string;
  height?: number;
  formatValue?: (value: number) => string;
  startLabel?: string;
  endLabel?: string;
}

const TONE_CLASS: Record<TimeSeriesTone, string> = {
  accent: "time-series-chart--accent",
  info: "time-series-chart--info",
  success: "time-series-chart--success",
  warn: "time-series-chart--warn",
  danger: "time-series-chart--danger"
};

function defaultFormatValue(value: number): string {
  if (Math.abs(value) >= 100) {
    return String(Math.round(value));
  }
  const fixed = value.toFixed(1);
  return fixed.endsWith(".0") ? String(Math.round(value)) : fixed;
}

function buildTicks(min: number, max: number, count: number): number[] {
  if (count <= 1) {
    return [min];
  }
  const range = max - min || 1;
  return Array.from({ length: count }, (_, index) => min + (range * index) / (count - 1));
}

export function TimeSeriesChart({
  points,
  tone = "accent",
  label,
  height = 200,
  formatValue = defaultFormatValue,
  startLabel,
  endLabel
}: TimeSeriesChartProps) {
  if (points.length === 0) {
    return <p className="muted-copy">No historical points in this window.</p>;
  }

  const width = 640;
  const pad = { top: 12, right: 12, bottom: 32, left: 44 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const globalMin = Math.min(...points.map((point) => point.min));
  const globalMax = Math.max(...points.map((point) => point.max));
  const range = globalMax - globalMin || 1;
  const yTicks = buildTicks(globalMin, globalMax, 4);

  const xAt = (index: number) => pad.left + (points.length === 1 ? innerW / 2 : (index / (points.length - 1)) * innerW);
  const yAt = (value: number) => pad.top + innerH - ((value - globalMin) / range) * innerH;

  const rangePath = points
    .map((point, index) => {
      const x = xAt(index);
      const yMin = yAt(point.min);
      return `${index === 0 ? "M" : "L"}${x},${yMin}`;
    })
    .join(" ");
  const rangePathReverse = [...points]
    .reverse()
    .map((point, reverseIndex) => {
      const index = points.length - 1 - reverseIndex;
      const x = xAt(index);
      const yMax = yAt(point.max);
      return `L${x},${yMax}`;
    })
    .join(" ");

  const avgPath = points
    .map((point, index) => `${index === 0 ? "M" : "L"}${xAt(index)},${yAt(point.avg)}`)
    .join(" ");

  const xStart = startLabel ?? formatTimeLabel(points[0]?.label, "start");
  const xEnd = endLabel ?? "now";

  return (
    <div className="time-series-chart-shell">
      <svg
        aria-label={label}
        className={["time-series-chart", TONE_CLASS[tone]].join(" ")}
        height={height}
        role={label ? "img" : undefined}
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
      >
        {yTicks.map((tick) => (
          <g key={tick}>
            <line
              className="time-series-chart__grid"
              x1={pad.left}
              x2={width - pad.right}
              y1={yAt(tick)}
              y2={yAt(tick)}
            />
            <text className="time-series-chart__tick" textAnchor="end" x={pad.left - 8} y={yAt(tick) + 4}>
              {formatValue(tick)}
            </text>
          </g>
        ))}
        <line className="time-series-chart__axis" x1={pad.left} x2={pad.left} y1={pad.top} y2={pad.top + innerH} />
        <line className="time-series-chart__axis" x1={pad.left} x2={width - pad.right} y1={pad.top + innerH} y2={pad.top + innerH} />
        <path className="time-series-chart__range" d={`${rangePath} ${rangePathReverse} Z`} />
        <path className="time-series-chart__avg" d={avgPath} />
        <text className="time-series-chart__tick" x={pad.left} y={height - 10}>
          {xStart}
        </text>
        <text className="time-series-chart__tick" textAnchor="end" x={width - pad.right} y={height - 10}>
          {xEnd}
        </text>
      </svg>
      <div className="time-series-chart__legend" aria-hidden="true">
        <span className="time-series-chart__legend-item">
          <span className="time-series-chart__legend-line" />
          Average
        </span>
        <span className="time-series-chart__legend-item">
          <span className="time-series-chart__legend-band" />
          Min–max range
        </span>
      </div>
    </div>
  );
}

function formatTimeLabel(label: string | undefined, position: "start" | "end"): string {
  if (!label) {
    return position === "end" ? "now" : "—";
  }
  const parsed = Date.parse(label);
  if (Number.isNaN(parsed)) {
    return label;
  }
  const deltaMinutes = Math.max(1, Math.round((Date.now() - parsed) / 60_000));
  if (deltaMinutes < 60) {
    return `${deltaMinutes}m ago`;
  }
  const deltaHours = Math.round(deltaMinutes / 60);
  if (deltaHours < 48) {
    return `${deltaHours}h ago`;
  }
  return new Date(parsed).toLocaleDateString();
}

export function rollupToRangePoints(
  points: Array<{ bucket_start?: string; sampled_at?: string; min_value?: number; max_value?: number; avg_value?: number; value_real?: number }>
): TimeSeriesRangePoint[] {
  return points
    .filter((point) => {
      const hasRollup = point.min_value != null && point.max_value != null && point.avg_value != null;
      const hasRaw = point.value_real != null;
      return hasRollup || hasRaw;
    })
    .map((point) => {
      if (point.min_value != null && point.max_value != null && point.avg_value != null) {
        return {
          label: point.bucket_start ?? point.sampled_at,
          min: point.min_value,
          max: point.max_value,
          avg: point.avg_value
        };
      }
      const value = point.value_real ?? 0;
      return {
        label: point.sampled_at,
        min: value,
        max: value,
        avg: value
      };
    });
}
