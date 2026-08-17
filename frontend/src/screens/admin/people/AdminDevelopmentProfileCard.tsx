import { fetchAdminDevelopmentProfile } from "../../../api/development";
import { Card } from "../../../components/Card";
import { ProgressRing } from "../../../components/ProgressRing";
import { SkeletonCard } from "../../../components/Skeleton";
import { useAsync } from "../../../hooks/useAsync";
import type { VectorDimension } from "../../../types/development";

const LABELS: Record<VectorDimension, string> = {
  energy: "Энергия",
  agency: "Опора",
  autonomy: "Самостоятельность",
  connection: "Связь",
  direction: "Направление",
};
const DIMENSIONS: VectorDimension[] = ["energy", "agency", "autonomy", "connection", "direction"];

export function AdminDevelopmentProfileCard({ userId }: { userId: number }) {
  const state = useAsync(() => fetchAdminDevelopmentProfile(userId), [userId]);

  if (state.status === "loading") return <SkeletonCard />;
  if (state.status === "error") {
    return (
      <Card>
        <strong>Развитие</strong>
        <p style={{ marginBottom: 0, color: "var(--era-text-muted)" }}>
          Профиль развития не открыт для просмотра или у вас нет права видеть индивидуальные показатели.
        </p>
      </Card>
    );
  }

  const data = state.data;
  return (
    <section style={{ display: "flex", flexDirection: "column", gap: ".75rem", minWidth: 0 }}>
      <div>
        <h2 style={{ margin: 0, fontSize: "var(--era-text-xl)" }}>Развитие</h2>
        <p style={{ margin: ".25rem 0 0", color: "var(--era-text-muted)" }}>
          Только разрешённые участником показатели. Не KPI и не критерий ценности.
        </p>
      </div>

      <Card style={{ padding: "1rem" }}>
        <div style={{ display: "grid", gridTemplateColumns: "auto minmax(0,1fr)", alignItems: "center", gap: "1rem" }}>
          <div style={{ width: 90, height: 90, position: "relative" }}>
            <ProgressRing percent={(data.index ?? 0) / 100} size={90} animationKey={`admin-user-development-${userId}`} />
            <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", textAlign: "center" }}>
              <div><strong style={{ fontSize: "1.25rem" }}>{data.index ?? "—"}</strong><span style={{ display: "block", color: "var(--era-text-muted)", fontSize: ".58rem" }}>СЕЙЧАС</span></div>
            </div>
          </div>
          <div>
            <strong>Последний Check-in</strong>
            <p style={{ margin: ".25rem 0 0", color: "var(--era-text-muted)" }}>
              {data.last_checkin_at ? new Date(data.last_checkin_at).toLocaleDateString("ru-RU") : "ещё не завершён"}
            </p>
          </div>
        </div>
        <div style={{ display: "grid", gap: ".55rem", marginTop: "1rem" }}>
          {DIMENSIONS.map((dimension) => {
            const value = data.state[dimension];
            const latest = data.history[0]?.delta?.[dimension];
            return (
              <div key={dimension} style={{ display: "flex", justifyContent: "space-between", gap: ".75rem" }}>
                <span>{LABELS[dimension]}</span>
                <strong>{value ?? "—"}{latest === undefined ? "" : latest > 0 ? " ↑" : latest < 0 ? " ↓" : " →"}</strong>
              </div>
            );
          })}
        </div>
      </Card>

      {data.strengths?.length ? (
        <Card><strong>Опоры</strong><p style={{ marginBottom: 0 }}>{data.strengths.slice(0, 3).join(" · ")}</p></Card>
      ) : null}

      {data.interests && Object.keys(data.interests).length ? (
        <Card>
          <strong>Интересы</strong>
          <p style={{ marginBottom: 0, color: "var(--era-text-muted)" }}>{humanizeRecord(data.interests)}</p>
        </Card>
      ) : null}

      {data.environment && Object.keys(data.environment).length ? (
        <Card>
          <strong>Предпочтительная среда</strong>
          <p style={{ marginBottom: 0, color: "var(--era-text-muted)" }}>{humanizeRecord(data.environment)}</p>
        </Card>
      ) : null}

      {data.current_focus ? (
        <Card style={{ borderLeft: "3px solid var(--era-red)" }}>
          <small>СЕЙЧАС РАЗВИВАЕТ</small>
          <strong style={{ display: "block", marginTop: 4 }}>{data.current_focus.title}</strong>
          {data.current_focus.experiment ? <p style={{ marginBottom: 0, color: "var(--era-text-muted)" }}>{data.current_focus.experiment}</p> : null}
        </Card>
      ) : null}

      {data.history.length ? (
        <Card>
          <strong>Динамика</strong>
          <div style={{ display: "flex", flexDirection: "column", gap: ".45rem", marginTop: ".65rem" }}>
            {data.history.slice(0, 6).map((item) => (
              <div key={item.month} style={{ display: "flex", justifyContent: "space-between", gap: ".75rem" }}>
                <span>{item.month}</span><strong>{item.index ?? "—"}</strong>
              </div>
            ))}
          </div>
        </Card>
      ) : null}

      <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", lineHeight: 1.5 }}>{data.notice}</p>
    </section>
  );
}

function humanizeRecord(value: Record<string, unknown>): string {
  const topCode = value.top_code;
  if (Array.isArray(topCode) && topCode.length) return topCode.join(" · ");
  return Object.entries(value)
    .filter(([, item]) => typeof item === "string" || typeof item === "number")
    .slice(0, 5)
    .map(([key, item]) => `${key}: ${String(item)}`)
    .join(" · ");
}
