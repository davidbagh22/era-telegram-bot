import { fetchHome, fetchLeaderboard } from "../../api/client";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { MonoLabel } from "../../components/MonoLabel";
import { SkeletonList } from "../../components/Skeleton";
import { useAsync } from "../../hooks/useAsync";

const RANKS: { key: string; label: string }[] = [
  { key: "new_member", label: "Новый участник" },
  { key: "involved_member", label: "Вовлечённый участник" },
  { key: "active_member", label: "Активный участник" },
  { key: "team_member", label: "Член команды" },
  { key: "project_curator", label: "Куратор проекта" },
  { key: "community_leader", label: "Лидер сообщества" },
];

function formatPoints(value: number): string {
  return new Intl.NumberFormat("ru-RU").format(value);
}

export function RanksPanel() {
  const home = useAsync(() => fetchHome(), []);
  const board = useAsync(() => fetchLeaderboard(), []);

  if (home.status === "loading" || board.status === "loading") {
    return <SkeletonList count={2} />;
  }
  if (home.status === "error") {
    return (
      <EmptyState
        title="Не удалось загрузить ранги"
        text="Проверьте соединение и обновите раздел."
        actionLabel="Обновить"
        onAction={() => { home.reload(); board.reload(); }}
      />
    );
  }

  const { rank, points_balance } = home.data;
  const currentIndex = Math.max(0, RANKS.findIndex((item) => item.key === rank.rank));
  const openLeaderboard = () => {
    if (window.location.hash !== "#/leaderboard") window.location.hash = "#/leaderboard";
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
      <Card gradient style={{ padding: "1.05rem" }}>
        <MonoLabel tone="violet">Ваш ранг</MonoLabel>
        <strong style={{ display: "block", marginTop: "0.35rem", fontSize: "1.2rem", lineHeight: 1.3 }}>
          {rank.rank_label}
        </strong>
        <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-secondary)", fontSize: "0.86rem" }}>
          {formatPoints(points_balance)} баллов
          {rank.next_rank_label ? ` · дальше — ${rank.next_rank_label}` : " · высший ранг достигнут"}
        </p>
      </Card>

      <Card style={{ padding: "0.95rem" }}>
        <MonoLabel>Лестница рангов</MonoLabel>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.45rem", marginTop: "0.7rem" }}>
          {RANKS.map((item, index) => {
            const current = index === currentIndex;
            const reached = index <= currentIndex;
            return (
              <div
                key={item.key}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.65rem",
                  padding: "0.55rem 0.65rem",
                  borderRadius: "var(--era-radius-md)",
                  background: current ? "var(--era-tint-violet)" : "transparent",
                  border: current ? "1px solid rgba(99,44,255,.22)" : "1px solid transparent",
                }}
              >
                <span
                  aria-hidden="true"
                  style={{
                    width: 10,
                    height: 10,
                    borderRadius: "50%",
                    flexShrink: 0,
                    background: reached ? "var(--era-violet)" : "var(--era-border)",
                  }}
                />
                <span
                  style={{
                    flex: 1,
                    fontWeight: current ? 800 : 600,
                    color: current ? "var(--era-violet)" : reached ? "var(--era-text)" : "var(--era-text-muted)",
                    fontSize: "0.9rem",
                  }}
                >
                  {item.label}
                </span>
                {current && (
                  <span style={{ fontSize: "0.72rem", fontWeight: 800, color: "var(--era-violet)" }}>сейчас</span>
                )}
              </div>
            );
          })}
        </div>
      </Card>

      <section style={{ display: "flex", flexDirection: "column", gap: "0.55rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.75rem" }}>
          <MonoLabel>Рейтинг по баллам</MonoLabel>
          <button type="button" className="era-btn-ghost" onClick={openLeaderboard}>
            Весь рейтинг →
          </button>
        </div>
        {board.status === "error" && (
          <EmptyState
            title="Рейтинг временно недоступен"
            text="Обновите список лидеров чуть позже."
            actionLabel="Обновить"
            onAction={board.reload}
          />
        )}
        {board.status === "ready" && (
          <>
            {board.data.me && (
              <Card style={{ background: "var(--era-tint-violet)", border: "1px solid rgba(99,44,255,.22)", padding: "0.8rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "baseline" }}>
                  <strong style={{ color: "var(--era-violet)" }}>
                    #{board.data.me.rank} · Вы
                  </strong>
                  <strong style={{ fontVariantNumeric: "tabular-nums" }}>{formatPoints(board.data.me.points)}</strong>
                </div>
                <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)", fontSize: "0.78rem" }}>
                  {board.data.me.growth_level}
                </p>
              </Card>
            )}
            <div style={{ display: "flex", flexDirection: "column", gap: "0.45rem" }}>
              {board.data.entries.slice(0, 5).map((entry) => (
                <Card key={`${entry.rank}-${entry.display_name}`} style={{ padding: "0.75rem 0.85rem" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.7rem" }}>
                    <span
                      style={{
                        width: 28,
                        height: 28,
                        borderRadius: "50%",
                        display: "grid",
                        placeItems: "center",
                        fontWeight: 800,
                        fontSize: "0.75rem",
                        background: entry.rank === 1 ? "var(--era-tint-gold)" : "var(--era-surface-2)",
                        color: entry.rank === 1 ? "var(--era-gold-ink)" : "var(--era-text-muted)",
                        flexShrink: 0,
                      }}
                    >
                      {entry.rank}
                    </span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <strong
                        style={{
                          display: "block",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                          fontSize: "0.92rem",
                        }}
                      >
                        {entry.display_name}
                        {entry.is_you ? " · Вы" : ""}
                      </strong>
                    </div>
                    <strong style={{ fontVariantNumeric: "tabular-nums", flexShrink: 0 }}>
                      {formatPoints(entry.points)}
                    </strong>
                  </div>
                </Card>
              ))}
              {board.data.entries.length === 0 && (
                <EmptyState text="Пока никто не набрал баллов — станьте первым." />
              )}
            </div>
          </>
        )}
      </section>
    </div>
  );
}
