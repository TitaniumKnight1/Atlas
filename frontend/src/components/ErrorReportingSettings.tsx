import { Toggle } from "./Toggle";

interface ErrorReportingSettingsProps {
  enabled: boolean;
  available: boolean;
  busy?: boolean;
  onChange: (enabled: boolean) => void;
}

export function ErrorReportingSettings({ enabled, available, busy = false, onChange }: ErrorReportingSettingsProps) {
  if (!available) {
    return (
      <div className="error-reporting-settings">
        <p className="eyebrow">Error reporting</p>
        <p className="muted-copy">Unavailable in this build (no reporting endpoint configured).</p>
      </div>
    );
  }

  return (
    <div className="error-reporting-settings">
      <p className="eyebrow">Error reporting</p>
      <Toggle
        checked={enabled}
        disabled={busy}
        onChange={(event) => onChange(event.currentTarget.checked)}
      >
        Share Atlas application errors (scrubbed)
      </Toggle>
      <p className="muted-copy">Sends Atlas crash reports only. Never sends server config, logs, or FiveM data.</p>
    </div>
  );
}
