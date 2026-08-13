import { fetchLeaderboard } from "../api/client";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { SkeletonList } from "../components/Skeleton";
import { StatusBanner } from "../components/StatusBanner";
import { useAsync } from "../hooks/useAsync";
import type { LeaderboardEntry } from "../types/leaderboard";

interface LeaderboardScreenProps {
  onBack: () => void;
}

// Rank badge tint — only the very top spot gets a distinct color (gold, same
// tone MetricCard/HomeScreen reserve for "completed"-type highlights); every
// other rank stays a plain neutral circle so the emphasis reads as "#1", not
// as a full podium ranking system that doesn't exist here.
function RankBadge({ rank }: { rank: number }) {
  const isTop = rank === 1;
  return (
    <span
      style={{
        flexShrink: 0,
        width: 32,
        height: 32,
        borderRadius: "50%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontWeight: 700,
        fontSize: "0.8125rem",
        fontVariantNumeric: "tabular-nums",
        background: isTop ? "var(--era-tint-gold)" : "var(--era-surface-2)",
        color: isTop ? "var(--era-gold-ink)" : "var(--era-text-muted)",
      }}
    >
      {rank}
    </span>
  );
}

function LeaderboardRow({ entry }: { entry: LeaderboardEntry }) {
  return (
    <Card
      style={
        entry.is_you
          ? { background: "var(--era-tint-violet)", border: "1px solid var(--era-violet)" }
          : undefined
      }
    >
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
        <RankBadge rank={entry.rank} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <strong
            style={{
              display: "block",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              color: entry.is_you ? "var(--era-violet)" : undefined,
            }}
          >
            {entry.display_name}
            {entry.is_you ? " · Вы" : ""}
          </strong>
          <span style={{ fontSize: "0.75rem", color: "var(--era-text-muted)" }}>
            {entry.growth_level}
          </span>
        </div>
        <strong style={{ fontVariantNumeric: "tabular-nums", flexShrink: 0 }}>
          {entry.points}
        </strong>
      </div>
    </Card>
  );
}

export function LeaderboardScreen({ onBack }: LeaderboardScreenProps) {
  const state = useAsync(fetchLeaderboard, []);

  return (
    <div className="era-page" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
        <button type="button" onClick={onBack} aria-label="Назад">
          ←
        </button>
        <h1 style={{ fontFamily: "var(--era-font-display)", fontSize: "1.375rem", margin: 0 }}>
          Рейтинг участников
        </h1>
      </div>

      {state.status === "loading" && <SkeletonList count={6} />}

      {state.status === "error" && (
        <StatusBanner
          title="Не удалось загрузить рейтинг"
          description="Потяните вниз, чтобы обновить страницу, или попробуйте ещё раз."
        />
      )}

      {state.status === "ready" && (
        <>
          {/* The viewer's own place — shown even when it falls outside the
              visible top slice below, so "where am I" never requires
              scrolling through everyone ahead. When it's already inside
              the top slice, this just repeats that same row up front,
              which is fine — it's the one row a participant opens this
              screen to find first. */}
          {state.data.me && (
            <section style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <h2 style={{ fontSize: "0.875rem", color: "var(--era-text-muted)", margin: 0 }}>
                Ваше место
              </h2>
              <LeaderboardRow entry={state.data.me} />
            </section>
          )}

          <section style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <h2 style={{ fontSize: "0.875rem", color: "var(--era-text-muted)", margin: 0 }}>
              Топ участников
            </h2>
            {state.data.entries.length > 0 ? (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                {state.data.entries.map((entry) => (
                  <LeaderboardRow key={entry.rank} entry={entry} />
                ))}
              </div>
            ) : (
              <EmptyState text="Пока никто не набрал баллов — станьте первым." />
            )}
          </section>
        </>
      )}
    </div>
  );
}
