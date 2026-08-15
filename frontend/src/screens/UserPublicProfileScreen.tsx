import { fetchCommunityUser } from "../api/communityUsers";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { PageHeader } from "../components/PageHeader";
import { SecondaryButton } from "../components/Buttons";
import { SkeletonCard } from "../components/Skeleton";
import { StatusBadge } from "../components/StatusBadge";
import { useAsync } from "../hooks/useAsync";

interface UserPublicProfileScreenProps { userId: number; onBack?: () => void; }

export function UserPublicProfileScreen({ userId, onBack }: UserPublicProfileScreenProps) {
  const state = useAsync(() => fetchCommunityUser(userId), [userId]);
  const back = onBack ?? (() => { if (window.history.length > 1) window.history.back(); else window.location.hash = "#/community"; });

  if (state.status === "loading") return <div className="era-page era-page-shell"><PageHeader title="Профиль" onBack={back} /><SkeletonCard /><SkeletonCard /></div>;
  if (state.status === "error") return <div className="era-page era-page-shell"><PageHeader title="Профиль" onBack={back} /><EmptyState title="Этот профиль больше недоступен" description="Возможно, пользователь удалён, заблокирован или доступ изменился." actionLabel="Вернуться в сообщество" onAction={() => { window.location.hash = "#/community"; }} /></div>;

  const user = state.data;
  const initials = user.name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toUpperCase()).join("");

  return (
    <div className="era-page era-page-shell">
      <PageHeader title="Публичный профиль" eyebrow="Сообщество ЭРА" onBack={back} />
      <Card style={{ textAlign: "center", padding: "1.3rem" }}>
        <div style={{ width: 78, height: 78, borderRadius: "50%", margin: "0 auto 0.8rem", display: "grid", placeItems: "center", background: "linear-gradient(145deg,var(--era-bg-subtle),#fff)", border: "1px solid var(--era-border)", fontSize: "1.35rem", fontWeight: 900 }}>{initials || "Э"}</div>
        <h1 style={{ margin: 0, fontSize: "var(--era-text-2xl)" }}>{user.name}</h1>
        {user.username && <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)" }}>@{user.username}</p>}
        <div style={{ display: "flex", justifyContent: "center", gap: "0.4rem", flexWrap: "wrap", marginTop: "0.65rem" }}><StatusBadge label={user.role_label} tone="neutral" /><StatusBadge label={user.participation_label} tone="neutral" /></div>
      </Card>

      <div className="era-grid-2">
        <Metric value={user.events_attended} label="события" />
        <Metric value={user.project_memberships} label="проекты" />
        <Metric value={user.tasks_completed} label="задания" />
        <Metric value={user.directions.length} label="интересы" />
      </div>

      {(user.departments.length > 0 || user.directions.length > 0) && <Card><strong>В ЭРА</strong>{user.departments.length > 0 && <p style={{ margin: "0.55rem 0 0", color: "var(--era-text-muted)" }}>Структура: {user.departments.join(", ")}</p>}{user.directions.length > 0 && <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem", marginTop: "0.65rem" }}>{user.directions.map((direction) => <span key={direction} style={{ padding: "0.35rem 0.55rem", borderRadius: 999, background: "var(--era-tint-red)", color: "var(--era-deep-red)", fontSize: "var(--era-text-xs)", fontWeight: 750 }}>{direction}</span>)}</div>}</Card>}

      {user.telegram_url ? <a href={user.telegram_url} target="_blank" rel="noreferrer" className="era-btn-primary">Связаться в Telegram</a> : <SecondaryButton disabled>Контакт Telegram не указан</SecondaryButton>}
      <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", textAlign: "center" }}>Телефон, email, дата рождения, анкета и другие личные данные публично не раскрываются.</p>
    </div>
  );
}

function Metric({ value, label }: { value: number; label: string }) { return <Card style={{ boxShadow: "none" }}><strong style={{ fontSize: "1.65rem" }}>{value}</strong><span style={{ display: "block", marginTop: 4, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>{label}</span></Card>; }
