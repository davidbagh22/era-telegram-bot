import type { CSSProperties } from "react";

interface GrainOverlayProps {
  /** 0..1. Defaults to the token's very light 2–3% baseline (ToR §5). */
  opacity?: number;
  style?: CSSProperties;
}

/**
 * A very faint noise texture for use *inside* a colored area (a glow, a
 * dark card) rather than the page-wide grain already applied via
 * `body::before` in tokens.css. Purely decorative — always
 * `pointer-events: none` so it never intercepts a tap.
 */
export function GrainOverlay({ opacity, style }: GrainOverlayProps) {
  return (
    <div
      aria-hidden="true"
      style={{
        position: "absolute",
        inset: 0,
        pointerEvents: "none",
        opacity: opacity ?? "var(--era-grain-opacity)" as unknown as number,
        backgroundImage:
          "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 180 180' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='.5'/%3E%3C/svg%3E\")",
        mixBlendMode: "overlay",
        borderRadius: "inherit",
        ...style,
      }}
    />
  );
}
