import { useState } from "react";

import { fetchAdminDevelopmentAnalytics } from "../../api/development";
import { Card } from "../../components/Card";
import { ProgressRing } from "../../components/ProgressRing";
import { SkeletonCard } from "../../components/Skeleton";
import { StatusBanner } from "../../components/StatusBanner";
import { useAsync } from "../../hooks/useAsync";
import type { VectorDimension } from "../../types/development";

const LABELS: Record<VectorDimension, string> = {
  energy: "Энергия",
  agency: "Опора",
  autonomy: "Самостоятельность",
  connection: "Связь",
  direction: "Направление",
};

const DIMENSIONS: VectorDimension[] = ["energy", "agency", "autonomy", "connection", "direction"];

export function AdminDevelopmentScreen() {
  const [period, setPeriod] = useState(30);
  const state = useAsync(() => fetchAdminDevelopmentAnalytics(period), [period]);

  if (state.status === "loading") {
    return <><SkeletonCard /><SkeletonCard /></>;
  }
  if (state.status === "error") {
    return <StatusBanner title="Не удалось загрузить аналитику развития" description="Обновите экран и попробуйте ещё раз." />;
  }

  const data = state.data;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem", minWidth: 0 }}>
      <Card gradient>
        <p style={{ margin: 0, color: "rgba(255,255,255,.68)", fontSize: "var(--era-text-xs)", fontWeight: 850, letterSpacing: ".08em" }}>
          ЛЮДИ / СОСТОЯНИЕ
        </p>
        <h2 style={{ margin: ".35rem 0 0", fontSize: "var(--era-text-2xl)" }}>Мой вектор · сообщество</h2>
        <p style={{ margin: ".5rem 0 0", color: "rgba(255,255,255,.76)" }}>
          Добровольные Check-in помогают видеть потребности сообщества. Это не рейтинг людей и не основание для автоматических решений.
        </p>
      </Card>

      <div style={{ display: "flex", gap: ".5rem", flexWrap: "wrap" }}>
        {[30, 90, 180].map((days) => (
          <button key={days} type="button" className={period === days ? "era-btn-primary" : undefined} onClick={() => setPeriod(days)}>
            {days === 30 ? "30 дней" : days === 90 ? "3 месяца" : "6 месяцев"}
          </button>
        ))}
      </div>

      <Card>
        <strong>Охват</strong>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: ".75rem", marginTop: ".75rem" }}>
          <Metric value={`${data.sample_size} / ${data.eligible_profiles}`} label="ответили / участников" />
          <Metric value={`${data.coverage_percent}%`} label="охват Check-in" />
        </div>
        <small style={{ display: "block", marginTop: ".75rem", color: "var(--era-text-muted)" }}>
          Минимальная безопасная группа: {data.minimum_cohort} человек.
        </small>
      </Card>

      {data.suppressed || !data.state ? (
        <Card>
          <strong>Данных пока недостаточно</strong>
          <p style={{ marginBottom: 0, color: "var(--era-text-muted)" }}>
            {data.message ?? "Групповая аналитика появится, когда наберётся минимальная безопасная выборка."}
          </p>
        </Card>
      ) : (
        <>
          <Card style={{ padding: "1.1rem" }}>
            <div style={{ display: "grid", gridTemplateColumns: "auto minmax(0,1fr)", gap: "1rem", alignItems: "center" }}>
              <div style={{ position: "relative", width: 96, height: 96 }}>
                <ProgressRing percent={(data.index ?? 0) / 100} size={96} animationKey={`admin-development-${period}`} />
                <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", textAlign: "center" }}>
                  <div><strong style={{ fontSize: "1.35rem" }}>{data.index ?? "—"}</strong><span style={{ display: "block", color: "var(--era-text-muted)", fontSize: ".62rem" }}>СЕЙЧАС</span></div>
                </div>
              </div>
              <div>
                <strong>Состояние сообщества</strong>
                <p style={{ margin: ".35rem 0 0", color: "var(--era-text-muted)" }}>На основе добровольных Check-in выбранного периода.</p>
              </div>
            </div>
          </Card>

          <Card>
            <strong>Пять областей</strong>
            <div style={{ display: "grid", gap: ".75rem", marginTop: ".8rem" }}>
              {DIMENSIONS.map((dimension) => {
                const value = data.state?.[dimension] ?? 0;
                const delta = data.delta?.[dimension];
                return (
                  <div key={dimension}>
                    <div style={{ display: "flex", justifyContent: "space-between", gap: ".75rem" }}>
                      <span>{LABELS[dimension]}</span>
                      <strong>{Math.round(value)}{delta === undefined ? "" : ` ${delta > 0 ? "↑" : delta < 0 ? "↓" : "→"}`}</strong>
                    </div>
                    <div style={{ height: 6, borderRadius: 999, background: "var(--era-ring-track)", overflow: "hidden", marginTop: 5 }}>
                      <div style={{ width: `${Math.max(0, Math.min(100, value))}%`, height: "100%", background: "var(--era-red)" }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>
        </>
      )}

      {data.development_wants?.length ? (
        <Card>
          <strong>Что люди хотят развивать</strong>
          <div style={{ display: "grid", gap: ".55rem", marginTop: ".75rem" }}>
            {data.development_wants.slice(0, 8).map((item) => (
              <div key={item.key} style={{ display: "flex", justifyContent: "space-between", gap: ".75rem" }}>
                <span>{item.key}</span><strong>{item.percent}%</strong>
              </div>
            ))}
          </div>
        </Card>
      ) : null}

      {data.interests?.length ? (
        <Card>
          <strong>Интересы сообщества</strong>
          <div style={{ display: "grid", gap: ".55rem", marginTop: ".75rem" }}>
            {data.interests.slice(0, 6).map((item) => (
              <div key={item.key} style={{ display: "flex", justifyContent: "space-between", gap: ".75rem" }}>
                <span>{item.key}</span><strong>{item.percent}%</strong>
              </div>
            ))}
          </div>
        </Card>
      ) : null}

      {data.recommendation ? (
        <Card style={{ borderLeft: "3px solid var(--era-gold-ink)" }}>
          <small>ЧТО ЭТО ЗНАЧИТ</small>
          <p style={{ marginBottom: 0 }}>{data.recommendation}</p>
        </Card>
      ) : null}

      <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", lineHeight: 1.5 }}>
        {data.disclaimer ?? "Агрегированные данные не используются для психологического рейтинга, отбора или автоматического назначения ролей."}
      </p>
    </div>
  );
}

function Metric({ value, label }: { value: string; label: string }) {
  return (
    <div style={{ padding: ".8rem", border: "1px solid var(--era-border)", borderRadius: ".85rem", background: "var(--era-bg)" }}>
      <strong style={{ display: "block", fontSize: "1.35rem" }}>{value}</strong>
      <span style={{ color: "var(--era-text-muted)", fontSize: ".72rem" }}>{label}</span>
    </div>
  );
}
