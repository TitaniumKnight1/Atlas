type SparklineTone = "accent" | "info" | "success" | "warn" | "danger";

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
  danger: "atlas-sparkline--danger"
};

export function Sparkline({ values, tone = "accent", label }: SparklineProps) {
  const points = normalize(values);
  const line = points.map(([x, y]) => `${x},${y}`).join(" L");
  const area = points.length > 0 ? `M${line} L100,40 L0,40 Z` : "";

  return (
    <svg
      aria-label={label}
      aria-hidden={label ? undefined : true}
      className={["atlas-sparkline", TONE_CLASS[tone]].join(" ")}
      preserveAspectRatio="none"
      role={label ? "img" : undefined}
      viewBox="0 0 100 40"
    >
      {area ? <path className="atlas-sparkline__area" d={area} /> : null}
      {line ? <path className="atlas-sparkline__line" d={`M${line}`} /> : null}
    </svg>
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
    const y = 36 - ((value - min) / range) * 32;
    return [Number(x.toFixed(2)), Number(y.toFixed(2))];
  });
}
