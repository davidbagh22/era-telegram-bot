import type { CSSProperties, ReactNode } from "react";
import { MonoLabel } from "./MonoLabel";
import { SignalGlow } from "./SignalGlow";
import { GrainOverlay } from "./GrainOverlay";

interface PosterCardProps {
  /** Short technical tag, e.g. "29 AUG" or a category. */
  eyebrow?: ReactNode;
  title: ReactNode;
  subtitle?: ReactNode;
  cta?: string;
  /** Rare near-black statement variant (ToR §7) — use sparingly. */
  dark?: boolean;
  onClick?: () => void;
  /** Decorative art on the right side of the card. */
  media?: ReactNode;
  style?: CSSProperties;
}

/**
 * Event/editorial "poster" card — big date/eyebrow, editorial title,
 * minimal supporting text, an arrow CTA. Used for Events, the Featured
 * Event block on Home, and any "afisha"-style listing.
 */
export function PosterCard({ eyebrow, title, subtitle, cta, dark = false, onClick, media, style }: PosterCardProps) {
  const Wrapper = onClick ? "button" : "div";
  return (
    <Wrapper
      type={onClick ? "button" : undefined}
      onClick={onClick}
      className={`era-card${dark ? " era-card-dark" : ""}`}
      style={{
        position: "relative",
        overflow: "hidden",
        borderRadius: "var(--era-radius-xl)",
        padding: "1.5rem",
        textAlign: "left",
        width: "100%",
        minHeight: 0,
        border: dark ? undefined : "1px solid var(--era-border)",
        background: dark ? undefined : "var(--era-surface)",
        boxShadow: "var(--era-shadow-soft)",
        display: "flex",
        flexDirection: "column",
        gap: "0.85rem",
        ...style,
      }}
    >
      {dark && <SignalGlow variant="hot" position="top-right" size={280} />}
      {dark && <GrainOverlay opacity={0.035} />}

      <div style={{ position: "relative", zIndex: 1, display: "flex", justifyContent: "space-between", gap: "1rem", alignItems: "flex-start" }}>
        <div style={{ minWidth: 0, display: "flex", flexDirection: "column", gap: "0.6rem" }}>
          {eyebrow && <MonoLabel tone={dark ? "onDark" : "violet"}>{eyebrow}</MonoLabel>}
          <div
            style={{
              fontFamily: "var(--era-font-display)",
              fontSize: "clamp(1.35rem, 6vw, 1.75rem)",
              fontWeight: 800,
              lineHeight: 1.08,
              letterSpacing: "-0.02em",
            }}
          >
            {title}
          </div>
          {subtitle && (
            <p style={{ margin: 0, color: dark ? "rgba(247,245,255,0.66)" : "var(--era-text-secondary)", fontSize: "var(--era-text-sm)" }}>
              {subtitle}
            </p>
          )}
        </div>
        {media && <div style={{ flexShrink: 0 }}>{media}</div>}
      </div>

      {cta && (
        <div
          style={{
            position: "relative",
            zIndex: 1,
            display: "flex",
            alignItems: "center",
            gap: "0.4rem",
            fontWeight: 700,
            fontSize: "var(--era-text-sm)",
            color: dark ? "#fff" : "var(--era-violet)",
          }}
        >
          {cta}
          <span aria-hidden="true">→</span>
        </div>
      )}
    </Wrapper>
  );
}
