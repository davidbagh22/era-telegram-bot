import { useState } from "react";
import type { FormEvent } from "react";
import { changeEventTopic, fetchEventDraft, saveEventDraft, type AdminEventDraftPatch } from "../../../api/adminEvents";
import { describeActionError } from "../../../api/client";
import { useAsync } from "../../../hooks/useAsync";

function yerevanInputTime(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 16);
  return new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Asia/Yerevan", year: "numeric", month: "2-digit",
    day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).format(date).replace(" ", "T");
}

export function EventDetailsEditor({ eventId, onClose }: { eventId: number; onClose: () => void }) {
  const [revision, setRevision] = useState(0);
  const state = useAsync(() => fetchEventDraft(eventId), [eventId, revision]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [confirmTopicAction, setConfirmTopicAction] = useState<"close" | "reopen" | null>(null);
  if (state.status === "loading") return <p>Открываем карточку…</p>;
  if (state.status === "error") return <p>Карточка недоступна. <button onClick={() => setRevision(revision + 1)}>Повторить</button> <button onClick={onClose}>Назад</button></p>;
  const event = state.data;
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    const data = new FormData(e.currentTarget);
    const value = (key: string) => String(data.get(key) ?? "").trim();
    const patch: AdminEventDraftPatch = {};
    for (const key of ["title", "full_description", "location", "event_date", "event_time", "chat_url", "registration_url"] as const) {
      const old = key === "event_time" ? event.event_time.slice(0, 5) : event[key] ?? "";
      if (value(key) !== old) patch[key] = value(key);
    }
    if (!value("title") || !value("location")) { setError("Заполните название и место."); return; }
    if (Number(value("points")) !== event.points_for_visit) patch.points_for_visit = Number(value("points"));
    // Preserve custom reminders configured in the detailed wizard.
    const presets = new Set([1440, 180, 60]);
    const custom = event.reminders.filter(value => !presets.has(value));
    const reminders = [...custom, ...data.getAll("reminder").map(value => Number(value))]
      .filter(value => Number.isInteger(value) && value >= 5).sort((a, b) => a - b);
    if (reminders.join(",") !== [...event.reminders].sort((a, b) => a - b).join(",")) patch.reminders = reminders;
    const nativeRegistration = data.has("native_registration") && !value("registration_url");
    if (nativeRegistration !== event.registration_required) patch.registration_required = nativeRegistration;
    const topicCloseTime = value("topic_close_at");
    if (topicCloseTime !== yerevanInputTime(event.topic_close_at)) {
      // The API interprets an unzoned datetime as Asia/Yerevan.
      patch.topic_close_at = topicCloseTime || null;
    }
    const certificate = data.has("certificate");
    if (certificate !== Boolean(event.issue_certificate)) patch.issue_certificate = certificate;
    if (!Object.keys(patch).length) { onClose(); return; }
    setBusy(true);
    try { await saveEventDraft(eventId, patch); onClose(); }
    catch (reason) { setError(describeActionError(reason)); }
    finally { setBusy(false); }
  }
  async function actOnTopic(action: "close" | "reopen") {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await changeEventTopic(eventId, action);
      setConfirmTopicAction(null);
      setRevision((value) => value + 1);
    } catch (reason) { setError(describeActionError(reason)); }
    finally { setBusy(false); }
  }
  return <form onSubmit={submit}><fieldset disabled={busy} style={{ display: "grid", gap: 12, padding: 16 }}>
    <legend>Редактировать мероприятие</legend>
    <label>Название<input required maxLength={255} name="title" defaultValue={event.title}/></label>
    <label>Описание<textarea rows={5} maxLength={10000} name="full_description" defaultValue={event.full_description}/></label>
    <label>Дата<input required type="date" name="event_date" defaultValue={event.event_date}/></label>
    <label>Начало по Еревану<input required type="time" name="event_time" defaultValue={event.event_time.slice(0,5)}/></label>
    <label>Место<input required maxLength={255} name="location" defaultValue={event.location}/></label>
    <label>Ссылка на тему обсуждения<input type="url" maxLength={500} name="chat_url" defaultValue={event.chat_url ?? ""}/></label>
    <label>Внешняя регистрация (необязательно)<input type="url" maxLength={500} name="registration_url" defaultValue={event.registration_url ?? ""} placeholder="https://t.me/..." /></label>
    <label><input type="checkbox" name="native_registration" defaultChecked={event.registration_required} /> Регистрация через Mini App ЭРА (если нет внешней ссылки)</label>
    <details><summary>Напоминания зарегистрированным</summary>
      {[[1440, "За 24 часа"], [180, "За 3 часа"], [60, "За 1 час"]].map(([mins, label]) =>
        <label key={mins}><input type="checkbox" name="reminder" value={mins} defaultChecked={event.reminders.includes(Number(mins))} /> {label}</label>)}
      <small>Напоминания ЭРА работают только для регистраций, оформленных внутри Mini App.</small>
    </details>
    <section style={{ padding: ".9rem", border: "1px solid var(--era-border)", borderRadius: "1rem", background: "var(--era-surface-2)", display: "grid", gap: ".65rem" }}>
      <strong>💬 Тема мероприятия в Telegram</strong>
      <span style={{ fontSize: ".82rem", color: "var(--era-text-secondary)" }}>
        {event.topic_close_state === "closed" ? "Тема закрыта: сообщения сохранены." :
          event.topic_close_state === "attention" ? "Тема требует проверки организатора." : "Тема открыта."}
      </span>
      <label>Автоматически закрыть (Ереван)
        <input type="datetime-local" name="topic_close_at" defaultValue={yerevanInputTime(event.topic_close_at)}
          disabled={event.topic_close_state === "closed"} style={{ width: "100%", boxSizing: "border-box" }} />
      </label>
      <small>Необязательно. Можно изменить или очистить дату. Закрывается только тема этого проекта, не весь чат. Это не срок окончания регистрации.</small>
      {event.topic_close_state === "closed" ? (
        <button type="button" onClick={() => setConfirmTopicAction("reopen")}>↪ Переоткрыть тему</button>
      ) : (
        <button type="button" onClick={() => setConfirmTopicAction("close")}>Закрыть тему сейчас</button>
      )}
      {confirmTopicAction && <div role="group" aria-label="Подтвердить действие с темой" style={{ display: "grid", gap: ".45rem" }}>
        <small>{confirmTopicAction === "close" ? "Закрыть обсуждение? История сохранится." : "Снова разрешить сообщения? Дата автоматического закрытия будет очищена."}</small>
        <button type="button" className="era-btn-primary" onClick={() => void actOnTopic(confirmTopicAction)}>Подтвердить</button>
        <button type="button" onClick={() => setConfirmTopicAction(null)}>Отмена</button>
      </div>}
    </section>
    <label>Баллы за посещение<input required type="number" min={0} max={200} name="points" defaultValue={event.points_for_visit}/></label>
    <label><input type="checkbox" name="certificate" defaultChecked={Boolean(event.issue_certificate)} /> Сертификат после посещения</label>
    <small>При изменении даты, времени или места бот отправит обновление в «Мероприятия», записанным и в лист ожидания.</small>
    {error && <p role="alert">{error}</p>}
    <button type="submit">{busy ? "Сохраняем…" : "Сохранить изменения"}</button>
    <button type="button" onClick={onClose}>Закрыть</button>
  </fieldset></form>;
}
