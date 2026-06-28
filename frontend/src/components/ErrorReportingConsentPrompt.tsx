import { Button, Dialog } from "../components";

interface ErrorReportingConsentPromptProps {
  onAccept: () => void;
  onDecline: () => void;
  busy?: boolean;
}

export function ErrorReportingConsentPrompt({ onAccept, onDecline, busy = false }: ErrorReportingConsentPromptProps) {
  return (
    <Dialog
      detail="Atlas can optionally send crash reports to help fix bugs in Atlas itself. Your choice is off until you decide."
      footer={
        <>
          <Button disabled={busy} variant="secondary" onClick={onDecline}>
            No thanks
          </Button>
          <Button disabled={busy} variant="secondary" onClick={onAccept}>
            Share error reports
          </Button>
        </>
      }
      icon="?"
      role="alertdialog"
      title="Help improve Atlas with optional error reports?"
      tone="accent"
    >
      <div className="atlas-consent-copy">
        <p>
          <strong>If you accept,</strong> Atlas may send <strong>Atlas application error reports</strong> — crashes and bugs in
          Atlas itself. Reports pass through an audited sanitizer that strips secrets and identifiers before anything leaves
          your machine.
        </p>
        <p>
          <strong>Atlas never sends</strong> your server configuration, logs, FiveM incident data, IPs, player information, or
          any project data.
        </p>
        <p className="muted-copy">You can change this later in the sidebar under Error reporting. Default is off until you choose.</p>
      </div>
    </Dialog>
  );
}
