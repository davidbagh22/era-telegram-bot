import type { CSSProperties } from "react";

export type SignalGlowVariant = "cool" | "hot" | "signal";

interface SignalGlowProps {
  variant?: SignalGlowVariant;
  /** Where the glow sits relative to its (relatively-positioned) parent. */
  position?: "top-right" | "top-left" | "bottom-left" | "center";
  size?: number;
  style?: CSSProperties;
}

const GRADIENTS: Record<SignalGlowVariant, string> = {
  cool: "radial-gradient(circle, rgba(60,67,255,0.30) 0%, rgba(99,44,255,0.16) 45%, transparent 72%)",
  hot: "radial-gradient(circle, rgba(255,100,0,0.26) 0%, rgba(215,25,120,0.18) 45%, transparent 72%)",
  signal: "radial-gradient(circle, rgba(99,44,255,0.28) 0%, rgba(215,25,120,0.16) 45%, rgba(255,100,0,0.10) 65%, transparent 78%)",
};

const POSITIONS: Record<NonNullable<SignalGlowProps["position"]>, CSSProperties> = {
  "top-right": { top: "-30%", right: "-25%" },
  "top-left": { top: "-30%", left: "-25%" },
  "bottom-left": { bottom: "-30%", left: "-25%" },
  center: { top: "50%", left: "50%", transform: "translate(-50%, -50%)" },
};

/**
 * "Light behind the interface" (ToR §3): a big soft blurred color field,
 * never a full-bleed saturated wash. Meant to sit absolutely inside a
 * `position: relative` container, behind real content (z-index 0).
 */
export function SignalGlow({ variant = "signal", position = "top-right", size = 340, style }: SignalGlowProps) {
  return (
    <div
      aria-hidden="true"
      style={{
        position: "absolute",
        width: size,
        height: size,
        background: GRADIENTS[variant],
        filter: "blur(2px)",
        pointerEvents: "none",
        zIndex: 0,
        ...POSITIONS[position],
        ...style,
      }}
    />
  );
}
