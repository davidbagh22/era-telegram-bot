import { useEffect, useRef } from "react";
import type { ReactNode } from "react";
import { GrainOverlay } from "./GrainOverlay";

const animatedOrbKeys = new Set<string>();

interface SignalOrbProps {
  /** 0..1 */
  percent: number;
  size?: number;
  strokeWidth?: number;
  /** Center content — usually a big "%" number + a short caption. Given
   * lots of internal white space rather than packed tight (ToR §4). */
  children?: ReactNode;
  /** Animate the ring fill from 0 only once per mounted app session for
   * this key, matching the ProgressRing convention. */
  animationKey?: string;
  glow?: boolean;
}

/**
 * ERA's signature element (ToR §4): a large glowing gradient progress
 * ring — semi-transparent gradient, soft glow, a hint of grain, gentle
 * breathing motion. Used for rank progress, points, achievements, new
 * levels. Reused across Home (hero), Profile (points), and anywhere a
 * single number deserves the visual center of the screen.
 */
export function SignalOrb({ percent, size = 220, strokeWidth, children, animationKey = "signal-orb", glow = true }: SignalOrbProps) {
  const pathRef = useRef<SVGCircleElement>(null);
  const gradientId = useRef(`signal-orb-gradient-${Math.random().toString(36).slice(2)}`).current;

  const sw = strokeWidth ?? Math.max(8, Math.round(size * 0.055));
  const r = size / 2 - sw / 2 - 2;
  const circumference = 2 * Math.PI * r;

  useEffect(() => {
    const circle = pathRef.current;
    if (!circle) return;

    const normalized = Math.max(0, Math.min(1, percent));
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const alreadyAnimated = animatedOrbKeys.has(animationKey);

    circle.style.strokeDasharray = `${circumference}`;

    if (reduced || alreadyAnimated) {
      circle.style.transition = "none";
      circle.style.strokeDashoffset = `${circumference * (1 - normalized)}`;
      return;
    }

    animatedOrbKeys.add(animationKey);
    circle.style.strokeDashoffset = `${circumference}`;
    // Force a layout flush so the browser registers the starting offset
    // before we transition to the target — otherwise it can skip straight
    // to the end state.
    void circle.getBoundingClientRect();
    circle.style.transition = "stroke-dashoffset 900ms cubic-bezier(0.22, 1, 0.36, 1)";
    circle.style.strokeDashoffset = `${circumference * (1 - normalized)}`;
  }, [animationKey, circumference, percent]);

  return (
    <div
      data-testid="signal-orb"
      style={{
        position: "relative",
        width: size,
        height: size,
        flexShrink: 0,
        display: "grid",
        placeItems: "center",
        isolation: "isolate",
      }}
    >
      {glow && (
        <div
          aria-hidden="true"
          className="era-orb-breathe"
          style={{
            position: "absolute",
            inset: "6%",
            borderRadius: "50%",
            background: "var(--era-gradient-signal)",
            filter: `blur(${Math.round(size * 0.16)}px)`,
            opacity: 0.42,
            zIndex: 0,
          }}
        />
      )}

      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        style={{ position: "absolute", inset: 0, width: "100%", height: "100%", zIndex: 1 }}
      >
        <defs>
          <linearGradient id={gradientId} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="var(--era-violet)" />
            <stop offset="55%" stopColor="var(--era-magenta)" />
            <stop offset="100%" stopColor="var(--era-orange)" />
          </linearGradient>
        </defs>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="var(--era-ring-track)"
          strokeWidth={sw}
        />
        <circle
          ref={pathRef}
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={`url(#${gradientId})`}
          strokeWidth={sw}
          strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>

      <div
        aria-hidden="true"
        style={{ position: "absolute", inset: "14%", borderRadius: "50%", overflow: "hidden", zIndex: 1 }}
      >
        <GrainOverlay opacity={0.03} />
      </div>

      {children && (
        <div
          data-testid="signal-orb-content"
          style={{
            position: "absolute",
            inset: "12%",
            zIndex: 2,
            display: "grid",
            placeItems: "center",
            alignContent: "center",
            textAlign: "center",
            minWidth: 0,
          }}
        >
          {children}
        </div>
      )}
    </div>
  );
}
