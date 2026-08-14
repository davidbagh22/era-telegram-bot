import { useState } from "react";
import { createAdminEvent } from "../../../api/adminEvents";
import { describeActionError } from "../../../api/client";
import { Card } from "../../../components/Card";

export function AdminEventCreatePanel() {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [eventDate, setEventDate] = useState("");
  const [eventTime, setEventTime] = useState("");
  const [location, setLocation] = useState("");
  const [format, setFormat] = useState("");
  const [participantLimit, setParticipantLimit] = useState("");
  const [points, setPoints] = useState("5");
  const [needsVolunteers, setNeedsVolunteers] = useState(false);
  const [additionalInfo, setAdditionalInfo] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const submit = async (publish: boolean) => {
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const limit = Number(participantLimit);
      const pointValue = Number(points);
      const event = await createAdminEvent({
        title: title.trim(),
        description: description.trim(),
        event_date: eventDate,
        event_time: eventTime,
        location: location.trim(),
        format: format.trim(),
        participant_limit: Number.isFinite(limit) && limit > 0 ? limit : undefined,
        points_for_visit: Number.isFinite(pointValue) ? pointValue : 5,
        needs_volunteers: needsVolunteers,
        additional_info: additionalInfo.trim() || undefined,
        publish,
      });
      setSuccess(
        publish
          ? `«${event.title}» создано. Регистрация уже открыта.`
          : `«${event.title}» сохранено как черновик.`,
      );
      setTitle("");
      setDescription("");
      setEventDate("");
      setEventTime("");
      setLocation("");
      setFormat("");
      setParticipantLimit("");
      setAdditionalInfo("");
    } catch (reason) {
      setError(describeActionError(reason));
    } finally {
      setBusy(false);
    }
  };

  const valid =
    title.trim().length >= 3 &&
    description.trim().length >= 10 &&
    eventDate &&
    eventTime &&
    location.trim().length >= 2 &&
    format.trim().length >= 2;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <Card gradient>
        <p style={{ margin: "0 0 0.25rem", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase", color: "rgba(255,255,255,0.72)" }}>
          Конструктор мероприятия
        </p>
        <h2 style={{ margin: 0, fontSize: "var(--era-text-2xl)" }}>От идеи до регистрации</h2>
        <p style={{ margin: "0.5rem 0 0", color: "rgba(255,255,255,0.82)", lineHeight: 1.45 }}>
          Заполните базовые данные. Можно сохранить черновик или сразу открыть регистрацию — без скрытых дополнительных шагов.
        </p>
      </Card>

      <Card>
        <Field label="Название" hint="Коротко и понятно: человек должен за секунду понять, куда его зовут.">
          <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Например: Медиа без скуки" />
        </Field>
        <Field label="Описание" hint="Что произойдёт, для кого это и с чем участник уйдёт после встречи.">
          <textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={5} placeholder="Два-три живых абзаца о пользе и формате" />
        </Field>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
          <Field label="Дата"><input type="date" value={eventDate} onChange={(event) => setEventDate(event.target.value)} /></Field>
          <Field label="Время"><input type="time" value={eventTime} onChange={(event) => setEventTime(event.target.value)} /></Field>
        </div>
        <Field label="Место" hint="Конкретное название или понятная точка сбора.">
          <input value={location} onChange={(event) => setLocation(event.target.value)} placeholder="Дом Москвы, лофт №11" />
        </Field>
        <Field label="Формат" hint="Мастер-класс, игра, встреча, квест, лекция, выезд и т.д.">
          <input value={format} onChange={(event) => setFormat(event.target.value)} placeholder="Мастер-класс + практика" />
        </Field>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
          <Field label="Лимит участников"><input inputMode="numeric" value={participantLimit} onChange={(event) => setParticipantLimit(event.target.value)} placeholder="30" /></Field>
          <Field label="Баллы за участие"><input inputMode="numeric" value={points} onChange={(event) => setPoints(event.target.value)} /></Field>
        </div>
        <label style={{ display: "flex", gap: "0.65rem", alignItems: "center", padding: "0.7rem 0" }}>
          <input type="checkbox" checked={needsVolunteers} onChange={(event) => setNeedsVolunteers(event.target.checked)} />
          <span><strong>Нужны волонтёры</strong><span style={{ display: "block", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>Отметьте, если для проведения понадобится команда помощников.</span></span>
        </label>
        <Field label="Дополнительно" hint="Что взять с собой, дресс-код, язык, особенности входа — только если это действительно нужно.">
          <textarea value={additionalInfo} onChange={(event) => setAdditionalInfo(event.target.value)} rows={3} />
        </Field>
      </Card>

      {error && <p style={{ margin: 0, color: "var(--era-error)" }}>{error}</p>}
      {success && <Card style={{ borderColor: "rgba(67,211,154,0.35)" }}><strong style={{ color: "var(--era-success)" }}>Готово</strong><p style={{ margin: "0.25rem 0 0" }}>{success}</p></Card>}

      <div style={{ display: "grid", gridTemplateColumns: "0.9fr 1.1fr", gap: "0.5rem" }}>
        <button type="button" disabled={busy || !valid} onClick={() => void submit(false)}>Сохранить черновик</button>
        <button type="button" className="era-btn-primary" disabled={busy || !valid} onClick={() => void submit(true)}>
          {busy ? "Сохраняю…" : "Создать и открыть регистрацию"}
        </button>
      </div>
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: "0.35rem", marginBottom: "0.75rem" }}>
      <strong>{label}</strong>
      {hint && <span style={{ color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)", lineHeight: 1.4 }}>{hint}</span>}
      {children}
    </label>
  );
}
