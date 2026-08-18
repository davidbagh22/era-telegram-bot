// DELTA ToR §2: five small signals around the main Signal Orb, one per My
// Vector area — intensity (not a label) is what reads at a glance. Reuses
// the same soft, non-hierarchical palette as DevelopmentScreen's
// SegmentedRing (ToR §21) so "Мой вектор" looks like one consistent system
// wherever it appears, not two different visual languages.
const AREA_ORDER = ["energy", "support", "autonomy", "connection", "direction"] as const;
const AREA_COLORS: Record<(typeof AREA_ORDER)[number], string> = {
  energy: "#ffb37a",
  support: "#b9a6ff",
  autonomy: "#ffb8d9",
  connection: "#8fa6ff",
  direction: "#c9a6e0",
};
const AREA_LABELS: Record<(typeof AREA_ORDER)[number], string> = {
  energy: "Энергия",
  support: "Опора",
  autonomy: "Самостоятельность",
  connection: "Связь",
  direction: "Направление",
};

interface VectorHaloProps {
  /** Matches the orb's own size so the halo sits just outside its ring. */
  orbSize: number;
  /** null renders 5 dim, empty-state dots -- never fabricated values. */
  areas: Record<string, number> | null;
}

export function VectorHalo({ orbSize, areas }: VectorHaloProps) {
  const haloSize = orbSize + 34;
  const dotBase = 10;
  const radius = haloSize / 2;

  return (
    <div
      aria-hidden="true"
      style={{ position: "absolute", inset: `${-(haloSize - orbSize) / 2}px`, pointerEvents: "none" }}
    >
      {AREA_ORDER.map((area, index) => {
        const angle = (index / AREA_ORDER.length) * 2 * Math.PI - Math.PI / 2;
        const x = radius + radius * Math.cos(angle) - dotBase / 2;
        const y = radius + radius * Math.sin(angle) - dotBase / 2;
        const value = areas ? areas[area] ?? 0 : 0;
        const scale = areas ? 0.7 + (value / 100) * 0.6 : 0.55;
        return (
          <span
            key={area}
            title={areas ? `${AREA_LABELS[area]} ${value}` : undefined}
            style={{
              position: "absolute",
              left: x,
              top: y,
              width: dotBase,
              height: dotBase,
              borderRadius: "50%",
              background: areas ? AREA_COLORS[area] : "var(--era-border)",
              opacity: areas ? 0.55 + (value / 100) * 0.45 : 0.4,
              transform: `scale(${scale})`,
              boxShadow: areas && value > 60 ? `0 0 8px ${AREA_COLORS[area]}` : "none",
            }}
          />
        );
      })}
    </div>
  );
}
