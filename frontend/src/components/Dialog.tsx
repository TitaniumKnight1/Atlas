import type { ReactNode } from "react";

import { Badge } from "./Badge";
import { Button } from "./Button";
import { Toggle } from "./Toggle";

interface DialogProps {
  title: string;
  detail?: string;
  icon?: ReactNode;
  tone?: "accent" | "warn" | "danger";
  children: ReactNode;
  footer: ReactNode;
  role?: "dialog" | "alertdialog";
}

export function Dialog({ title, detail, icon = "i", tone = "accent", children, footer, role = "dialog" }: DialogProps) {
  const iconClass =
    tone === "danger" ? "atlas-dialog__icon atlas-dialog__icon--danger" : tone === "warn" ? "atlas-dialog__icon atlas-dialog__icon--warn" : "atlas-dialog__icon";

  return (
    <div className="atlas-modal-scrim">
      <section className="atlas-dialog" role={role} aria-modal="true" aria-label={title}>
        <div className="atlas-dialog__head">
          <span className={iconClass} aria-hidden="true">
            {icon}
          </span>
          <div>
            <h2>{title}</h2>
            {detail ? <p className="muted-copy">{detail}</p> : null}
          </div>
        </div>
        <div className="atlas-dialog__body">{children}</div>
        <div className="atlas-dialog__foot">{footer}</div>
      </section>
    </div>
  );
}

export interface CapabilityRequest {
  icon: ReactNode;
  label: string;
  scope: "read" | "write" | "trust";
}

interface ConsentDialogProps {
  pluginName: string;
  projectName: string;
  capabilities: CapabilityRequest[];
  onDeny: () => void;
  onGrant: () => void;
}

export function ConsentDialog({ pluginName, projectName, capabilities, onDeny, onGrant }: ConsentDialogProps) {
  return (
    <Dialog
      detail={`Plugin requests scoped access for ${projectName}. You can revoke capabilities later in Plugins -> Trust.`}
      footer={
        <>
          <Button variant="ghost" onClick={onDeny}>
            Deny
          </Button>
          <Button variant="primary" onClick={onGrant}>
            Grant {capabilities.length} capabilities
          </Button>
        </>
      }
      icon="shield"
      title={`Grant capabilities to ${pluginName}`}
    >
      <div className="atlas-cap-list">
        {capabilities.map((capability) => (
          <div className="atlas-cap" key={`${capability.scope}-${capability.label}`}>
            <span className="atlas-cap__icon" aria-hidden="true">
              {capability.icon}
            </span>
            <span>{capability.label}</span>
            <span className="atlas-cap__scope">
              <Badge variant={capability.scope === "read" ? "neutral" : capability.scope === "write" ? "warn" : "info"}>
                {capability.scope}
              </Badge>
            </span>
          </div>
        ))}
      </div>
      <Toggle>Trust this publisher for future installs</Toggle>
    </Dialog>
  );
}

interface ApprovalPromptProps {
  title: string;
  detail: string;
  confirmLabel: string;
  acknowledged: boolean;
  onAcknowledge: (value: boolean) => void;
  onCancel: () => void;
  onApprove: () => void;
  children: ReactNode;
}

export function ApprovalPrompt({
  title,
  detail,
  confirmLabel,
  acknowledged,
  onAcknowledge,
  onCancel,
  onApprove,
  children
}: ApprovalPromptProps) {
  return (
    <Dialog
      detail={detail}
      footer={
        <>
          <Button variant="secondary" onClick={onCancel}>
            Cancel
          </Button>
          <Button disabled={!acknowledged} variant="danger" onClick={onApprove}>
            {confirmLabel}
          </Button>
        </>
      }
      icon="!"
      role="alertdialog"
      title={title}
      tone="warn"
    >
      {children}
      <div style={{ marginTop: "var(--space-3)" }}>
        <Toggle checked={acknowledged} onChange={(event) => onAcknowledge(event.currentTarget.checked)}>
          I understand this action changes the project
        </Toggle>
      </div>
    </Dialog>
  );
}
