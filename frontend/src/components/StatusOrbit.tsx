import type { ReactNode } from "react";

interface StatusOrbitProps {
  percent: number;
  size?: number;
  strokeWidth?: number;
  label?: string;
  children?: ReactNode;
}

export function StatusOrbit({ percent, size = 112, strokeWidth = 8, label, children }: StatusOrbitProps) {
  const normalized = Math.max(0, Math.min(100, percent));
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - normalized / 100);

  return (
    <div
      aria-label={label ?? `Прогресс ${Math.round(normalized)}%`}
      role="img"
      style={{ position: "relative", width: size, height: size, flexShrink: 0 }}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ display: "block", transform: "rotate(-90deg)" }}>
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="var(--era-ring-track)" strokeWidth={strokeWidth} />
        <circle
          className="era-status-orbit__progress"
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--era-red)"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          style={{
            ["--era-orbit-circumference" as string]: circumference,
            ["--era-orbit-offset" as string]: offset,
          }}
        />
      </svg>
      <div style={{ position: "absolute", inset: strokeWidth + 4, display: "flex", alignItems: "center", justifyContent: "center", textAlign: "center" }}>
        {children ?? <strong style={{ fontSize: "1.15rem" }}>{Math.round(normalized)}%</strong>}
      </div>
    </div>
  );
}
