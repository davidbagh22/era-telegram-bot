import { useEffect, useState, type ReactNode } from "react";
import { AchievementOverlay } from "../components/AchievementOverlay";
import { Avatar } from "../components/Avatar";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { FocusCard } from "../components/FocusCard";
import { MetricStrip, SignalMetric } from "../components/MetricStrip";
import { MonoLabel } from "../components/MonoLabel";
import { PosterCard } from "../components/PosterCard";
import { SignalOrb } from "../components/SignalOrb";
import { Skeleton, SkeletonCard } from "../components/Skeleton";
import { StatusBanner } from "../components/StatusBanner";
import { EventIcon, ProjectsIcon, TaskIcon } from "../components/icons";
import { useHome } from "../hooks/useHome";
import type { GrowthProgress, OpportunityProgress } from "../types/home";
import type { MiniAppUserSummary } from "../types/auth";

const LAST_SEEN_LEVEL_KEY = "era.home.lastSeenLevelIndex";

/** Fullscreen "signal mode" the moment a participant's rank actually goes up. */
function useRankUpAchievement(growth: GrowthProgress | null) {
  const [justRankedUp, setJustRankedUp] = useState(false);

  useEffect(() => {
    if (!growth) return;
    let previous: string | null = null;
    try {
      previous = window.localStorage.getItem(LAST_SEEN_LEVEL_KEY);
    } catch {
      return;
    }
    if (previous !== null && Number(previous) < growth.level_index) {
      setJustRankedUp(true);
    }
    try {
      window.localStorage.setItem(LAST_SEEN_LEVEL_KEY, String(growth.level_index));
    } catch {
      // Storage must never block the real Home state.
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
  onOpenCommunity,
  onOpenOpportunity,
}: HomeScreenProps) {
  const home = useHome();
  const achievement = useRankUpAchievement(home.status === "ready" ? home.data.growth : null);

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

  const focus: { title: string; description: string; onClick?: () => void } | null = data.next_step
    ? { title: data.next_step.title, description: data.next_step.description }
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
    <div className="era-page era-stagger" style={{ padding: "1.15rem 1.15rem 1.5rem", display: "flex", flexDirection: "column", gap: "1.75rem" }}>
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

      <button
        type="button"
        onClick={onOpenProgress}
        style={{ all: "unset", cursor: onOpenProgress ? "pointer" : "default", display: "flex", justifyContent: "center", padding: "0.5rem 0 0.25rem" }}
        aria-label="Открыть прогресс роста"
      >
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
              <MonoLabel>Путь роста в ЭРА</MonoLabel>
            </div>
            <div style={{ marginTop: "0.3rem", color: "var(--era-text-secondary)", fontSize: "0.875rem" }}>
              баллов на счету: {data.points_balance}
            </div>
          </div>
        </SignalOrb>
      </button>

      <Card style={{ padding: "1.1rem", display: "flex", flexDirection: "column", gap: "0.9rem" }}>
        <div>
          <MonoLabel>ТВОЙ ПРОГРЕСС</MonoLabel>
          <strong style={{ display: "block", marginTop: "0.35rem", fontSize: "1.12rem" }}>
            {data.rank.rank_label} · {data.points_balance} баллов
          </strong>
          <div style={{ marginTop: "0.2rem", color: "var(--era-text-secondary)", fontSize: "0.86rem" }}>
            {data.rank.next_rank_label ? `Следующий ранг: ${data.rank.next_rank_label}` : "Вы на вершине пути ЭРА"}
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.65rem" }}>
          <div style={{ padding: "0.75rem", borderRadius: "var(--era-radius-md)", background: "var(--era-surface-2)" }}>
            <MonoLabel>Сегодня</MonoLabel>
            <strong style={{ display: "block", marginTop: "0.25rem", fontSize: "1.2rem" }}>+{data.points_today}</strong>
            <span style={{ color: "var(--era-text-secondary)", fontSize: "0.75rem" }}>заработано</span>
          </div>
          <div style={{ padding: "0.75rem", borderRadius: "var(--era-radius-md)", background: "var(--era-surface-2)" }}>
            <MonoLabel>За месяц</MonoLabel>
            <strong style={{ display: "block", marginTop: "0.25rem", fontSize: "1.2rem" }}>+{data.points_month}</strong>
            <span style={{ color: "var(--era-text-secondary)", fontSize: "0.75rem" }}>заработано</span>
          </div>
        </div>

        {data.new_opportunity && (
          <ProgressOpportunityCard
            label="ДОСТУПНО"
            item={data.new_opportunity}
            tone="available"
            onClick={onOpenOpportunity ? () => onOpenOpportunity(data.new_opportunity!.id) : onOpenCommunity}
          />
        )}
        {data.almost_opportunity && (
          <ProgressOpportunityCard
            label="ПОЧТИ ДОСТУПНО"
            item={data.almost_opportunity}
            tone="almost"
            onClick={onOpenOpportunity ? () => onOpenOpportunity(data.almost_opportunity!.id) : onOpenCommunity}
          />
        )}
        {data.locked_opportunity && (
          <ProgressOpportunityCard
            label="ПОКА ЗАКРЫТО"
            item={data.locked_opportunity}
            tone="locked"
            onClick={onOpenOpportunity ? () => onOpenOpportunity(data.locked_opportunity!.id) : onOpenCommunity}
          />
        )}
      </Card>

      {focus && (
        <FocusCard
          eyebrow="ТВОЙ ФОКУС"
          title={focus.title}
          actionLabel={focus.description}
          onClick={focus.onClick}
        />
      )}

      {onOpenDevelopment && (
        <Card gradient onClick={onOpenDevelopment} style={{ padding: "1.15rem" }}>
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
                  {item.point_cost ? `Требуется: ${item.point_cost} баллов` : "Доступно участникам"}{item.expires_at ? ` · до ${formatDate(item.expires_at)}` : ""}
                </p>
              </div>
            </div>
          </Card>
        )) : <EmptyState text="Новых персональных возможностей пока нет." />}
      </section>

      <Card onClick={onOpenCommunity} style={{ padding: "1rem" }}>
        <MonoLabel tone="violet">СКОРО В ЭРА</MonoLabel>
        <strong style={{ display: "block", marginTop: "0.4rem", lineHeight: 1.35 }}>
          Форумы · Стажировки · Делегации · Обучение
        </strong>
        <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-secondary)", fontSize: "0.82rem", lineHeight: 1.45 }}>
          Новые внешние возможности будут появляться здесь по мере запуска — без фиктивных заявок.
        </p>
      </Card>

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

function ProgressOpportunityCard({
  label,
  item,
  tone,
  onClick,
}: {
  label: string;
  item: OpportunityProgress;
  tone: "available" | "almost" | "locked";
  onClick?: () => void;
}) {
  const styleByTone = {
    available: { background: "var(--era-tint-violet)", border: "1px solid rgba(99,44,255,0.18)" },
    almost: { background: "var(--era-tint-gold, var(--era-surface-2))", border: "1px solid rgba(244,193,93,0.38)" },
    locked: { background: "var(--era-surface-2)", border: "1px solid var(--era-border)" },
  }[tone];
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        all: "unset",
        display: "block",
        width: "100%",
        boxSizing: "border-box",
        cursor: onClick ? "pointer" : "default",
        padding: "0.78rem 0.85rem",
        borderRadius: "var(--era-radius-md)",
        ...styleByTone,
      }}
    >
      <MonoLabel tone={tone === "available" ? "violet" : undefined}>{label}</MonoLabel>
      <div style={{ marginTop: "0.25rem", fontWeight: 800 }}>«{item.title}»</div>
      <div style={{ marginTop: "0.18rem", color: "var(--era-text-secondary)", fontSize: "0.78rem" }}>{item.issuer}</div>
      <div style={{ marginTop: "0.35rem", fontSize: "0.84rem" }}>{item.progress_text}</div>
    </button>
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
