import { useEffect, useState } from "react";
import {
  fetchParticipationPeople,
  fetchParticipationSummary,
  type ParticipationPerson,
  type ParticipationSummary,
} from "../../api/adminParticipation";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { MonoLabel } from "../../components/MonoLabel";
import { StatusBanner } from "../../components/StatusBanner";

const STATE_LABELS: Record<string, string> = {
  ADAPTATION: "Адаптация",
  ACTIVE: "Активные",
  COOLING: "Cooling",
  INACTIVE: "Неактивные",
  DORMANT: "Dormant",
  ARCHIVE_CANDIDATE: "Кандидаты на архив",
};

const MODE_LABELS: Record<string, string> = {
  ACTIVE: "Активный режим",
  LIGHT: "Лёгкий режим",
  PAUSED: "На паузе",
  OBSERVER: "Наблюдатели",
  EXITED: "Вышли",
};

type Drilldown =
  | { label: string; state: string }
  | { label: string; mode: string }
  | { label: string; returned30d: true }
  | { label: string };

export function AdminParticipationScreen() {
  const [summary, setSummary] = useState<ParticipationSummary | null>(null);
  const [people, setPeople] = useState<ParticipationPerson[]>([]);
  const [drilldown, setDrilldown] = useState<Drilldown>({ label: "Текущий состав" });
  const [loading, setLoading] = useState(true);
  const [peopleLoading, setPeopleLoading] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    void fetchParticipationSummary()
      .then((data) => {
        setSummary(data);
        setError(false);
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  async function open(next: Drilldown) {
    setDrilldown(next);
    setPeopleLoading(true);
    try {
      const data = await fetchParticipationPeople({
        state: "state" in next ? next.state : undefined,
        mode: "mode" in next ? next.mode : undefined,
        returned30d: "returned30d" in next ? next.returned30d : undefined,
      });
      setPeople(data);
    } finally {
      setPeopleLoading(false);
    }
  }

  useEffect(() => {
    void open({ label: "Текущий состав" });
  }, []);

  if (loading) return <p style={{ color: "var(--era-text-muted)" }}>Считаем состояния участников…</p>;
  if (error || !summary) return <StatusBanner title="Не удалось загрузить состояния" description="Попробуйте открыть раздел ещё раз." />;

  const kpis: Array<{ label: string; value: number; drilldown: Drilldown }> = [
    { label: "Текущий состав", value: summary.current_roster, drilldown: { label: "Текущий состав" } },
    { label: "Активная база", value: summary.active_base, drilldown: { label: "Активная база", state: "ACTIVE" } },
    { label: "Новые 30 дней", value: summary.new_30d, drilldown: { label: "Новые 30 дней" } },
    { label: "Вернулись 30 дней", value: summary.returned_30d, drilldown: { label: "Вернулись за 30 дней", returned30d: true } },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      <Card gradient>
        <MonoLabel tone="violet">LIFECYCLE</MonoLabel>
        <h2 style={{ margin: ".35rem 0 0" }}>Состояние участников</h2>
        <p style={{ margin: ".45rem 0 0", color: "var(--era-text-secondary)" }}>
          Режим выбирает человек. Activity State система считает только по подтверждённым действиям и текущей ответственности.
        </p>
      </Card>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: ".55rem" }}>
        {kpis.map((item) => (
          <button key={item.label} type="button" onClick={() => void open(item.drilldown)} style={{ border: 0, padding: 0, background: "transparent", textAlign: "left" }}>
            <Card style={{ minHeight: 104, padding: ".85rem" }}>
              <strong style={{ fontSize: "1.7rem" }}>{item.value}</strong>
              <span style={{ display: "block", marginTop: ".3rem", fontSize: ".78rem" }}>{item.label}</span>
            </Card>
          </button>
        ))}
      </div>

      <section>
        <MonoLabel>ACTIVITY STATE</MonoLabel>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: ".45rem", marginTop: ".55rem" }}>
          {Object.entries(STATE_LABELS).map(([key, label]) => (
            <button key={key} type="button" className="era-btn-secondary" onClick={() => void open({ label, state: key })} style={{ justifyContent: "space-between" }}>
              <span>{label}</span><strong>{summary.states[key] ?? 0}</strong>
            </button>
          ))}
        </div>
      </section>

      <section>
        <MonoLabel>РЕЖИМ УЧАСТИЯ</MonoLabel>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: ".45rem", marginTop: ".55rem" }}>
          {Object.entries(MODE_LABELS).map(([key, label]) => (
            <button key={key} type="button" className="era-btn-secondary" onClick={() => void open({ label, mode: key })} style={{ justifyContent: "space-between" }}>
              <span>{label}</span><strong>{summary.modes[key] ?? 0}</strong>
            </button>
          ))}
        </div>
      </section>

      <section>
        <div style={{ display: "flex", justifyContent: "space-between", gap: ".75rem", alignItems: "baseline" }}>
          <h3 style={{ margin: 0 }}>{drilldown.label}</h3>
          <span style={{ color: "var(--era-text-muted)", fontSize: ".78rem" }}>{people.length}</span>
        </div>
        {peopleLoading ? (
          <p style={{ color: "var(--era-text-muted)" }}>Загружаем список…</p>
        ) : people.length === 0 ? (
          <EmptyState text="В этом сегменте никого нет." />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: ".45rem", marginTop: ".55rem" }}>
            {people.map((person) => (
              <Card key={person.id} style={{ padding: ".8rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: ".65rem" }}>
                  <div style={{ minWidth: 0 }}>
                    <strong style={{ overflowWrap: "anywhere" }}>{person.name}</strong>
                    <span style={{ display: "block", color: "var(--era-text-muted)", fontSize: ".75rem", marginTop: ".2rem" }}>
                      {STATE_LABELS[person.activity_state] ?? person.activity_state} · {MODE_LABELS[person.participation_mode] ?? person.participation_mode}
                    </span>
                    {person.last_meaningful_at && (
                      <span style={{ display: "block", color: "var(--era-text-muted)", fontSize: ".72rem", marginTop: ".15rem" }}>
                        Последнее действие: {new Date(person.last_meaningful_at).toLocaleDateString("ru-RU")}
                      </span>
                    )}
                  </div>
                  <button type="button" className="era-btn-ghost" onClick={() => { window.location.hash = `#/users/${person.id}`; }}>Открыть →</button>
                </div>
              </Card>
            ))}
          </div>
        )}
      </section>

      <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: ".75rem" }}>
        Historical approved: {summary.historical_approved}. EXITED сохраняются в истории, но не входят в текущий состав. PAUSED/OBSERVER не входят в Active Base.
      </p>
    </div>
  );
}
