import type { InputHTMLAttributes, ReactNode } from "react";

interface ToggleProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  children: ReactNode;
}

export function Toggle({ children, className, ...props }: ToggleProps) {
  return (
    <label className={["atlas-switch", className ?? ""].filter(Boolean).join(" ")}>
      <input type="checkbox" {...props} />
      <span className="atlas-switch__track" aria-hidden="true">
        <span className="atlas-switch__thumb" />
      </span>
      <span className="atlas-switch__text">{children}</span>
    </label>
  );
}
