import type { ReactNode } from "react";
import { Avatar } from "../components/Avatar";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { ProgressRing } from "../components/ProgressRing";
import { Skeleton, SkeletonCard } from "../components/Skeleton";
import { StatusBanner } from "../components/StatusBanner";
import { EventIcon, OpportunitiesIcon, ProjectsIcon, TaskIcon } from "../components/icons";
import { useHome } from "../hooks/useHome";
import type { MiniAppUserSummary } from "../types/auth";

interface HomeScreenProps {
  user: MiniAppUserSummary;
  onOpenProfile?: () => void;
  onOpenProgress?: () => void;
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
  return date.toLocaleDateString("ru-RU", { day: "2-digit", month: "short" });
}

function isToday(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return false;
  const today = new Date();
  return date.getFullYear() === today.getFullYear() && date.getMonth() === today.getMonth() && date.getDate() === today.getDate();
}

export function HomeScreen({
  user,
  onOpenProfile,
  onOpenProgress,
  onOpenEvents,
  onOpenEvent,
  onOpenProject,
  onOpenTask,
  onOpenCommunity,
  onOpenOpportunity,
}: HomeScreenProps) {
  const home = useHome();

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
        <Skeleton height="12rem" radius="var(--era-radius-card)" />
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

  return (
    <div className="era-page" style={{ padding: "1.15rem 1.15rem 1.5rem", display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <header style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
        <button
          type="button"
          onClick={onOpenProfile}
          aria-label="Открыть профиль"
          style={{ minWidth: 44, width: 44, height: 44, minHeight: 44, padding: 0, border: 0, borderRadius: "50%", background: "transparent", boxShadow: "none" }}
        >
          <Avatar firstName={user.first_name} lastName={user.last_name} />
        </button>
        <button
          type="button"
          onClick={onOpenProfile}
          style={{ flex: 1, minHeight: 44, padding: 0, border: 0, background: "transparent", boxShadow: "none", textAlign: "left" }}
        >
          <strong style={{ display: "block", fontSize: "1.05rem" }}>{user.first_name} {user.last_name ?? ""}</strong>
          <span style={{ display: "block", marginTop: 2, color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>
            {data.growth.label} · уровень {data.growth.level_index + 1}
          </span>
        </button>
      </header>

      <Card gradient onClick={onOpenProgress} style={{ padding: "1.25rem" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "1rem" }}>
          <div style={{ minWidth: 0 }}>
            <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, letterSpacing: ".08em" }}>ERA SCORE</p>
            <div style={{ marginTop: ".15rem", fontFamily: "var(--era-font-display)", fontSize: "clamp(2.75rem, 13vw, 3.5rem)", fontWeight: 850, lineHeight: 1, letterSpacing: "-0.055em" }}>
              {data.points_balance}
            </div>
            <p style={{ margin: ".65rem 0 0", color: "var(--era-text-muted)" }}>
              Нажмите, чтобы увидеть, из чего складывается ваш рост.
            </p>
          </div>
          <div style={{ position: "relative", width: 104, height: 104, flexShrink: 0 }}>
            <ProgressRing percent={orbitPercent} size={104} />
            <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", textAlign: "center" }}>
              <div>
                <strong style={{ display: "block", fontSize: "1.2rem" }}>{Math.round(orbitPercent * 100)}%</strong>
                <span style={{ color: "var(--era-text-muted)", fontSize: ".68rem" }}>до уровня</span>
              </div>
            </div>
          </div>
        </div>
      </Card>

      <section style={{ display: "flex", flexDirection: "column", gap: ".75rem" }}>
        <div>
          <h2 style={{ margin: 0, fontSize: "var(--era-text-xl)" }}>Сегодня</h2>
          <p style={{ margin: ".25rem 0 0", color: "var(--era-text-muted)" }}>Только то, что требует вашего внимания.</p>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: ".6rem" }}>
          <TodayMetric label="События" value={todayEventCount} onClick={todayEventCount ? onOpenEvents : undefined} />
          <TodayMetric label="Задания" value={data.active_task ? 1 : 0} onClick={data.active_task && onOpenTask ? () => onOpenTask(data.active_task!.id) : undefined} />
          <TodayMetric label="Возможности" value={data.opportunities.length} onClick={data.opportunities.length ? onOpenCommunity : undefined} />
        </div>
        {todayEventCount === 0 && onOpenEvents && (
          <button type="button" onClick={onOpenEvents} style={{ width: "100%" }}>Сегодня событий нет · посмотреть ближайшие</button>
        )}
      </section>

      {data.nearest_event && (
        <section style={{ display: "flex", flexDirection: "column", gap: ".75rem" }}>
          <h2 style={{ margin: 0, fontSize: "var(--era-text-xl)" }}>Ближайшее событие</h2>
          <Card onClick={onOpenEvent ? () => onOpenEvent(data.nearest_event!.id) : onOpenEvents} style={{ padding: "1.1rem" }}>
            <div style={{ display: "flex", gap: ".85rem", alignItems: "flex-start" }}>
              <IconBubble tone="red"><EventIcon width={19} height={19} /></IconBubble>
              <div style={{ minWidth: 0 }}>
                <strong style={{ display: "block", fontSize: "1.08rem" }}>{data.nearest_event.title}</strong>
                <p style={{ margin: ".35rem 0 0", color: "var(--era-text-muted)" }}>
                  {formatDate(data.nearest_event.event_date)} · {data.nearest_event.event_time}
                </p>
                <p style={{ margin: ".2rem 0 0", color: "var(--era-text-muted)" }}>{data.nearest_event.location}</p>
              </div>
            </div>
          </Card>
        </section>
      )}

      <section style={{ display: "flex", flexDirection: "column", gap: ".75rem" }}>
        <h2 style={{ margin: 0, fontSize: "var(--era-text-xl)" }}>Следующий шаг</h2>
        {data.next_step || data.active_task || data.active_project ? (
          <div style={{ display: "flex", flexDirection: "column", gap: ".75rem" }}>
            {data.next_step && (
              <Card style={{ borderLeft: "3px solid var(--era-red)" }}>
                <strong>{data.next_step.title}</strong>
                <p style={{ margin: ".35rem 0 0", color: "var(--era-text-muted)" }}>{data.next_step.description}</p>
              </Card>
            )}
            {data.active_task && onOpenTask && (
              <Card onClick={() => onOpenTask(data.active_task!.id)}>
                <div style={{ display: "flex", gap: ".75rem" }}>
                  <IconBubble tone="red"><TaskIcon width={18} height={18} /></IconBubble>
                  <div><strong>{data.active_task.title}</strong><p style={{ margin: ".25rem 0 0", color: "var(--era-text-muted)" }}>До {formatDate(data.active_task.deadline)} · {data.active_task.points} баллов</p></div>
                </div>
              </Card>
            )}
            {data.active_project && onOpenProject && (
              <Card onClick={() => onOpenProject(data.active_project!.id)}>
                <div style={{ display: "flex", gap: ".75rem" }}>
                  <IconBubble tone="gold"><ProjectsIcon width={18} height={18} /></IconBubble>
                  <div><strong>{data.active_project.title}</strong><p style={{ margin: ".25rem 0 0", color: "var(--era-text-muted)" }}>{data.active_project.status}</p></div>
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
          <h2 style={{ margin: 0, fontSize: "var(--era-text-xl)" }}>Для тебя</h2>
          {onOpenCommunity && <button type="button" onClick={onOpenCommunity} style={{ minHeight: 44, padding: ".5rem .8rem" }}>Все</button>}
        </div>
        {data.opportunities.length ? data.opportunities.slice(0, 3).map((item) => (
          <Card key={item.id} onClick={onOpenOpportunity ? () => onOpenOpportunity(item.id) : onOpenCommunity}>
            <div style={{ display: "flex", gap: ".75rem" }}>
              <IconBubble tone="gold"><OpportunitiesIcon width={18} height={18} /></IconBubble>
              <div style={{ minWidth: 0 }}>
                <strong>{item.title}</strong>
                <p style={{ margin: ".25rem 0 0", color: "var(--era-text-muted)" }}>
                  {item.point_cost ? `${item.point_cost} баллов` : "Доступно участникам"}{item.expires_at ? ` · до ${formatDate(item.expires_at)}` : ""}
                </p>
              </div>
            </div>
          </Card>
        )) : <EmptyState text="Новых персональных возможностей пока нет." />}
      </section>
    </div>
  );
}

function TodayMetric({ label, value, onClick }: { label: string; value: number; onClick?: () => void }) {
  const content = <><strong style={{ display: "block", fontSize: "1.45rem", color: value ? "var(--era-red)" : "var(--era-text)" }}>{value}</strong><span style={{ display: "block", marginTop: 2, color: "var(--era-text-muted)", fontSize: ".72rem" }}>{label}</span></>;
  if (!onClick) return <Card style={{ padding: ".8rem", textAlign: "center", boxShadow: "none" }}>{content}</Card>;
  return <Card onClick={onClick} style={{ padding: ".8rem", textAlign: "center", boxShadow: "none" }}>{content}</Card>;
}

function IconBubble({ children, tone }: { children: ReactNode; tone: "red" | "gold" }) {
  const styleByTone = tone === "gold"
    ? { background: "var(--era-tint-gold)", color: "var(--era-gold-ink)" }
    : { background: "var(--era-tint-red)", color: "var(--era-red)" };
  return <span style={{ flexShrink: 0, width: 40, height: 40, borderRadius: "50%", display: "grid", placeItems: "center", ...styleByTone }}>{children}</span>;
}
