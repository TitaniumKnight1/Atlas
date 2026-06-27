import type { ButtonHTMLAttributes, ReactNode } from "react";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "dangerSoft";
type ButtonSize = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  iconOnly?: boolean;
  children: ReactNode;
}

export function Button({
  variant = "secondary",
  size = "md",
  loading = false,
  iconOnly = false,
  className,
  disabled,
  children,
  ...props
}: ButtonProps) {
  const classes = [
    "atlas-button",
    `atlas-button--${variant}`,
    size !== "md" ? `atlas-button--${size}` : "",
    iconOnly ? "atlas-button--icon" : "",
    className ?? ""
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <button className={classes} disabled={disabled || loading} {...props}>
      {loading ? <span className="atlas-spinner" aria-hidden="true" /> : null}
      {children}
    </button>
  );
}
