interface ProgressBarProps {
  value: number;
  max?: number;
  label?: string;
  indeterminate?: boolean;
}

export function ProgressBar({ value, max = 100, label, indeterminate = false }: ProgressBarProps) {
  const safeMax = max > 0 ? max : 0;
  const percent = indeterminate || safeMax === 0 ? 0 : Math.min(100, Math.round((value / safeMax) * 100));

  return (
    <div className="atlas-progress">
      <div
        aria-label={label}
        aria-valuemax={indeterminate ? undefined : 100}
        aria-valuemin={indeterminate ? undefined : 0}
        aria-valuenow={indeterminate ? undefined : percent}
        className={indeterminate ? "atlas-progress__track atlas-progress__track--indeterminate" : "atlas-progress__track"}
        role="progressbar"
      >
        <div className="atlas-progress__fill" style={indeterminate ? undefined : { width: `${percent}%` }} />
      </div>
      {label ? <p className="muted-copy atlas-progress__label">{label}</p> : null}
    </div>
  );
}
