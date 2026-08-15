import { useEffect, useRef, useState } from "react";

interface AnimatedScoreProps {
  value: number;
}

export function AnimatedScore({ value }: AnimatedScoreProps) {
  const previousRef = useRef(value);
  const [displayValue, setDisplayValue] = useState(value);
  const [delta, setDelta] = useState<number | null>(null);

  useEffect(() => {
    const previous = previousRef.current;
    previousRef.current = value;

    if (previous === value) {
      setDisplayValue(value);
      return;
    }

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const difference = value - previous;
    setDelta(difference);

    if (reduced) {
      setDisplayValue(value);
      const timeout = window.setTimeout(() => setDelta(null), 900);
      return () => window.clearTimeout(timeout);
    }

    const duration = 520;
    let start: number | null = null;
    let raf = 0;
    let hideTimeout = 0;

    const easeOut = (t: number) => 1 - Math.pow(1 - t, 3);
    const step = (timestamp: number) => {
      if (start === null) start = timestamp;
      const progress = Math.min(1, (timestamp - start) / duration);
      setDisplayValue(Math.round(previous + difference * easeOut(progress)));
      if (progress < 1) {
        raf = requestAnimationFrame(step);
      } else {
        setDisplayValue(value);
        hideTimeout = window.setTimeout(() => setDelta(null), 850);
      }
    };

    raf = requestAnimationFrame(step);
    return () => {
      cancelAnimationFrame(raf);
      window.clearTimeout(hideTimeout);
    };
  }, [value]);

  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: ".55rem", minHeight: "3.6rem" }}>
      <span
        aria-label={`${value} баллов`}
        style={{
          fontFamily: "var(--era-font-display)",
          fontSize: "clamp(2.75rem, 13vw, 3.5rem)",
          fontWeight: 850,
          lineHeight: 1,
          letterSpacing: "-0.055em",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {displayValue}
      </span>
      {delta !== null && delta !== 0 && (
        <span
          aria-hidden="true"
          className="era-success-state"
          style={{
            marginBottom: ".3rem",
            padding: ".18rem .45rem",
            borderRadius: "var(--era-radius-pill)",
            background: delta > 0 ? "var(--era-success-bg)" : "rgba(255,102,117,.11)",
            color: delta > 0 ? "var(--era-success)" : "var(--era-error)",
            fontSize: "var(--era-text-xs)",
            fontWeight: 850,
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {delta > 0 ? `+${delta}` : delta}
        </span>
      )}
    </div>
  );
}
