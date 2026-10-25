import { useMemo, useState } from "react";
import { fetchEraPro, submitEraPro, type EraProApplicationPayload } from "../api/eraPro";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { MonoLabel } from "../components/MonoLabel";
import { SkeletonCard } from "../components/Skeleton";
import { StatusBanner } from "../components/StatusBanner";
import { useAsync } from "../hooks/useAsync";

const DIRECTIONS = [
  ["diplomacy", "Дипломатия"],
  ["international_relations", "Международные отношения"],
  ["entrepreneurship", "Предпринимательство"],
  ["management", "Управление"],
  ["public_speaking", "Публичные выступления"],
  ["culture", "Культура"],
  ["education", "Образование"],
  ["media", "Медиа"],
  ["social_projects", "Социальные проекты"],
  ["project_work", "Проектная деятельность"],
  ["other", "Другие направления"],
] as const;

const BENEFITS = [
  ["Наставники", "Люди с реальным профессиональным опытом."],
  ["Закрытые встречи", "Общение в небольшом кругу."],
  ["Вопрос — ответ", "Возможность получать обратную связь."],
  ["Возможности", "Отборы, проекты, мероприятия и предложения."],
  ["Связи", "Окружение активных участников."],
  ["Материалы", "Опыт, рекомендации и полезные ресурсы."],
] as const;

const PRO_SECTIONS = [
  ["announcements", "Объявления", "Главное, что происходит внутри ЭРА PRO: встречи, обновления и важные сообщения."],
  ["opportunities", "Возможности", "Закрытые отборы, проекты, мероприятия и профессиональные предложения."],
  ["qa", "Вопрос — Ответ", "Место для вопросов наставникам и экспертам по реальным задачам развития."],
  ["community", "Общение", "Связь с участниками закрытого сообщества и людьми из разных профессиональных сфер."],
  ["materials", "Полезные материалы", "Подборки, рекомендации и ресурсы от наставников и команды ЭРА."],
] as const;

type ProSectionKey = typeof PRO_SECTIONS[number][0];

function formatPoints(value: number) {
  return new Intl.NumberFormat("ru-RU").format(value);
}

function statusCopy(status: string, comment?: string | null) {
  if (status === "submitted") return { title: "Заявка рассматривается", text: "Команда ЭРА изучает ответы и историю вашей активности. Баллы остаются на вашем счёте." };
  if (status === "needs_info") return { title: "Нужно дополнить", text: comment || "Команда ЭРА попросила уточнить информацию в заявке." };
  if (status === "approved") return { title: "Вы в ЭРА PRO", text: "Доступ открыт. Теперь закрытые возможности и форматы ЭРА PRO доступны в этом разделе." };
  if (status === "declined") return { title: "Рассмотрение завершено", text: "Сейчас доступ не выдан. Это не списывает баллы и не закрывает возможность подать новую заявку позже." };
  return null;
}

export function EraProScreen({ onBack }: { onBack?: () => void }) {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchEraPro(), [refreshKey]);
  const [editing, setEditing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState<ProSectionKey>("announcements");
  const [form, setForm] = useState<EraProApplicationPayload>({
    motivation: "",
    directions: [],
    target_result: "",
    community_value: "",
    portfolio_url: "",
  });

  const activeSectionData = useMemo(() => PRO_SECTIONS.find(([key]) => key === activeSection)!, [activeSection]);

  if (state.status === "loading") {
    return <div className="era-page" style={{ padding: "1.25rem", display: "grid", gap: "0.8rem" }}>{onBack && <button type="button" onClick={onBack}>← Назад</button>}<SkeletonCard /><SkeletonCard /></div>;
  }
  if (state.status === "error") return <StatusBanner title="Не удалось открыть ЭРА PRO" description="Попробуйте открыть раздел ещё раз." />;

  const data = state.data;
  const status = statusCopy(data.status, data.application?.admin_comment);
  const percent = Math.min(100, Math.round((data.points / Math.max(1, data.threshold)) * 100));

  const beginApplication = () => {
    setForm({
      motivation: data.application?.motivation ?? "",
      directions: data.application?.directions ?? [],
      target_result: data.application?.target_result ?? "",
      community_value: data.application?.community_value ?? "",
      portfolio_url: data.application?.portfolio_url ?? "",
    });
    setError(null);
    setEditing(true);
  };

  const toggleDirection = (key: string) => {
    setForm((current) => {
      const selected = current.directions.includes(key);
      if (selected) return { ...current, directions: current.directions.filter((item) => item !== key) };
      if (current.directions.length >= 6) return current;
      return { ...current, directions: [...current.directions, key] };
    });
  };

  const submit = async () => {
    setError(null);
    if (form.motivation.trim().length < 20 || form.target_result.trim().length < 20 || form.community_value.trim().length < 20 || form.directions.length === 0) {
      setError("Заполните три содержательных ответа и выберите хотя бы одно направление.");
      return;
    }
    setSubmitting(true);
    try {
      await submitEraPro({ ...form, portfolio_url: form.portfolio_url?.trim() || null }, data.status === "needs_info");
      setEditing(false);
      setRefreshKey((value) => value + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось отправить заявку.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="era-page era-stagger" style={{ padding: "1.2rem 1.2rem var(--era-page-bottom-safe)", display: "flex", flexDirection: "column", gap: "1rem" }}>
      {onBack && <button type="button" onClick={onBack} style={{ alignSelf: "flex-start" }}>← Назад</button>}

      <Card gradient>
        <MonoLabel tone="violet">ЭРА PRO</MonoLabel>
        <h1 style={{ margin: "0.35rem 0 0", fontFamily: "var(--era-font-display)", fontSize: "1.8rem" }}>Следующий уровень твоего окружения.</h1>
        <p style={{ margin: "0.55rem 0 0", color: "var(--era-text-secondary)", lineHeight: 1.55 }}>
          Закрытая среда молодых лидеров и наставников, где можно получать обратную связь, находить связи, общаться с экспертами и открывать новые профессиональные возможности.
        </p>
        <p style={{ margin: "0.75rem 0 0", fontWeight: 850, color: "var(--era-violet)" }}>Ты не покупаешь вход. Ты открываешь его своей активностью.</p>
      </Card>

      <Card>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "0.8rem", alignItems: "baseline" }}>
          <div><MonoLabel>Порог подачи заявки</MonoLabel><strong style={{ display: "block", marginTop: "0.25rem", fontSize: "1.3rem" }}>{formatPoints(data.points)} / {formatPoints(data.threshold)}</strong></div>
          <strong>{percent}%</strong>
        </div>
        <div style={{ height: 8, marginTop: "0.7rem", borderRadius: 999, overflow: "hidden", background: "var(--era-ring-track)" }}><div style={{ width: `${percent}%`, height: "100%", background: "var(--era-gradient-signal)" }} /></div>
        <p style={{ margin: "0.55rem 0 0", color: "var(--era-text-muted)", fontSize: "0.82rem" }}>
          {data.remaining_points > 0 ? `Ещё ${formatPoints(data.remaining_points)} баллов до права подать заявку.` : "Порог достигнут. Баллы не списываются при подаче или после одобрения."}
        </p>
        {data.status === "locked" && <button type="button" onClick={() => { window.location.hash = "#/development"; }} style={{ marginTop: "0.7rem" }}>Как приблизиться →</button>}
      </Card>

      <section>
        <h2 style={{ margin: "0 0 0.65rem", fontSize: "1.15rem" }}>Направления наставников</h2>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.45rem" }}>{DIRECTIONS.map(([, label]) => <span key={label} style={{ padding: "0.46rem 0.66rem", borderRadius: 999, background: "var(--era-surface-2)", border: "1px solid var(--era-border)", fontSize: "0.78rem", fontWeight: 700 }}>{label}</span>)}</div>
      </section>

      <section>
        <h2 style={{ margin: "0 0 0.65rem", fontSize: "1.15rem" }}>Что получает участник</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.55rem" }}>{BENEFITS.map(([title, text]) => <Card key={title} style={{ padding: "0.8rem" }}><strong>{title}</strong><p style={{ margin: "0.28rem 0 0", color: "var(--era-text-muted)", fontSize: "0.78rem", lineHeight: 1.4 }}>{text}</p></Card>)}</div>
      </section>

      {status && <StatusBanner title={status.title} description={status.text} />}

      {!editing && data.status === "available" && <button type="button" className="era-btn-primary" onClick={beginApplication}>Подать заявку в ЭРА PRO</button>}
      {!editing && data.status === "needs_info" && <button type="button" className="era-btn-primary" onClick={beginApplication}>Дополнить заявку</button>}
      {!editing && data.status === "declined" && data.eligible && <button type="button" className="era-btn-primary" onClick={beginApplication}>Подать новую заявку</button>}

      {editing && (
        <Card style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
          <div><MonoLabel tone="violet">Заявка ЭРА PRO</MonoLabel><h2 style={{ margin: "0.25rem 0 0" }}>Расскажи, куда хочешь вырасти</h2></div>
          <Field label="Почему вы хотите попасть в ЭРА PRO?" value={form.motivation} onChange={(value) => setForm((current) => ({ ...current, motivation: value }))} />
          <div>
            <strong style={{ display: "block", marginBottom: "0.45rem" }}>В каких направлениях хотите развиваться?</strong>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>{DIRECTIONS.map(([key, label]) => {
              const active = form.directions.includes(key);
              return <button key={key} type="button" aria-pressed={active} onClick={() => toggleDirection(key)} style={{ padding: "0.5rem 0.65rem", borderRadius: 999, border: active ? "1px solid var(--era-violet)" : "1px solid var(--era-border)", background: active ? "var(--era-tint-violet)" : "var(--era-surface-2)", color: active ? "var(--era-violet)" : "var(--era-text)" }}>{label}</button>;
            })}</div>
            <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)", fontSize: "0.75rem" }}>Можно выбрать до 6 направлений.</p>
          </div>
          <Field label="Какой результат хотите получить за ближайшие 3–6 месяцев?" value={form.target_result} onChange={(value) => setForm((current) => ({ ...current, target_result: value }))} />
          <Field label="Чем можете быть полезны сообществу?" value={form.community_value} onChange={(value) => setForm((current) => ({ ...current, community_value: value }))} />
          <label><strong style={{ display: "block", marginBottom: "0.4rem" }}>Ссылка на проект / портфолио <span style={{ color: "var(--era-text-muted)", fontWeight: 500 }}>необязательно</span></strong><input type="url" value={form.portfolio_url ?? ""} onChange={(event) => setForm((current) => ({ ...current, portfolio_url: event.target.value }))} placeholder="https://…" /></label>
          {error && <p style={{ margin: 0, color: "var(--era-error)", fontSize: "0.82rem" }}>{error}</p>}
          <div style={{ display: "grid", gridTemplateColumns: "0.8fr 1.2fr", gap: "0.5rem" }}><button type="button" disabled={submitting} onClick={() => setEditing(false)}>Отмена</button><button type="button" className="era-btn-primary" disabled={submitting} onClick={() => void submit()}>{submitting ? "Отправляем…" : "Отправить заявку"}</button></div>
        </Card>
      )}

      {data.has_access && (
        <section style={{ display: "flex", flexDirection: "column", gap: "0.7rem" }}>
          <h2 style={{ margin: 0, fontSize: "1.15rem" }}>Внутри ЭРА PRO</h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.45rem" }}>{PRO_SECTIONS.map(([key, label]) => <button key={key} type="button" aria-pressed={activeSection === key} onClick={() => setActiveSection(key)} style={{ minWidth: 0, padding: "0.62rem", borderRadius: "var(--era-radius-control)", border: activeSection === key ? "1px solid var(--era-violet)" : "1px solid var(--era-border)", background: activeSection === key ? "var(--era-tint-violet)" : "var(--era-surface)", color: activeSection === key ? "var(--era-violet)" : "var(--era-text)", fontWeight: 750 }}>{label}</button>)}</div>
          <Card><MonoLabel tone="violet">{activeSectionData[1]}</MonoLabel><p style={{ margin: "0.4rem 0 0", color: "var(--era-text-secondary)", lineHeight: 1.5 }}>{activeSectionData[2]}</p></Card>
        </section>
      )}

      {!data.eligible && !editing && <EmptyState text="Продолжайте участвовать в проектах, событиях и подтверждённых активностях — система сама откроет право подачи заявки после 8 000 баллов." />}
    </div>
  );
}

function Field({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label><strong style={{ display: "block", marginBottom: "0.4rem" }}>{label}</strong><textarea rows={4} value={value} onChange={(event) => onChange(event.target.value)} style={{ minHeight: 105 }} /></label>;
}
