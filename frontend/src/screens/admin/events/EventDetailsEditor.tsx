import { useState } from "react";
import type { FormEvent } from "react";
import { fetchEventDraft, saveEventDraft, type AdminEventDraftPatch } from "../../../api/adminEvents";
import { describeActionError } from "../../../api/client";
import { useAsync } from "../../../hooks/useAsync";

export function EventDetailsEditor({ eventId, onClose }: { eventId: number; onClose: () => void }) {
  const [revision, setRevision] = useState(0);
  const state = useAsync(() => fetchEventDraft(eventId), [eventId, revision]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (state.status === "loading") return <p>Открываем карточку…</p>;
  if (state.status === "error") return <p>Карточка недоступна. <button onClick={() => setRevision(revision + 1)}>Повторить</button> <button onClick={onClose}>Назад</button></p>;
  const event = state.data;
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    const data = new FormData(e.currentTarget);
    const value = (key: string) => String(data.get(key) ?? "").trim();
    const patch: AdminEventDraftPatch = {};
    for (const key of ["title", "full_description", "location", "event_date", "event_time", "chat_url"] as const) {
      const old = key === "event_time" ? event.event_time.slice(0, 5) : event[key] ?? "";
      if (value(key) !== old) patch[key] = value(key);
    }
    if (!value("title") || !value("location")) { setError("Заполните название и место."); return; }
    if (Number(value("points")) !== event.points_for_visit) patch.points_for_visit = Number(value("points"));
    if (!Object.keys(patch).length) { onClose(); return; }
    setBusy(true);
    try { await saveEventDraft(eventId, patch); onClose(); }
    catch (reason) { setError(describeActionError(reason)); }
    finally { setBusy(false); }
  }
  return <form onSubmit={submit}><fieldset disabled={busy} style={{ display: "grid", gap: 12, padding: 16 }}>
    <legend>Редактировать мероприятие</legend>
    <label>Название<input required maxLength={255} name="title" defaultValue={event.title}/></label>
    <label>Описание<textarea rows={5} maxLength={10000} name="full_description" defaultValue={event.full_description}/></label>
    <label>Дата<input required type="date" name="event_date" defaultValue={event.event_date}/></label>
    <label>Начало по Еревану<input required type="time" name="event_time" defaultValue={event.event_time.slice(0,5)}/></label>
    <label>Место<input required maxLength={255} name="location" defaultValue={event.location}/></label>
    <label>Ссылка на чат<input type="url" maxLength={500} name="chat_url" defaultValue={event.chat_url ?? ""}/></label>
    <label>Баллы за посещение<input required type="number" min={0} max={200} name="points" defaultValue={event.points_for_visit}/></label>
    <small>При изменении даты, времени или места бот отправит обновление в «Мероприятия», записанным и в лист ожидания.</small>
    {error && <p role="alert">{error}</p>}
    <button type="submit">{busy ? "Сохраняем…" : "Сохранить изменения"}</button>
    <button type="button" onClick={onClose}>Закрыть</button>
  </fieldset></form>;
}
