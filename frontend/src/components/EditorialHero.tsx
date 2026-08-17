import type { CSSProperties, ReactNode } from "react";
import { MonoLabel } from "./MonoLabel";
import { SignalGlow, type SignalGlowVariant } from "./SignalGlow";

interface EditorialHeroProps {
  eyebrow?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  /** A row of small meta items (deadline, team, status…). */
  meta?: ReactNode;
  dark?: boolean;
  glow?: SignalGlowVariant | "none";
  children?: ReactNode;
  style?: CSSProperties;
}

/**
 * Large editorial section header (ToR §22 Media, §17 Projects, §16
 * Missions): big title, generous air, a soft signal glow behind it rather
 * than a boxed card. The base building block MissionHero specializes.
 */
export function EditorialHero({ eyebrow, title, description, meta, dark = false, glow = "signal", children, style }: EditorialHeroProps) {
  return (
    <section
      className={dark ? "era-card-dark" : undefined}
      style={{
        position: "relative",
        overflow: "hidden",
        borderRadius: "var(--era-radius-xl)",
        padding: "1.5rem",
        background: dark ? undefined : "var(--era-surface)",
        border: dark ? undefined : "1px solid var(--era-border)",
        boxShadow: "var(--era-shadow-soft)",
        ...style,
      }}
    >
      {glow !== "none" && <SignalGlow variant={glow} position="top-right" size={320} />}

      <div style={{ position: "relative", zIndex: 1, display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        {eyebrow && <MonoLabel tone={dark ? "onDark" : "violet"}>{eyebrow}</MonoLabel>}
        <h1
          style={{
            margin: 0,
            fontFamily: "var(--era-font-display)",
            fontSize: "clamp(1.75rem, 8vw, 2.5rem)",
            fontWeight: 850,
            lineHeight: 1.05,
            letterSpacing: "-0.03em",
          }}
        >
          {title}
        </h1>
        {description && (
          <p style={{ margin: 0, color: dark ? "rgba(247,245,255,0.68)" : "var(--era-text-secondary)", maxWidth: "34rem" }}>
            {description}
          </p>
        )}
        {meta && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: "1rem", marginTop: "0.25rem" }}>{meta}</div>
        )}
        {children}
      </div>
    </section>
  );
}
