import { fetchCommunityUser } from "../api/communityUsers";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { StatusBadge } from "../components/StatusBadge";
import { useAsync } from "../hooks/useAsync";

interface UserPublicProfileScreenProps {
  userId: number;
  onBack?: () => void;
}

export function UserPublicProfileScreen({ userId, onBack }: UserPublicProfileScreenProps) {
  const state = useAsync(() => fetchCommunityUser(userId), [userId]);

  if (state.status === "loading") {
    return <div className="era-page" style={{ padding: "1.25rem" }}><p style={{ color: "var(--era-text-muted)" }}>Открываем профиль…</p></div>;
  }
  if (state.status === "error") {
    return (
      <div className="era-page" style={{ padding: "1.25rem" }}>
        {onBack && <button type="button" onClick={onBack} style={{ marginBottom: ".75rem" }}>← Назад</button>}
        <EmptyState text="Этот объект больше недоступен. Профиль удалён, закрыт или ссылка неверна." />
      </div>
    );
  }

  const user = state.data;
  const initials = user.name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toUpperCase()).join("");

  return (
    <div className="era-page" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: ".8rem" }}>
      {onBack && <button type="button" onClick={onBack} style={{ alignSelf: "flex-start" }}>← Назад</button>}
      <Card gradient style={{ textAlign: "center", padding: "1.3rem" }}>
        <div style={{ width: 72, height: 72, borderRadius: "50%", margin: "0 auto .8rem", display: "grid", placeItems: "center", background: "rgba(255,255,255,.15)", fontSize: "1.35rem", fontWeight: 900 }}>{initials || "Э"}</div>
        <h1 style={{ margin: 0, fontSize: "var(--era-text-2xl)" }}>{user.name}</h1>
        <div style={{ display: "flex", justifyContent: "center", gap: ".4rem", flexWrap: "wrap", marginTop: ".65rem" }}>
          <StatusBadge label={user.role_label} tone="violet" />
          <StatusBadge label={user.participation_label} tone="neutral" />
        </div>
      </Card>
      <Card>
        <strong>В ЭРА</strong>
        {user.departments.length > 0 ? (
          <div style={{ display: "flex", flexDirection: "column", gap: ".45rem", marginTop: ".6rem" }}>
            {user.departments.map((department) => <div key={department} style={{ padding: ".65rem .75rem", borderRadius: ".8rem", background: "rgba(255,255,255,.04)" }}>{department}</div>)}
          </div>
        ) : (
          <p style={{ margin: ".4rem 0 0", color: "var(--era-text-muted)" }}>Участник пока не закреплён за департаментом.</p>
        )}
      </Card>
      <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: ".78rem", textAlign: "center" }}>
        Публичный профиль показывает только роль и участие в структуре. Контакты и другие персональные данные не раскрываются.
      </p>
    </div>
  );
}
