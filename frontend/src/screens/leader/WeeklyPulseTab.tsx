import { useEffect, useMemo, useState } from "react";
import {
  fetchCurrentLeadershipPulse,
  fetchLeadershipFeedback,
  submitLeadershipPulse,
} from "../../api/leadership";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { MetricCard } from "../../components/MetricCard";
import type { LeadershipFeedback, LeadershipWeeklyReport } from "../../types/leadership";

const STATUS_OPTIONS = [
  { value: "green", label: "В темпе" },
  { value: "yellow", label: "Нужно внимание" },
  { value: "red", label: "Нужна помощь" },
] as const;

function ScoreField({
  label,
  value,
  onChange,
  hint,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  hint: string;
}) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: "0.45rem" }}>
      <span style={{ fontWeight: 800 }}>{label}: {value}/5</span>
      <input
        aria-label={label}
        type="range"
        min={1}
        max={5}
        step={1}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
      <span style={{ color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>{hint}</span>
    </label>
  );
}

export function WeeklyPulseTab() {
  const [report, setReport] = useState<LeadershipWeeklyReport | null>(null);
  const [feedback, setFeedback] = useState<LeadershipFeedback[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<"green" | "yellow" | "red">("green");
  const [pace, setPace] = useState(3);
  const [clarity, setClarity] = useState(3);
  const [load, setLoad] = useState(3);
  const [mainResult, setMainResult] = useState("");
  const [priority, setPriority] = useState("");
  const [attention, setAttention] = useState("");
  const [needsHelp, setNeedsHelp] = useState(false);
  const [blocker, setBlocker] = useState("");

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const current = await fetchCurrentLeadershipPulse();
        if (!active) return;
        setReport(current);
        setStatus(current.status);
        setPace(current.pace_score ?? 3);
        setClarity(current.clarity_score ?? 3);
        setLoad(current.load_score ?? 3);
        setMainResult(current.main_result ?? "");
        setPriority(current.next_priorities[0] ?? "");
        setAttention(current.attention_text ?? "");
        setNeedsHelp(current.needs_help);
        setBlocker(current.blocker_note ?? "");
        try {
          setFeedback(await fetchLeadershipFeedback(current.id));
        } catch {
          setFeedback([]);
        }
      } catch {
        if (active) setError("Не удалось открыть Weekly Pulse.");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const facts = report?.system_snapshot;
  const period = useMemo(() => {
    if (!report) return "";
    return `${report.period_start} — ${report.period_end}`;
  }, [report]);

  async function submit() {
    if (!report || saving) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await submitLeadershipPulse({
        status,
        main_result: mainResult,
        blocker_note: blocker,
        next_priorities: priority.trim() ? [priority.trim()] : [],
        needs_help: needsHelp || status === "red",
        office_assignment_id: report.office_assignment_id,
        pace_score: pace,
        clarity_score: clarity,
        load_score: load,
        attention_text: attention,
      });
      setReport(updated);
      setFeedback(await fetchLeadershipFeedback(updated.id));
    } catch {
      setError("Не удалось сохранить Weekly Pulse. Проверьте данные и повторите.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <p style={{ color: "var(--era-text-muted)" }}>Собираем факты недели…</p>;
  }
  if (!report || !facts) {
    return <EmptyState text={error ?? "Weekly Pulse пока недоступен."} />;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      <Card>
        <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>
          Система уже знает
        </p>
        <h2 style={{ margin: "0.35rem 0 0", fontSize: "var(--era-text-xl)" }}>Факты недели</h2>
        <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)" }}>
          {period}. Эти показатели формируются системой и не редактируются лидером.
        </p>
      </Card>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.5rem" }}>
        <MetricCard label="Команда" value={facts.team_size} />
        <MetricCard label="Закрыто задач" value={facts.tasks_completed_this_week} />
        <MetricCard label="Просрочено" value={facts.tasks_overdue} />
        <MetricCard label="Активные проекты" value={facts.projects_active} />
        <MetricCard label="События недели" value={facts.events_this_week} />
        <MetricCard label="Активные цели" value={facts.active_goals} />
      </div>

      <Card style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        <div>
          <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>
            Ваша оценка
          </p>
          <h2 style={{ margin: "0.35rem 0 0", fontSize: "var(--era-text-xl)" }}>Weekly Pulse</h2>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "0.5rem" }}>
          {STATUS_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              aria-pressed={status === option.value}
              onClick={() => setStatus(option.value)}
              style={{ minHeight: 52, fontWeight: 800 }}
            >
              {option.label}
            </button>
          ))}
        </div>

        <ScoreField label="Темп" value={pace} onChange={setPace} hint="1 — сильно отстаём, 5 — идём уверенно" />
        <ScoreField label="Ясность" value={clarity} onChange={setClarity} hint="Насколько команде понятны приоритеты" />
        <ScoreField label="Нагрузка" value={load} onChange={setLoad} hint="1 — легко, 5 — перегруз" />

        <label style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
          <strong>Главный результат недели</strong>
          <textarea value={mainResult} onChange={(event) => setMainResult(event.target.value)} maxLength={1000} rows={3} />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
          <strong>Следующий приоритет</strong>
          <input value={priority} onChange={(event) => setPriority(event.target.value)} maxLength={300} />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
          <strong>Что требует внимания</strong>
          <textarea value={attention} onChange={(event) => setAttention(event.target.value)} maxLength={1000} rows={2} />
        </label>
        <label style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
          <input type="checkbox" checked={needsHelp} onChange={(event) => setNeedsHelp(event.target.checked)} />
          <span>Нужна помощь вышестоящего руководителя</span>
        </label>
        {(needsHelp || status === "red") && (
          <label style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
            <strong>Блокер</strong>
            <textarea value={blocker} onChange={(event) => setBlocker(event.target.value)} maxLength={1000} rows={2} />
          </label>
        )}

        {error && <p role="alert" style={{ margin: 0 }}>{error}</p>}
        <button type="button" disabled={saving} onClick={() => void submit()} style={{ minHeight: 48, fontWeight: 900 }}>
          {saving ? "Сохраняем…" : report.submitted_at ? "Обновить Weekly Pulse" : "Отправить Weekly Pulse"}
        </button>
        {report.submitted_at && (
          <p style={{ margin: 0, color: "var(--era-text-muted)" }}>
            Последняя отправка: {new Date(report.submitted_at).toLocaleString("ru-RU")}
          </p>
        )}
      </Card>

      <section>
        <h2 style={{ fontSize: "0.875rem", color: "var(--era-text-muted)", margin: "0 0 0.5rem" }}>
          Обратная связь
        </h2>
        {feedback.length === 0 ? (
          <EmptyState text="Обратной связи по этому Pulse пока нет." />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {feedback.map((item) => (
              <Card key={item.id}>
                <strong>{item.status === "follow_up" ? "Нужен следующий шаг" : item.status === "resolved" ? "Закрыто" : "Принято"}</strong>
                {item.comment && <p style={{ margin: "0.35rem 0 0" }}>{item.comment}</p>}
              </Card>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
