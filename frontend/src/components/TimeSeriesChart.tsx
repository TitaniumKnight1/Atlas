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
}

const TONE_CLASS: Record<TimeSeriesTone, string> = {
  accent: "time-series-chart--accent",
  info: "time-series-chart--info",
  success: "time-series-chart--success",
  warn: "time-series-chart--warn",
  danger: "time-series-chart--danger"
};

export function TimeSeriesChart({ points, tone = "accent", label, height = 120 }: TimeSeriesChartProps) {
  if (points.length === 0) {
    return <p className="muted-copy">No historical points in this window.</p>;
  }

  const width = 400;
  const pad = { top: 8, right: 8, bottom: 20, left: 8 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const globalMin = Math.min(...points.map((point) => point.min));
  const globalMax = Math.max(...points.map((point) => point.max));
  const range = globalMax - globalMin || 1;

  const xAt = (index: number) => pad.left + (points.length === 1 ? innerW / 2 : (index / (points.length - 1)) * innerW);
  const yAt = (value: number) => pad.top + innerH - ((value - globalMin) / range) * innerH;

  const rangePath = points
    .map((point, index) => {
      const x = xAt(index);
      const yMin = yAt(point.min);
      const yMax = yAt(point.max);
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

  return (
    <svg
      aria-label={label}
      className={["time-series-chart", TONE_CLASS[tone]].join(" ")}
      height={height}
      role={label ? "img" : undefined}
      viewBox={`0 0 ${width} ${height}`}
      width="100%"
    >
      <path className="time-series-chart__range" d={`${rangePath} ${rangePathReverse} Z`} />
      <path className="time-series-chart__avg" d={avgPath} />
      {points.map((point, index) => (
        <g key={`${point.label ?? index}`}>
          <line
            className="time-series-chart__whisker"
            x1={xAt(index)}
            x2={xAt(index)}
            y1={yAt(point.min)}
            y2={yAt(point.max)}
          />
          <circle className="time-series-chart__avg-dot" cx={xAt(index)} cy={yAt(point.avg)} r="2.5" />
        </g>
      ))}
    </svg>
  );
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
