import type { VectorDimension } from "../types/development";

const DIMENSION_ORDER: VectorDimension[] = ["energy", "agency", "autonomy", "connection", "direction"];
const DIMENSION_LABELS: Record<VectorDimension, string> = {
  energy: "Энергия",
  agency: "Действие",
  autonomy: "Опора",
  connection: "Связь",
  direction: "Курс",
};

interface VectorRadarProps {
  values: Partial<Record<VectorDimension, number>>;
  index?: number | null;
}

function polar(cx: number, cy: number, radius: number, angleRad: number): [number, number] {
  return [cx + radius * Math.cos(angleRad), cy + radius * Math.sin(angleRad)];
}

/**
 * Live polar chart of the five vector dimensions.
 * Values are real profile scores (0–100); the polygon animates on mount.
 */
export function VectorRadar({ values, index = null }: VectorRadarProps) {
  const cx = 130;
  const cy = 130;
  const maxR = 88;
  const n = DIMENSION_ORDER.length;

  const points = DIMENSION_ORDER.map((key, i) => {
    const raw = values[key];
    const score = typeof raw === "number" && Number.isFinite(raw) ? Math.max(0, Math.min(100, raw)) : 0;
    const angle = -Math.PI / 2 + (i * 2 * Math.PI) / n;
    return {
      key,
      score,
      angle,
      xy: polar(cx, cy, (score / 100) * maxR, angle),
    };
  });

  const polygon = points.map((p) => `${p.xy[0]},${p.xy[1]}`).join(" ");

  return (
    <div style={{ position: "relative", width: "100%", maxWidth: 280, margin: "0 auto" }}>
      <svg viewBox="0 0 260 260" width="100%" height="auto" role="img" aria-label="Динамика вектора">
        <defs>
          <radialGradient id="era-vector-glow" cx="50%" cy="50%" r="55%">
            <stop offset="0%" stopColor="rgba(36, 85, 255, 0.22)" />
            <stop offset="100%" stopColor="rgba(36, 85, 255, 0)" />
          </radialGradient>
          <linearGradient id="era-vector-fill" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="rgba(13, 148, 136, 0.45)" />
            <stop offset="100%" stopColor="rgba(15, 23, 42, 0.12)" />
          </linearGradient>
        </defs>
        <circle cx={cx} cy={cy} r={maxR + 18} fill="url(#era-vector-glow)" />
        {[0.25, 0.5, 0.75, 1].map((scale) => (
          <circle
            key={scale}
            cx={cx}
            cy={cy}
            r={maxR * scale}
            fill="none"
            stroke="var(--era-border)"
            strokeWidth={scale === 1 ? 1.2 : 0.8}
          />
        ))}
        {points.map((p) => {
          const [x, y] = polar(cx, cy, maxR, p.angle);
          return <line key={`axis-${p.key}`} x1={cx} y1={cy} x2={x} y2={y} stroke="var(--era-border)" strokeWidth={0.9} />;
        })}
        <polygon
          points={polygon}
          fill="url(#era-vector-fill)"
          stroke="var(--era-cyan, #75ddff)"
          strokeWidth={2.2}
          style={{
            transformOrigin: "130px 130px",
            animation: "era-vector-in 700ms cubic-bezier(.2,.8,.2,1) both",
          }}
        />
        {points.map((p) => {
          const [x, y] = p.xy;
          const [lx, ly] = polar(cx, cy, maxR + 22, p.angle);
          return (
            <g key={p.key}>
              <circle cx={x} cy={y} r={4.5} fill="var(--era-cyan, #75ddff)" stroke="#fff" strokeWidth={1.5} />
              <text
                x={lx}
                y={ly}
                textAnchor="middle"
                dominantBaseline="middle"
                fill="var(--era-text-muted)"
                style={{ fontSize: 9.5, fontWeight: 700 }}
              >
                {DIMENSION_LABELS[p.key]}
              </text>
            </g>
          );
        })}
        {index != null && Number.isFinite(index) ? (
          <g>
            <circle cx={cx} cy={cy} r={22} fill="var(--era-surface)" stroke="var(--era-border)" />
            <text x={cx} y={cy - 2} textAnchor="middle" dominantBaseline="middle" fill="var(--era-text)" style={{ fontSize: 16, fontWeight: 900 }}>
              {Math.round(index)}
            </text>
            <text x={cx} y={cy + 12} textAnchor="middle" fill="var(--era-text-muted)" style={{ fontSize: 7.5, fontWeight: 700 }}>
              индекс
            </text>
          </g>
        ) : null}
      </svg>
      <style>{`
        @keyframes era-vector-in {
          from { opacity: 0; transform: scale(0.72); }
          to { opacity: 1; transform: scale(1); }
        }
      `}</style>
    </div>
  );
}
