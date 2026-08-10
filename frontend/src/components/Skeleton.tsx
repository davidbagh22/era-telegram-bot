interface SkeletonProps {
  width?: string | number;
  height?: string | number;
  radius?: string;
}

/** A single shimmering placeholder block. See docs/UI_DESIGN_SYSTEM.md —
 * replaces the old plain "Загрузка…" text that every screen used to show
 * on its own while `useAsync`'s status was "loading". */
export function Skeleton({ width = "100%", height = "1rem", radius }: SkeletonProps) {
  return (
    <div
      className="era-skeleton"
      style={{ width, height, borderRadius: radius }}
      aria-hidden="true"
    />
  );
}

/** A handful of skeleton lines of decreasing width, mimicking a paragraph
 * — for text-heavy loading states (card bodies, descriptions). */
export function SkeletonText({ lines = 3 }: { lines?: number }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
      {Array.from({ length: lines }).map((_, index) => (
        <Skeleton key={index} height="0.75rem" width={index === lines - 1 ? "60%" : "100%"} />
      ))}
    </div>
  );
}

/** A skeleton shaped like Card.tsx's default padding/radius, for
 * loading states that will resolve into a list of cards — keeps the
 * layout from jumping once real data arrives. */
export function SkeletonCard({ lines = 2 }: { lines?: number }) {
  return (
    <div
      style={{
        borderRadius: "var(--era-radius-card)",
        padding: "1rem",
        border: "1px solid var(--era-border)",
        background: "var(--era-surface)",
        display: "flex",
        flexDirection: "column",
        gap: "0.5rem",
      }}
    >
      <Skeleton height="1.125rem" width="55%" />
      <SkeletonText lines={lines} />
    </div>
  );
}

/** A vertical stack of SkeletonCard — the common case (a list screen's
 * loading state before the first real card renders). */
export function SkeletonList({ count = 3 }: { count?: number }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {Array.from({ length: count }).map((_, index) => (
        <SkeletonCard key={index} />
      ))}
    </div>
  );
}
