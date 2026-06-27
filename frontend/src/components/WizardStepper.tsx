export type WizardStepStatus = "upcoming" | "active" | "complete" | "failed";

export interface WizardStepItem {
  id: string;
  label: string;
  status: WizardStepStatus;
}

interface WizardStepperProps {
  steps: WizardStepItem[];
  ariaLabel?: string;
}

export function WizardStepper({ steps, ariaLabel = "Setup wizard progress" }: WizardStepperProps) {
  return (
    <nav className="wizard-stepper" aria-label={ariaLabel}>
      {steps.map((step, index) => (
        <span
          className={["command-step", commandStepClass(step.status)].filter(Boolean).join(" ")}
          key={step.id}
          aria-current={step.status === "active" ? "step" : undefined}
        >
          <span className="command-step__mark" aria-hidden="true">
            {step.status === "complete" ? "✓" : step.status === "failed" ? "!" : index + 1}
          </span>
          {step.label}
        </span>
      ))}
    </nav>
  );
}

function commandStepClass(status: WizardStepStatus): string {
  switch (status) {
    case "active":
      return "command-step--active";
    case "complete":
      return "command-step--done";
    case "failed":
      return "command-step--failed";
    default:
      return "";
  }
}
