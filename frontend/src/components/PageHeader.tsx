import type { ReactNode } from "react";
import { IconButton } from "./Buttons";
import { ArrowBackIcon } from "./icons";

interface PageHeaderProps {
  title: string;
  eyebrow?: string;
  subtitle?: string;
  onBack?: () => void;
  trailing?: ReactNode;
}

export function PageHeader({ title, eyebrow, subtitle, onBack, trailing }: PageHeaderProps) {
  return (
    <header style={{ display: "flex", alignItems: "flex-start", gap: "0.75rem", minWidth: 0 }}>
      {onBack && (
        <IconButton label="Назад" onClick={onBack} style={{ flexShrink: 0 }}>
          <ArrowBackIcon width={21} height={21} />
        </IconButton>
      )}
      <div style={{ minWidth: 0, flex: 1, paddingTop: onBack ? 3 : 0 }}>
        {eyebrow && <p className="era-kicker" style={{ marginBottom: "0.3rem" }}>{eyebrow}</p>}
        <h1 style={{ margin: 0, fontSize: "var(--era-text-3xl)", lineHeight: 1.08, letterSpacing: "-0.035em", overflowWrap: "anywhere" }}>{title}</h1>
        {subtitle && <p style={{ margin: "0.45rem 0 0", color: "var(--era-text-muted)", maxWidth: 520 }}>{subtitle}</p>}
      </div>
      {trailing && <div style={{ flexShrink: 0 }}>{trailing}</div>}
    </header>
  );
}
