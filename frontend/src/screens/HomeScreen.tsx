import { useCallback, type ReactNode } from "react";
import { fetchWeeklyLeaderboard } from "../api/client";
import { fetchReferralSummary } from "../api/referrals";
import { Avatar } from "../components/Avatar";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { MonoLabel } from "../components/MonoLabel";
import { PosterCard } from "../components/PosterCard";
import { Skeleton, SkeletonCard } from "../components/Skeleton";
import { StatusBanner } from "../components/StatusBanner";
import { EventIcon, ProjectsIcon, TaskIcon } from "../components/icons";
import { useAsync } from "../hooks/useAsync";
import { useHome } from "../hooks/useHome";
import type { MiniAppUserSummary } from "../types/auth";

const ERA_PRO_THRESHOLD = 8_000;

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
  return date.toLocaleDateString("ru-RU", { day: "2-digit", month: "short" }).replace(".", "");
}

function greeting() {
  const hour = new Date().getHours();
  if (hour < 5) return "Доброй ночи";
  if (hour < 12) return "Доброе утро";
  if (hour < 18) return "Добрый день";
  return "Добрый вечер";
}

function formatPoints(value: number) {
  return new Intl.NumberFormat("ru-RU").format(value);
}

function IconBubble({ children, tone }: { children: ReactNode; tone: "violet" | "orange" | "magenta" }) {
  const styles = {
    violet: { background: "var(--era-tint-violet)", color: "var(--era-violet)" },
    orange: { background: "var(--era-tint-gold)", color: "var(--era-gold-ink)" },
    magenta: { background: "rgba(215,25,120,0.10)", color: "var(--era-magenta)" },
  }[tone];
  return (
    <span style={{ flexShrink: 0, width: 40, height: 40, borderRadius: "50%", display: "grid", placeItems: "center", ...styles }}>
      {children}
    </span>
  );
}

export function HomeScreen({
  user,
  onOpenProfile,
  onOpenDevelopment,
  onOpenEvents,
  onOpenEvent,
  onOpenProject,
  onOpenTask,
  onOpenCommunity,
  onOpenOpportunity,
}: HomeScreenProps) {
  const home = useHome();
  const weeklyTop = useAsync(() => fetchWeeklyLeaderboard(), []);
  const referral = useAsync(() => fetchReferralSummary(), []);

  const shareReferral = useCallback(() => {
    if (referral.status !== "ready") return;
    const shareUrl = new URL("https://t.me/share/url");
    shareUrl.searchParams.set("url", referral.data.invite_url);
    shareUrl.searchParams.set("text", referral.data.share_text);
    const webApp = window.Telegram?.WebApp;
    if (webApp?.openTelegramLink) {
      webApp.openTelegramLink(shareUrl.toString());
      return;
    }
    if (navigator.share) {
      void navigator.share({ title: "Присоединяйся к ЭРА", text: referral.data.share_text, url: referral.data.invite_url || undefined });
      return;
    }
    if (navigator.clipboard?.writeText) void navigator.clipboard.writeText(referral.data.invite_url || referral.data.share_text);
  }, [referral]);

  if (home.status === "loading") {
    return (
      <div className="era-page" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <Skeleton width={44} height={44} radius="50%" />
          <div style={{ flex: 1 }}><Skeleton height="1.1rem" width="58%" /></div>
        </div>
        <Skeleton height="15rem" radius="var(--era-radius-xl)" />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  if (home.status === "error") {
    return <StatusBanner title="Не получилось загрузить главную" description="Проверьте соединение и откройте экран ещё раз." />;
  }

  const { data } = home;
  const proRemaining = Math.max(0, ERA_PRO_THRESHOLD - data.points_balance);
  const proPercent = Math.min(100, Math.round((data.points_balance / ERA_PRO_THRESHOLD) * 100));

  const nextStepClick = (() => {
    if (!data.next_step) return undefined;
    const { kind, entity_id } = data.next_step;
    if (kind === "task" && entity_id != null && onOpenTask) return () => onOpenTask(entity_id);
    if (kind === "event" && entity_id != null && onOpenEvent) return () => onOpenEvent(entity_id);
    if (kind === "project" && entity_id != null && onOpenProject) return () => onOpenProject(entity_id);
    if (kind === "opportunity" && entity_id != null && onOpenOpportunity) return () => onOpenOpportunity(entity_id);
    if (kind === "growth" && onOpenDevelopment) return onOpenDevelopment;
    return undefined;
  })();

  const contextual = data.next_step && nextStepClick
    ? { title: data.next_step.title, description: data.next_step.description, onClick: nextStepClick }
    : data.active_task && onOpenTask
      ? { title: data.active_task.title, description: `До ${formatDate(data.active_task.deadline)} · ${data.active_task.points} баллов`, onClick: () => onOpenTask(data.active_task!.id) }
      : data.active_project && onOpenProject
        ? { title: data.active_project.title, description: data.active_project.status, onClick: () => onOpenProject(data.active_project!.id) }
        : { title: "У тебя нет активного проекта", description: "Создать или выбрать проект", onClick: () => { window.location.hash = "#/projects"; } };

  return (
    <div className="era-page era-stagger" style={{ padding: "1.15rem 1.15rem var(--era-page-bottom-safe)", display: "flex", flexDirection: "column", gap: "1.35rem" }}>
      <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem" }}>
        <div>
          <MonoLabel tone="violet">ЭРА</MonoLabel>
          <h1 style={{ margin: "0.35rem 0 0", fontFamily: "var(--era-font-display)", fontSize: "1.8rem", lineHeight: 1.05 }}>
            {greeting()}, {user.first_name}.
          </h1>
          <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-secondary)", fontSize: "0.86rem" }}>
            Вот что сейчас важнее всего.
          </p>
        </div>
        <button type="button" onClick={onOpenProfile} aria-label="Открыть профиль" style={{ minWidth: 44, width: 44, height: 44, minHeight: 44, padding: 0, border: 0, borderRadius: "50%", background: "transparent", boxShadow: "none" }}>
          <Avatar firstName={user.first_name} lastName={user.last_name} />
        </button>
      </header>

      <Card gradient style={{ padding: "1.15rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", alignItems: "flex-start" }}>
          <div>
            <MonoLabel tone="orange">МОЙ ВЕКТОР</MonoLabel>
            <strong style={{ display: "block", marginTop: "0.35rem", fontSize: "1.25rem" }}>{data.growth.label}</strong>
            <span style={{ display: "block", marginTop: "0.2rem", color: "var(--era-text-secondary)" }}>{formatPoints(data.points_balance)} баллов</span>
          </div>
          <strong style={{ fontFamily: "var(--era-font-display)", fontSize: "1.55rem" }}>{proPercent}%</strong>
        </div>

        <div>
          <div style={{ height: 8, borderRadius: 999, overflow: "hidden", background: "var(--era-ring-track)" }}>
            <div style={{ width: `${proPercent}%`, height: "100%", borderRadius: "inherit", background: "var(--era-gradient-signal)" }} />
          </div>
          <p style={{ margin: "0.55rem 0 0", color: "var(--era-text-secondary)", fontSize: "0.84rem", lineHeight: 1.45 }}>
            {proRemaining > 0
              ? `До права подать заявку в ЭРА PRO осталось ${formatPoints(proRemaining)} баллов.`
              : "Порог ЭРА PRO достигнут. Право подать заявку открыто."}
          </p>
        </div>

        <button type="button" className="era-btn-primary" onClick={onOpenDevelopment} disabled={!onOpenDevelopment}>
          Открыть мой вектор
        </button>

        <button type="button" onClick={contextual.onClick} style={{ textAlign: "left", width: "100%", padding: "0.8rem", borderRadius: "var(--era-radius-md)", background: "var(--era-surface-2)", border: "1px solid var(--era-border)" }}>
          <MonoLabel>СЛЕДУЮЩИЙ ШАГ</MonoLabel>
          <strong style={{ display: "block", marginTop: "0.28rem" }}>{contextual.title}</strong>
          <span style={{ display: "block", marginTop: "0.18rem", color: "var(--era-text-secondary)", fontSize: "0.8rem" }}>{contextual.description} →</span>
        </button>
      </Card>

      <section style={{ display: "flex", flexDirection: "column", gap: "0.7rem" }}>
        <MonoLabel>Ближайшее</MonoLabel>
        {data.nearest_event ? (
          <PosterCard
            dark
            eyebrow={formatDate(data.nearest_event.event_date)}
            title={data.nearest_event.title}
            subtitle={`${data.nearest_event.event_time} · ${data.nearest_event.location}`}
            cta="Открыть событие"
            onClick={onOpenEvent ? () => onOpenEvent(data.nearest_event!.id) : onOpenEvents}
          />
        ) : data.active_task && onOpenTask ? (
          <Card onClick={() => onOpenTask(data.active_task!.id)}>
            <div style={{ display: "flex", gap: "0.75rem" }}>
              <IconBubble tone="violet"><TaskIcon width={18} height={18} /></IconBubble>
              <div><strong>{data.active_task.title}</strong><p style={{ margin: ".25rem 0 0", color: "var(--era-text-secondary)" }}>До {formatDate(data.active_task.deadline)}</p></div>
            </div>
          </Card>
        ) : data.active_project && onOpenProject ? (
          <Card onClick={() => onOpenProject(data.active_project!.id)}>
            <div style={{ display: "flex", gap: "0.75rem" }}>
              <IconBubble tone="orange"><ProjectsIcon width={18} height={18} /></IconBubble>
              <div><strong>{data.active_project.title}</strong><p style={{ margin: ".25rem 0 0", color: "var(--era-text-secondary)" }}>{data.active_project.status}</p></div>
            </div>
          </Card>
        ) : <EmptyState text="Сейчас нет ближайшего события или активной задачи." />}
      </section>

      <section style={{ display: "flex", flexDirection: "column", gap: "0.7rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.75rem" }}>
          <MonoLabel>Возможности для тебя</MonoLabel>
          {onOpenCommunity && <button type="button" className="era-btn-ghost" onClick={onOpenCommunity}>Все →</button>}
        </div>
        {data.opportunities.length ? data.opportunities.slice(0, 3).map((item) => (
          <Card key={item.id} onClick={onOpenOpportunity ? () => onOpenOpportunity(item.id) : onOpenCommunity}>
            <div style={{ display: "flex", gap: "0.75rem" }}>
              <IconBubble tone="magenta"><EventIcon width={18} height={18} /></IconBubble>
              <div style={{ minWidth: 0 }}>
                <strong>{item.title}</strong>
                <p style={{ margin: ".25rem 0 0", color: "var(--era-text-secondary)", fontSize: "0.82rem" }}>
                  {item.point_cost ? `От ${formatPoints(item.point_cost)} баллов` : "Доступно участникам"}{item.expires_at ? ` · до ${formatDate(item.expires_at)}` : ""}
                </p>
              </div>
            </div>
          </Card>
        )) : <EmptyState text="Новых персональных возможностей пока нет." />}
      </section>

      <Card onClick={referral.status === "ready" ? shareReferral : undefined} style={{ padding: "1rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "0.9rem", alignItems: "center" }}>
          <div>
            <MonoLabel tone="violet">Пригласи в ЭРА</MonoLabel>
            <strong style={{ display: "block", marginTop: "0.3rem" }}>+100 баллов, если друг действительно включится</strong>
            <p style={{ margin: "0.28rem 0 0", color: "var(--era-text-secondary)", fontSize: "0.8rem" }}>+30 после одобрения · +70 после первого подтверждённого участия</p>
          </div>
          <span aria-hidden="true" style={{ fontSize: "1.15rem" }}>→</span>
        </div>
      </Card>

      {weeklyTop.status === "ready" && weeklyTop.data.entries.length > 0 && (
        <section style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
          <MonoLabel>Топ участников недели</MonoLabel>
          <Card style={{ padding: "0.85rem 1rem" }}>
            {weeklyTop.data.entries.slice(0, 5).map((entry, index) => (
              <div key={`${entry.rank}-${entry.display_name}`} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem", padding: "0.45rem 0", borderBottom: index < Math.min(weeklyTop.data.entries.length, 5) - 1 ? "1px solid var(--era-border)" : "none" }}>
                <div style={{ display: "flex", gap: "0.6rem", minWidth: 0 }}>
                  <strong style={{ width: "1.25rem", color: index < 3 ? "var(--era-violet)" : "var(--era-text-secondary)" }}>{entry.rank}</strong>
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontWeight: entry.is_you ? 800 : 600 }}>{entry.display_name}{entry.is_you ? " · ты" : ""}</span>
                </div>
                <strong style={{ color: "var(--era-violet)" }}>+{entry.points}</strong>
              </div>
            ))}
          </Card>
        </section>
      )}
    </div>
  );
}
