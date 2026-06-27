import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

interface FieldProps {
  label: string;
  hint?: string;
  error?: string;
  children: ReactNode;
}

export function Field({ label, hint, error, children }: FieldProps) {
  return (
    <label className="atlas-field">
      <span className="atlas-field__label">{label}</span>
      {children}
      {error ? <span className="atlas-field__error">{error}</span> : hint ? <span className="atlas-field__hint">{hint}</span> : null}
    </label>
  );
}

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={["atlas-input", className ?? ""].filter(Boolean).join(" ")} {...props} />;
}

export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={["atlas-select", className ?? ""].filter(Boolean).join(" ")} {...props}>
      {children}
    </select>
  );
}

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={["atlas-textarea", className ?? ""].filter(Boolean).join(" ")} {...props} />;
}

export function InputGroup({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={["atlas-input-group", className ?? ""].filter(Boolean).join(" ")}>{children}</div>;
}
