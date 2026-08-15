import type { ButtonHTMLAttributes, ReactNode } from "react";

interface BaseButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  busy?: boolean;
  busyLabel?: string;
  icon?: ReactNode;
}

export function PrimaryButton({ busy = false, busyLabel = "Сохраняем…", icon, children, disabled, ...props }: BaseButtonProps) {
  return (
    <button {...props} type={props.type ?? "button"} className={`era-btn-primary${props.className ? ` ${props.className}` : ""}`} disabled={disabled || busy}>
      {icon}
      {busy ? busyLabel : children}
    </button>
  );
}

export function SecondaryButton({ busy = false, busyLabel = "Подождите…", icon, children, disabled, ...props }: BaseButtonProps) {
  return (
    <button {...props} type={props.type ?? "button"} className={`era-btn-secondary${props.className ? ` ${props.className}` : ""}`} disabled={disabled || busy}>
      {icon}
      {busy ? busyLabel : children}
    </button>
  );
}

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  label: string;
  children: ReactNode;
}

export function IconButton({ label, children, style, ...props }: IconButtonProps) {
  return (
    <button
      {...props}
      type={props.type ?? "button"}
      aria-label={label}
      title={label}
      style={{
        width: 44,
        height: 44,
        minWidth: 44,
        minHeight: 44,
        padding: 0,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        borderRadius: "50%",
        ...style,
      }}
    >
      {children}
    </button>
  );
}
