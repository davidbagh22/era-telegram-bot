import type { ReactNode } from "react";
import { GrainOverlay } from "./GrainOverlay";

interface AchievementOverlayProps {
  open: boolean;
  onClose: () => void;
  kicker?: string;
  title: ReactNode;
  description?: ReactNode;
  actionLabel?: string;
}

/**
 * Fullscreen "signal mode" (ToR §28) for rank-ups, certificates, big
 * milestones, new opportunities. White → violet → red/orange, closes back
 * to the normal light UI. Rare by design — only mount this around a real
 * achievement moment, never as a routine confirmation.
 */
export function AchievementOverlay({ open, onClose, kicker, title, description, actionLabel = "Продолжить" }: AchievementOverlayProps) {
  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="era-modal"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 90,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: "1.5rem",
        padding: "2rem 1.5rem",
        textAlign: "center",
        overflow: "hidden",
        background:
          "radial-gradient(120% 90% at 50% -10%, rgba(99,44,255,0.55), transparent 55%)," +
          "radial-gradient(110% 90% at 100% 110%, rgba(255,100,0,0.5), transparent 55%)," +
          "radial-gradient(90% 80% at 0% 110%, rgba(215,25,120,0.4), transparent 55%)," +
          "#ffffff",
      }}
    >
      <GrainOverlay opacity={0.035} />

      <button
        type="button"
        onClick={onClose}
        aria-label="Закрыть"
        style={{
          position: "absolute",
          top: "1.25rem",
          right: "1.25rem",
          width: 40,
          height: 40,
          minHeight: 40,
          padding: 0,
          borderRadius: "50%",
          border: "1px solid rgba(17,17,24,0.12)",
          background: "rgba(255,255,255,0.7)",
          zIndex: 2,
        }}
      >
        ✕
      </button>

      <div style={{ position: "relative", zIndex: 1, display: "flex", flexDirection: "column", gap: "0.85rem", maxWidth: "22rem" }}>
        {kicker && (
          <span className="era-mono-label" style={{ color: "var(--era-violet)", justifyContent: "center" }}>
            {kicker}
          </span>
        )}
        <h1
          style={{
            margin: 0,
            fontFamily: "var(--era-font-display)",
            fontSize: "clamp(2.25rem, 12vw, 3.25rem)",
            fontWeight: 900,
            lineHeight: 1.02,
            letterSpacing: "-0.03em",
          }}
        >
          {title}
        </h1>
        {description && <p style={{ margin: 0, color: "var(--era-text-secondary)", fontSize: "1rem" }}>{description}</p>}
      </div>

      <button
        type="button"
        className="era-btn-signal"
        onClick={onClose}
        style={{ position: "relative", zIndex: 1, minWidth: "12rem" }}
      >
        {actionLabel}
      </button>
    </div>
  );
}
