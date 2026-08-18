import { useEffect, useState, type ReactNode } from "react";
import { fetchWeeklyLeaderboard } from "../api/client";
import { AchievementOverlay } from "../components/AchievementOverlay";
import { Avatar } from "../components/Avatar";
import { BottomSheet } from "../components/BottomSheet";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { FocusCard } from "../components/FocusCard";
import { MetricStrip, SignalMetric } from "../components/MetricStrip";
import { MonoLabel } from "../components/MonoLabel";
import { PosterCard } from "../components/PosterCard";
import { SignalOrb } from "../components/SignalOrb";
import { Skeleton, SkeletonCard } from "../components/Skeleton";
import { StatusBanner } from "../components/StatusBanner";
import { VectorHalo } from "../components/VectorHalo";
import { EventIcon, ProjectsIcon, TaskIcon } from "../components/icons";
import { useAsync } from "../hooks/useAsync";
import { useHome } from "../hooks/useHome";
import type { GrowthProgress, VectorHomeSummary } from "../types/home";
import type { MiniAppUserSummary } from "../types/auth";

const AREA_LABELS: Record<string, string> = {
  energy: "Энергия",
  support: "Опора",
  autonomy: "Самостоятельность",
  connection: "Связь",
  direction: "Направление",
};

const LAST_SEEN_LEVEL_KEY = "era.home.lastSeenLevelIndex";

/** Fullscreen "signal mode" (ToR §28) the moment a participant's rank
 * actually goes up — never on ordinary loads. Purely client-side and
 * presentational: compares the level index the browser last recorded
 * against the one the API just returned, and shows the celebratory
 * overlay only on a genuine increase (never on first-ever load, since
 * there is nothing to compare against yet). */
function useRankUpAchievement(growth: GrowthProgress | null) {
  const [justRankedUp, setJustRankedUp] = useState(false);

  useEffect(() => {
    if (!growth) return;
    let previous: string | null = null;
    try {
      previous = window.localStorage.getItem(LAST_SEEN_LEVEL_KEY);
    } catch {
      // Storage unavailable (private mode, etc.) — skip the celebration,
      // never block rendering the real level.
      return;
    }
    if (previous !== null && Number(previous) < growth.level_index) {
      setJustRankedUp(true);
    }
    try {
      window.localStorage.setItem(LAST_SEEN_LEVEL_KEY, String(growth.level_index));
    } catch {
      // Ignore — nothing else depends on this write succeeding.
    }
  }, [growth]);

  return { justRankedUp, dismiss: () => setJustRankedUp(false) };
}

interface HomeScreenProps {
  user: MiniAppUserSummary;
  onOpenProfile?: () => void;
  onOpenProgress?: () => void;
  onOpenDevelopment?: () => void;
  onOpenEvents?: () => void;
  onOpenEvent?: (id: number) => void;
  onOpenProject?: (id: number) => void;
  onOpenTask?: (id: number) => void;
  onOpenTasks?: () => void;
  onOpenCommunity?: () => void;
  onOpenOpportunity?: (id: number) => void;
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("ru-RU", { day: "2-digit", month: "short" }).toUpperCase().replace(".", "");
}

function isToday(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return false;
  const today = new Date();
  return date.getFullYear() === today.getFullYear() && date.getMonth() === today.getMonth() && date.getDate() === today.getDate();
}

function greeting() {
  const hour = new Date().getHours();
  if (hour < 5) return "Доброй ночи";
  if (hour < 12) return "Доброе утро";
  if (hour < 18) return "Добрый день";
  return "Добрый вечер";
}

export function HomeScreen({
  user,
  onOpenProfile,
  onOpenProgress,
  onOpenDevelopment,
  onOpenEvents,
  onOpenEvent,
  onOpenProject,
  onOpenTask,
  onOpenTasks,
  onOpenCommunity,
  onOpenOpportunity,
}: HomeScreenProps) {
  const home = useHome();
  const achievement = useRankUpAchievement(home.status === "ready" ? home.data.growth : null);
  const [pulseSheetOpen, setPulseSheetOpen] = useState(false);
  const weeklyTop = useAsync(() => fetchWeeklyLeaderboard(), []);

  if (home.status === "loading") {
    return (
      <div className="era-page" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <Avatar firstName={user.first_name} lastName={user.last_name} />
          <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "0.375rem" }}>
            <Skeleton height="1.125rem" width="60%" />
            <Skeleton height="0.75rem" width="40%" />
          </div>
        </div>
        <Skeleton height="16rem" radius="var(--era-radius-xl)" />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  if (home.status === "error") {
    return <StatusBanner title="Не получилось загрузить главную" description="Проверьте соединение и откройте экран ещё раз." />;
  }

  const { data } = home;
  const growthPercent = data.growth.level_count <= 1 ? 1 : data.growth.level_index / (data.growth.level_count - 1);
  const orbitPercent = Math.max(0, Math.min(1, growthPercent));
  const todayEventCount = data.nearest_event && isToday(data.nearest_event.event_date) ? 1 : 0;
  const levelTag = `${String(data.growth.level_index + 1).padStart(2, "0")} / ${data.growth.label.toUpperCase()}`;

  // DELTA ToR §6: every next_step must resolve to a real tap action --
  // never a card that looks interactive but does nothing. next_step.kind
  // picks which existing on-open callback owns the entity_id; "growth" has
  // no single entity and always routes to the Vector/development screen.
  function nextStepOnClick(): (() => void) | undefined {
    if (!data.next_step) return undefined;
    const { kind, entity_id } = data.next_step;
    if (kind === "task" && entity_id != null && onOpenTask) return () => onOpenTask(entity_id);
    if (kind === "event" && entity_id != null && onOpenEvent) return () => onOpenEvent(entity_id);
    if (kind === "project" && entity_id != null && onOpenProject) return () => onOpenProject(entity_id);
    if (kind === "opportunity" && entity_id != null && onOpenOpportunity) return () => onOpenOpportunity(entity_id);
    if (kind === "growth" && onOpenDevelopment) return onOpenDevelopment;
    return undefined;
  }

  const focus: { title: string; description: string; onClick?: () => void } | null = data.next_step
    ? { title: data.next_step.title, description: data.next_step.description, onClick: nextStepOnClick() }
    : data.active_task
      ? {
          title: data.active_task.title,
          description: `До ${formatDate(data.active_task.deadline)} · ${data.active_task.points} баллов`,
          onClick: onOpenTask ? () => onOpenTask(data.active_task!.id) : undefined,
        }
      : data.active_project
        ? {
            title: data.active_project.title,
            description: data.active_project.status,
            onClick: onOpenProject ? () => onOpenProject(data.active_project!.id) : undefined,
          }
        : null;

  return (
    <div className="era-page era-stagger" style={{ padding: "1.15rem 1.15rem var(--era-page-bottom-safe)", display: "flex", flexDirection: "column", gap: "1.75rem" }}>
      <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem" }}>
        <MonoLabel tone="violet">ЭРА</MonoLabel>
        <button
          type="button"
          onClick={onOpenProfile}
          aria-label="Открыть профиль"
          style={{ minWidth: 44, width: 44, height: 44, minHeight: 44, padding: 0, border: 0, borderRadius: "50%", background: "transparent", boxShadow: "none" }}
        >
          <Avatar firstName={user.first_name} lastName={user.last_name} />
        </button>
      </header>

      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "1rem" }}>
        <h1
          style={{
            margin: 0,
            fontFamily: "var(--era-font-display)",
            fontSize: "clamp(1.6rem, 8vw, 2.1rem)",
            fontWeight: 800,
            lineHeight: 1.1,
            letterSpacing: "-0.025em",
          }}
        >
          {greeting()},<br />{user.first_name}.
        </h1>
        <div style={{ textAlign: "right", flexShrink: 0, paddingTop: "0.3rem" }}>
          <MonoLabel>УРОВЕНЬ</MonoLabel>
          <div style={{ marginTop: "0.2rem", fontWeight: 800, fontSize: "var(--era-text-sm)" }}>{levelTag}</div>
        </div>
      </div>

      {/* ToR §2-4: the orb is "Пульс участника" -- progress ring + a halo
          of 5 small My Vector signals, tap opens the "Твой пульс" detail
          sheet (which itself hands off to full Progress/Vector screens). */}
      <button
        type="button"
        onClick={() => setPulseSheetOpen(true)}
        style={{ all: "unset", cursor: "pointer", display: "flex", justifyContent: "center", padding: "0.5rem 0 0.25rem", position: "relative" }}
        aria-label="Открыть твой пульс"
      >
        <div style={{ position: "relative", display: "grid", placeItems: "center" }}>
          <VectorHalo orbSize={232} areas={data.vector?.areas ?? null} />
          <SignalOrb percent={orbitPercent} size={232} animationKey="home-signal-orb">
            <div>
              <strong
                style={{
                  display: "block",
                  fontFamily: "var(--era-font-display)",
                  fontSize: "3.25rem",
                  fontWeight: 900,
                  lineHeight: 1,
                  letterSpacing: "-0.03em",
                }}
              >
                {Math.round(orbitPercent * 100)}%
              </strong>
              <div style={{ marginTop: "0.6rem" }}>
                <MonoLabel>До следующего ранга</MonoLabel>
              </div>
              <div style={{ marginTop: "0.3rem", color: "var(--era-text-secondary)", fontSize: "0.875rem" }}>
                баллов на счету: {data.points_balance}
              </div>
              <div style={{ marginTop: "0.55rem", paddingTop: "0.55rem", borderTop: "1px solid var(--era-border)" }}>
                {data.vector ? (
                  <>
                    <div style={{ fontSize: "0.8rem", fontWeight: 800 }}>Мой вектор · {data.vector.pulse}</div>
                    {data.vector.signals.slice(0, 2).map((signal) => (
                      <div key={signal.area} style={{ fontSize: "0.75rem", color: "var(--era-text-secondary)" }}>
                        {signal.label} {signal.value} {signal.trend === "up" ? "↑" : "↓"}
                      </div>
                    ))}
                  </>
                ) : (
                  <div style={{ fontSize: "0.8rem", color: "var(--era-text-secondary)" }}>Мой вектор ещё не заполнен · Пройти →</div>
                )}
              </div>
            </div>
          </SignalOrb>
        </div>
      </button>

      <PulseSheet
        open={pulseSheetOpen}
        onClose={() => setPulseSheetOpen(false)}
        orbitPercent={orbitPercent}
        vector={data.vector}
        onOpenProgress={onOpenProgress}
        onOpenDevelopment={onOpenDevelopment}
      />

      {/* Points/Ranks ToR §39/49: rank + the nearest real Opportunity,
          honestly computed -- no fabricated "points until next rank" (rank
          is metrics-based, not points-linear, see progression_service.py). */}
      <Card style={{ padding: "1.1rem" }}>
        <MonoLabel>{data.rank.rank_label.toUpperCase()}</MonoLabel>
        <strong style={{ display: "block", marginTop: "0.35rem", fontSize: "1.05rem" }}>
          {data.rank.next_rank_label ? `Следующий ранг: ${data.rank.next_rank_label}` : "Вы на вершине пути ЭРА"}
        </strong>
        {data.new_opportunity && (
          <button
            type="button"
            onClick={onOpenOpportunity ? () => onOpenOpportunity(data.new_opportunity!.id) : onOpenCommunity}
            style={{
              all: "unset",
              display: "block",
              width: "100%",
              boxSizing: "border-box",
              cursor: onOpenOpportunity || onOpenCommunity ? "pointer" : "default",
              marginTop: "0.85rem",
              padding: "0.75rem 0.85rem",
              borderRadius: "var(--era-radius-md)",
              background: "var(--era-tint-violet)",
            }}
          >
            <MonoLabel tone="violet">Новая возможность</MonoLabel>
            <div style={{ marginTop: "0.25rem", fontWeight: 800 }}>«{data.new_opportunity.title}»</div>
          </button>
        )}
        {!data.new_opportunity && data.nearest_locked_opportunity && (
          <button
            type="button"
            onClick={onOpenOpportunity ? () => onOpenOpportunity(data.nearest_locked_opportunity!.id) : onOpenCommunity}
            style={{
              all: "unset",
              display: "block",
              width: "100%",
              boxSizing: "border-box",
              cursor: onOpenOpportunity || onOpenCommunity ? "pointer" : "default",
              marginTop: "0.85rem",
              padding: "0.75rem 0.85rem",
              borderRadius: "var(--era-radius-md)",
              background: "var(--era-surface-2)",
            }}
          >
            <div style={{ color: "var(--era-text-secondary)", fontSize: "0.85rem" }}>
              До «{data.nearest_locked_opportunity.title}» ({data.nearest_locked_opportunity.issuer})
            </div>
            <div style={{ marginTop: "0.2rem", fontWeight: 800 }}>
              осталось {data.nearest_locked_opportunity.points_needed} баллов
            </div>
          </button>
        )}
      </Card>

      {/* ToR §6: "Карточки без action запрещены" -- if nothing resolved an
          onClick (e.g. a callback prop wasn't passed in), don't show a
          focus card that looks tappable but isn't. */}
      {focus && focus.onClick && (
        <FocusCard
          eyebrow="ТВОЙ ФОКУС"
          title={focus.title}
          actionLabel={focus.description}
          onClick={focus.onClick}
        />
      )}

      {/* ToR §15: compact "Задания" entry point -- Tasks has no bottom-nav
          slot of its own, so Home is one of its main doors in. */}
      {onOpenTasks && (
        <Card onClick={onOpenTasks} style={{ padding: "1.1rem" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem" }}>
            <div style={{ minWidth: 0 }}>
              <MonoLabel tone="violet">Задания</MonoLabel>
              <strong style={{ display: "block", marginTop: ".3rem", fontSize: "1.05rem" }}>
                {data.tasks_available_count} доступно · {data.tasks_in_progress_count} в работе
              </strong>
            </div>
            <span aria-hidden="true" style={{ color: "var(--era-text-muted)", fontSize: "1.125rem", flexShrink: 0 }}>→</span>
          </div>
        </Card>
      )}

      {onOpenDevelopment && (
        <Card
          gradient
          onClick={onOpenDevelopment}
          style={{ padding: "1.15rem" }}
        >
          <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: "1rem", alignItems: "center" }}>
            <div style={{ minWidth: 0 }}>
              <MonoLabel tone="orange">МОЙ ВЕКТОР</MonoLabel>
              <strong style={{ display: "block", marginTop: ".4rem", fontSize: "1.1rem", lineHeight: 1.2 }}>Как ты изменился за последний месяц?</strong>
              <p style={{ margin: ".45rem 0 0", color: "var(--era-text-secondary)" }}>Проверить себя · 6 мин</p>
            </div>
            <div aria-hidden="true" style={{ width: 52, height: 52, borderRadius: "50%", display: "grid", placeItems: "center", background: "var(--era-gradient-signal)", boxShadow: "var(--era-glow-hot)" }}>
              <span style={{ fontSize: "1.15rem", fontWeight: 900, color: "#fff" }}>↗</span>
            </div>
          </div>
        </Card>
      )}

      <section style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        <MonoLabel>Сейчас в ЭРА</MonoLabel>
        <MetricStrip>
          <SignalMetric tone="violet" value={todayEventCount} label="событий сегодня" onClick={todayEventCount ? onOpenEvents : undefined} />
          <SignalMetric tone="orange" value={data.active_task ? 1 : 0} label="активных заданий" onClick={data.active_task && onOpenTask ? () => onOpenTask(data.active_task!.id) : undefined} />
          <SignalMetric tone="magenta" value={data.opportunities.length} label="новых возможностей" onClick={data.opportunities.length ? onOpenCommunity : undefined} />
        </MetricStrip>
        {todayEventCount === 0 && onOpenEvents && (
          <button type="button" onClick={onOpenEvents} className="era-btn-ghost" style={{ width: "100%", justifyContent: "flex-start", padding: "0.25rem 0" }}>
            Сегодня событий нет · посмотреть ближайшие →
          </button>
        )}
      </section>

      {data.nearest_event && (
        <section style={{ display: "flex", flexDirection: "column", gap: ".85rem" }}>
          <MonoLabel>Ближайшее событие</MonoLabel>
          <PosterCard
            dark
            eyebrow={formatDate(data.nearest_event.event_date)}
            title={data.nearest_event.title}
            subtitle={`${data.nearest_event.event_time} · ${data.nearest_event.location}`}
            cta="Участвовать"
            onClick={onOpenEvent ? () => onOpenEvent(data.nearest_event!.id) : onOpenEvents}
          />
        </section>
      )}

      <section style={{ display: "flex", flexDirection: "column", gap: ".75rem" }}>
        <MonoLabel>Следующий шаг</MonoLabel>
        {data.active_task || data.active_project ? (
          <div style={{ display: "flex", flexDirection: "column", gap: ".75rem" }}>
            {data.active_task && onOpenTask && (
              <Card onClick={() => onOpenTask(data.active_task!.id)}>
                <div style={{ display: "flex", gap: ".75rem" }}>
                  <IconBubble tone="violet"><TaskIcon width={18} height={18} /></IconBubble>
                  <div><strong>{data.active_task.title}</strong><p style={{ margin: ".25rem 0 0", color: "var(--era-text-secondary)" }}>До {formatDate(data.active_task.deadline)} · {data.active_task.points} баллов</p></div>
                </div>
              </Card>
            )}
            {data.active_project && onOpenProject && (
              <Card onClick={() => onOpenProject(data.active_project!.id)}>
                <div style={{ display: "flex", gap: ".75rem" }}>
                  <IconBubble tone="orange"><ProjectsIcon width={18} height={18} /></IconBubble>
                  <div><strong>{data.active_project.title}</strong><p style={{ margin: ".25rem 0 0", color: "var(--era-text-secondary)" }}>{data.active_project.status}</p></div>
                </div>
              </Card>
            )}
          </div>
        ) : (
          <EmptyState text="Срочных действий нет. Можно выбрать новый проект или событие." />
        )}
      </section>

      <section style={{ display: "flex", flexDirection: "column", gap: ".75rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: ".75rem" }}>
          <MonoLabel>Для тебя</MonoLabel>
          {onOpenCommunity && <button type="button" onClick={onOpenCommunity} className="era-btn-ghost" style={{ padding: ".4rem .2rem" }}>Все →</button>}
        </div>
        {data.opportunities.length ? data.opportunities.slice(0, 3).map((item) => (
          <Card key={item.id} onClick={onOpenOpportunity ? () => onOpenOpportunity(item.id) : onOpenCommunity}>
            <div style={{ display: "flex", gap: ".75rem" }}>
              <IconBubble tone="magenta"><EventIcon width={18} height={18} /></IconBubble>
              <div style={{ minWidth: 0 }}>
                <strong>{item.title}</strong>
                <p style={{ margin: ".25rem 0 0", color: "var(--era-text-secondary)" }}>
                  {item.point_cost ? `${item.point_cost} баллов` : "Доступно участникам"}{item.expires_at ? ` · до ${formatDate(item.expires_at)}` : ""}
                </p>
              </div>
            </div>
          </Card>
        )) : <EmptyState text="Новых персональных возможностей пока нет." />}
      </section>

      {/* ToR §52-54: Топ-5 недели -- no dedicated screen needed, this is
          the primary entry point. Rows aren't tappable unless a public
          profile is actually reachable at #/users/{id} (see UserPublicProfileScreen). */}
      {weeklyTop.status === "ready" && weeklyTop.data.entries.length > 0 && (
        <section style={{ display: "flex", flexDirection: "column", gap: ".6rem" }}>
          <MonoLabel>Топ недели</MonoLabel>
          <Card style={{ padding: "0.9rem 1.1rem" }}>
            {weeklyTop.data.entries.map((entry, index) => (
              <div
                key={entry.rank}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  gap: ".6rem",
                  padding: ".45rem 0",
                  borderBottom: index < weeklyTop.data.entries.length - 1 ? "1px solid var(--era-border)" : "none",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: ".6rem", minWidth: 0 }}>
                  <span style={{ fontWeight: 900, fontSize: index < 3 ? "1.05rem" : "0.9rem", color: index < 3 ? "var(--era-violet)" : "var(--era-text-secondary)", width: "1.4rem", flexShrink: 0 }}>
                    {entry.rank}
                  </span>
                  <span style={{ fontWeight: entry.is_you ? 800 : 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {entry.display_name}{entry.is_you ? " · ты" : ""}
                  </span>
                </div>
                <strong style={{ flexShrink: 0, color: "var(--era-violet)" }}>+{entry.points}</strong>
              </div>
            ))}
          </Card>
        </section>
      )}

      <AchievementOverlay
        open={achievement.justRankedUp}
        onClose={achievement.dismiss}
        kicker="Новый уровень"
        title={<>ТЫ ТЕПЕРЬ<br />{data.growth.label.toUpperCase()}</>}
        description="Продолжай в том же духе — это заметно."
      />
    </div>
  );
}

function IconBubble({ children, tone }: { children: ReactNode; tone: "violet" | "orange" | "magenta" }) {
  const styleByTone = {
    violet: { background: "var(--era-tint-violet)", color: "var(--era-violet)" },
    orange: { background: "var(--era-tint-gold)", color: "var(--era-gold-ink)" },
    magenta: { background: "rgba(215,25,120,0.10)", color: "var(--era-magenta)" },
  }[tone];
  return <span style={{ flexShrink: 0, width: 40, height: 40, borderRadius: "50%", display: "grid", placeItems: "center", ...styleByTone }}>{children}</span>;
}

/** ToR §4: tapping the main orb opens this detail sheet -- "Активность в
 * ЭРА" percent plus the full My Vector breakdown (all 5 areas, not just
 * the 1-2 the orb itself has room for), then hands off to the two real
 * screens (Progress / My Vector) rather than duplicating them here. */
function PulseSheet({
  open,
  onClose,
  orbitPercent,
  vector,
  onOpenProgress,
  onOpenDevelopment,
}: {
  open: boolean;
  onClose: () => void;
  orbitPercent: number;
  vector: VectorHomeSummary | null;
  onOpenProgress?: () => void;
  onOpenDevelopment?: () => void;
}) {
  return (
    <BottomSheet open={open} onClose={onClose} title="Твой пульс">
      <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        <div>
          <MonoLabel>Активность в ЭРА</MonoLabel>
          <strong style={{ display: "block", fontSize: "1.75rem", marginTop: ".25rem" }}>{Math.round(orbitPercent * 100)}%</strong>
        </div>

        <div>
          <MonoLabel tone="violet">Мой вектор</MonoLabel>
          {vector ? (
            <>
              <strong style={{ display: "block", fontSize: "1.5rem", margin: ".25rem 0 .6rem" }}>{vector.pulse} / 100</strong>
              <div style={{ display: "flex", flexDirection: "column", gap: ".35rem" }}>
                {Object.entries(vector.areas).map(([area, value]) => (
                  <div key={area} style={{ display: "flex", justifyContent: "space-between", fontSize: ".9rem" }}>
                    <span style={{ color: "var(--era-text-secondary)" }}>{AREA_LABELS[area] ?? area}</span>
                    <strong>{value}</strong>
                  </div>
                ))}
              </div>
              <p style={{ margin: ".7rem 0 0", color: "var(--era-text-muted)", fontSize: ".78rem" }}>
                Последнее обновление: {new Date(vector.updated_at).toLocaleDateString("ru-RU", { day: "numeric", month: "long" })}
              </p>
            </>
          ) : (
            <p style={{ margin: ".35rem 0 0", color: "var(--era-text-secondary)" }}>Мой вектор ещё не заполнен.</p>
          )}
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: ".5rem" }}>
          {onOpenProgress && (
            <button type="button" className="era-btn-primary" onClick={() => { onClose(); onOpenProgress(); }}>
              Открыть мой прогресс
            </button>
          )}
          {onOpenDevelopment && (
            <button type="button" onClick={() => { onClose(); onOpenDevelopment(); }}>
              Открыть Мой вектор
            </button>
          )}
        </div>
      </div>
    </BottomSheet>
  );
}
