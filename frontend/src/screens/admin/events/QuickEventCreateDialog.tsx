import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { AdminEventDraft } from "../../../api/adminEvents";

interface Props {
  draft: AdminEventDraft;
  posterUrl: string | null;
  busy: boolean;
  saving: boolean;
  saveLabel: string;
  error: string | null;
  onChange: (recipe: (current: AdminEventDraft) => AdminEventDraft) => void;
  onClose: () => Promise<void>;
  onPublish: () => Promise<void>;
  onPoster: (file: File | null) => Promise<void>;
  onWizard: () => void;
}

const firstLine = (text: string) => text.split("\n").find((line) => line.trim())?.trim().slice(0, 255) ?? "";

export function QuickEventCreateDialog({ draft, posterUrl, busy, saving, saveLabel, error, onChange, onClose, onPublish, onPoster, onWizard }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [preview, setPreview] = useState(false);
  const [photoError, setPhotoError] = useState<string | null>(null);
  const complete = draft.is_complete && draft.status !== "draft";
  const valid = Boolean(draft.full_description.trim() && draft.title.trim() && draft.title !== "Новое мероприятие"
    && draft.event_date && draft.event_time && draft.location.trim());

  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);

  const poster = async (file: File | null) => {
    if (file && (!new Set(["image/jpeg", "image/png", "image/webp"]).has(file.type) || file.size > 5 * 1024 * 1024)) {
      setPhotoError("Выберите JPG, PNG или WEBP размером до 5 МБ.");
      return;
    }
    setPhotoError(null);
    await onPoster(file);
  };

  const updateText = (text: string) => onChange((current) => {
    const title = !current.title || current.title === "Новое мероприятие" || current.title === firstLine(current.full_description)
      ? firstLine(text) : current.title;
    const lines = text.trim().split("\n");
    const body = lines[0]?.trim() === title ? lines.slice(1).join("\n").trim() : text.trim();
    return { ...current, title, full_description: text, short_description: (body || text.trim()).slice(0, 1000) };
  });

  return (
    <dialog ref={dialog} className="era-event-dialog" aria-labelledby="quick-event-title" onCancel={(event) => { event.preventDefault(); if (!busy && !saving) void onClose(); }}
      style={{ width: "min(34rem, calc(100vw - 2rem))", maxHeight: "90dvh", overflowY: "auto", boxSizing: "border-box", border: "1px solid var(--era-border)", borderRadius: "1.25rem", padding: "1rem", color: "var(--era-text)", background: "var(--era-surface)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: ".5rem" }}>
        <h2 id="quick-event-title" style={{ margin: 0 }}>{complete ? "Мероприятие опубликовано" : preview ? "Проверьте анонс" : "Быстрое создание"}</h2>
        <button type="button" aria-label="Сохранить и закрыть" disabled={busy || saving} onClick={() => void onClose()}>✕</button>
      </div>
      {complete ? (
        <>
          <h3>{draft.title}</h3>
          <p>{draft.announcement_status === "sent" ? `Анонс${draft.has_poster ? " с афишей" : ""} отправлен в тему «Мероприятия».` : draft.announcement_status === "needs_attention"
            ? "Событие сохранено. Отправка анонса не подтверждена — проверьте тему «Мероприятия» перед повторной отправкой."
            : "Событие опубликовано. Анонс ожидает отправки; создавать мероприятие повторно не нужно."}</p>
          <button type="button" className="era-btn-primary" onClick={() => void onClose()}>Готово</button>
        </>
      ) : (
        <form onSubmit={(event) => { event.preventDefault(); if (valid) setPreview(true); }}>
          <fieldset disabled={busy} style={{ border: 0, padding: 0, margin: "1rem 0", minWidth: 0 }}>
            {preview ? (
              <>
                {draft.has_poster && posterUrl && <img alt="Афиша мероприятия" src={posterUrl} style={{ width: "100%", maxHeight: 300, objectFit: "contain", borderRadius: ".8rem" }} />}
                {draft.full_description.split("\n")[0].trim() !== draft.title.trim() && <h3>{draft.title}</h3>}
                <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{draft.full_description}</p>
                <p>📅 {draft.event_date.split("-").reverse().join(".")} · {draft.event_time.slice(0, 5)}<br />📍 {draft.location}</p>
                <p style={{ color: "var(--era-text-muted)" }}>{draft.registration_required ? "Регистрация открывается после публикации." : "Без регистрации."} Анонс отправится в тему «Мероприятия».</p>
              </>
            ) : (
              <>
                <p style={{ marginTop: 0, color: "var(--era-text-muted)" }}>Вставьте готовый текст и добавьте фото. Черновик сохраняется автоматически.</p>
                <Field label="Текст анонса"><textarea required value={draft.full_description} onChange={(event) => updateText(event.target.value)} rows={8} maxLength={10000} placeholder="Вставьте текст мероприятия целиком…" /></Field>
                <Field label="Заголовок"><input required value={draft.title === "Новое мероприятие" ? "" : draft.title} onChange={(event) => onChange((current) => ({ ...current, title: event.target.value }))} maxLength={255} placeholder="Первая строка текста или свой заголовок" /></Field>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 10rem), 1fr))", gap: ".5rem" }}>
                  <Field label="Дата"><input required type="date" style={{ width: "100%", minWidth: 0, boxSizing: "border-box" }} value={draft.event_date} onChange={(event) => onChange((current) => ({ ...current, event_date: event.target.value }))} /></Field>
                  <Field label="Время"><input required type="time" style={{ width: "100%", minWidth: 0, boxSizing: "border-box" }} value={draft.event_time} onChange={(event) => onChange((current) => ({ ...current, event_time: event.target.value }))} /></Field>
                </div>
                <Field label="Место или ссылка"><input required value={draft.location} maxLength={255} onChange={(event) => onChange((current) => ({ ...current, location: event.target.value }))} placeholder="Адрес или ссылка на онлайн-встречу" /></Field>
                <Field label="Фото (до 5 МБ)"><input type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => { const file = event.target.files?.[0]; if (file) void poster(file); event.target.value = ""; }} /></Field>
                {draft.has_poster && <div style={{ marginBottom: ".8rem" }}>{posterUrl && <img alt="Прикреплённая афиша" src={posterUrl} style={{ width: "100%", maxHeight: 200, objectFit: "contain", borderRadius: ".8rem" }} /> }<button type="button" onClick={() => void poster(null)}>Удалить фото</button></div>}
                <details><summary>Регистрация и баллы</summary>
                  <Field label="Формат"><select value={draft.attendance_mode} onChange={(event) => onChange((current) => ({ ...current, attendance_mode: event.target.value as AdminEventDraft["attendance_mode"] }))}><option value="offline">Офлайн</option><option value="online">Онлайн</option><option value="hybrid">Гибрид</option></select></Field>
                  <label><input type="checkbox" checked={draft.registration_required} onChange={(event) => onChange((current) => ({ ...current, registration_required: event.target.checked }))} /> Нужна регистрация</label>
                  {draft.registration_required && <Field label="Количество мест"><input type="number" min={1} max={5000} value={draft.participant_limit ?? ""} onChange={(event) => onChange((current) => ({ ...current, participant_limit: event.target.value ? Number(event.target.value) : null }))} placeholder="Без ограничения" /></Field>}
                  <Field label="Баллы за посещение"><input type="number" min={0} max={200} value={draft.points_for_visit} onChange={(event) => onChange((current) => ({ ...current, points_for_visit: Number(event.target.value) }))} /></Field>
                </details>
              </>
            )}
          </fieldset>
          <p aria-live="polite" style={{ fontSize: ".8rem", color: "var(--era-text-muted)" }}>{saving ? "Сохраняем…" : saveLabel}</p>
          {(photoError || error) && <p role="alert" style={{ color: "var(--era-error)" }}>{photoError || error}</p>}
          <div style={{ display: "flex", gap: ".5rem" }}>
            {preview && <button type="button" disabled={busy} onClick={() => setPreview(false)}>Изменить</button>}
            {preview ? <button type="button" className="era-btn-primary" disabled={busy || saving || !valid} onClick={() => void onPublish()}>{busy ? "Публикуем…" : "Опубликовать"}</button>
              : <button type="submit" className="era-btn-primary" disabled={busy || !valid || Boolean(photoError)}>Проверить публикацию</button>}
          </div>
          <button type="button" disabled={busy || saving} onClick={onWizard} style={{ marginTop: ".7rem" }}>Открыть подробный конструктор</button>
        </form>
      )}
    </dialog>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label style={{ display: "flex", flexDirection: "column", gap: ".3rem", marginBottom: ".8rem", minWidth: 0 }}><strong>{label}</strong>{children}</label>;
}
