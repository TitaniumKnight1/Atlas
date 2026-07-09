type SparklineTone = "accent" | "info" | "success" | "warn" | "danger" | "muted";

interface SparklineProps {
  values: number[];
  tone?: SparklineTone;
  label?: string;
}

const TONE_CLASS: Record<SparklineTone, string> = {
  accent: "atlas-sparkline--accent",
  info: "atlas-sparkline--info",
  success: "atlas-sparkline--success",
  warn: "atlas-sparkline--warn",
  danger: "atlas-sparkline--danger",
  muted: "atlas-sparkline--muted"
};

/** Contained sparkline — wrap clips overflow; path stays inside viewBox padding. */
export function Sparkline({ values, tone = "accent", label }: SparklineProps) {
  const points = normalize(values);
  const line = points.map(([x, y]) => `${x},${y}`).join(" L");
  const area = points.length > 0 ? `M${line} L100,36 L0,36 Z` : "";

  return (
    <div className="atlas-sparkline-wrap">
      <svg
        aria-label={label}
        aria-hidden={label ? undefined : true}
        className={["atlas-sparkline", TONE_CLASS[tone]].join(" ")}
        preserveAspectRatio="none"
        role={label ? "img" : undefined}
        viewBox="0 0 100 36"
      >
        {area ? <path className="atlas-sparkline__area" d={area} /> : null}
        {line ? <path className="atlas-sparkline__line" d={`M${line}`} /> : null}
      </svg>
    </div>
  );
}

function normalize(values: number[]): Array<[number, number]> {
  if (values.length === 0) {
    return [];
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  return values.map((value, index) => {
    const x = values.length === 1 ? 100 : (index / (values.length - 1)) * 100;
    const y = 34 - ((value - min) / range) * 30;
    return [Number(x.toFixed(2)), Number(y.toFixed(2))];
  });
}
