import { useEffect, useMemo, useRef, useState } from "react";
import {
  createEventDraft,
  listEventDrafts,
  publishEventDraft,
  removeEventPoster,
  saveEventDraft,
  uploadEventPoster,
  type AdminEventDraft,
  type AdminEventDraftPatch,
} from "../../../api/adminEvents";
import { BottomSheet } from "../../../components/BottomSheet";
import { Card } from "../../../components/Card";
import { EmptyState } from "../../../components/EmptyState";
import { PrimaryButton, SecondaryButton } from "../../../components/Buttons";
import { SkeletonCard } from "../../../components/Skeleton";
import { CheckIcon } from "../../../components/icons";

const STEP_COUNT = 10;
const AUTOSAVE_DELAY = 700;

type ProgramItem = { time?: string; title: string; description?: string; responsible?: string };
type TaskItem = { title: string; description?: string; points?: number };

function humanError(error: unknown): string {
  const detail = error instanceof Error ? error.message : "";
  if (detail.includes("poster_must_be_image")) return "Выберите изображение JPG, PNG или WebP.";
  if (detail.includes("poster_too_large")) return "Файл слишком большой. Максимум — 5 МБ.";
  if (detail.includes("missing:")) return "Не хватает обязательных данных. Проверьте название, описание и место.";
  return "Не получилось сохранить. Данные на экране не потеряны — попробуйте ещё раз.";
}

function patchFromDraft(draft: AdminEventDraft, wizardStep = draft.wizard_step): AdminEventDraftPatch {
  return {
    wizard_step: Math.max(1, Math.min(STEP_COUNT, wizardStep)),
    title: draft.title,
    short_description: draft.short_description,
    full_description: draft.full_description,
    project_id: draft.project_id,
    category: draft.category,
    event_date: draft.event_date,
    event_time: draft.event_time,
    end_time: draft.end_time,
    location: draft.location,
    address: draft.address,
    attendance_mode: draft.attendance_mode,
    registration_required: draft.registration_required,
    participant_limit: draft.participant_limit,
    registration_close_at: draft.registration_close_at,
    waitlist_enabled: draft.waitlist_enabled,
    registration_audience: draft.registration_audience,
    chat_url: draft.chat_url,
    organizer: draft.organizer,
    participant_value: draft.participant_value,
    contact: draft.contact,
    program: draft.program,
    participant_tasks: draft.participant_tasks,
    points_for_visit: draft.points_for_visit,
    reminders: draft.reminders,
    broadcast_enabled: draft.broadcast_enabled,
    broadcast_targets: draft.broadcast_targets,
  };
}

function parseProgram(value: string): ProgramItem[] {
  return value.split("\n").map((line) => line.trim()).filter(Boolean).map((line) => {
    const [time, title, description, responsible] = line.split("|").map((part) => part.trim());
    return { time: time || undefined, title: title || time || "Активность", description: description || undefined, responsible: responsible || undefined };
  });
}

function programText(items: unknown[]): string {
  return items.map((raw) => {
    const item = raw as Record<string, unknown>;
    return [item.time, item.title, item.description, item.responsible].map((value) => String(value ?? "").trim()).join(" | ").replace(/( \| )+$/g, "");
  }).join("\n");
}

function parseTasks(value: string): TaskItem[] {
  return value.split("\n").map((line) => line.trim()).filter(Boolean).map((line) => {
    const [title, description, pointsRaw] = line.split("|").map((part) => part.trim());
    const points = Number(pointsRaw);
    return { title: title || "Задание", description: description || undefined, points: Number.isFinite(points) && points >= 0 ? points : undefined };
  });
}

function tasksText(items: unknown[]): string {
  return items.map((raw) => {
    const item = raw as Record<string, unknown>;
    return [item.title, item.description, item.points].map((value) => String(value ?? "").trim()).join(" | ").replace(/( \| )+$/g, "");
  }).join("\n");
}

function StepHeader({ step, title, savedState }: { step: number; title: string; savedState: "idle" | "saving" | "saved" | "error" }) {
  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem" }}>
        <p className="era-kicker">Шаг {step} / {STEP_COUNT}</p>
        <span style={{ color: savedState === "error" ? "var(--era-error)" : "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>
          {savedState === "saving" ? "Сохраняем…" : savedState === "saved" ? "✓ Сохранено" : savedState === "error" ? "Не удалось сохранить" : "Автосохранение включено"}
        </span>
      </div>
      <div style={{ marginTop: 7, height: 6, borderRadius: 999, background: "var(--era-ring-track)", overflow: "hidden" }}>
        <div style={{ width: `${(step / STEP_COUNT) * 100}%`, height: "100%", borderRadius: 999, background: "var(--era-gradient)", transition: "width var(--era-motion)" }} />
      </div>
      <h2 style={{ margin: "0.7rem 0 0", fontSize: "var(--era-text-2xl)", letterSpacing: "-0.03em" }}>{title}</h2>
    </div>
  );
}

export function AdminEventCreatePanel() {
  const [drafts, setDrafts] = useState<AdminEventDraft[]>([]);
  const [draft, setDraft] = useState<AdminEventDraft | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedState, setSavedState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [confirmPublish, setConfirmPublish] = useState(false);
  const [programInput, setProgramInput] = useState("");
  const [tasksInput, setTasksInput] = useState("");
  const [customReminder, setCustomReminder] = useState("");
  const [localPosterUrl, setLocalPosterUrl] = useState<string | null>(null);
  const lastSaved = useRef<string>("");
  const sequence = useRef(0);

  const reloadDrafts = async () => {
    setLoading(true);
    setError(null);
    try { setDrafts(await listEventDrafts()); }
    catch (cause) { setError(humanError(cause)); }
    finally { setLoading(false); }
  };

  useEffect(() => { void reloadDrafts(); }, []);
  useEffect(() => () => { if (localPosterUrl) URL.revokeObjectURL(localPosterUrl); }, [localPosterUrl]);

  const openDraft = (item: AdminEventDraft) => {
    setDraft(item);
    setProgramInput(programText(item.program));
    setTasksInput(tasksText(item.participant_tasks));
    lastSaved.current = JSON.stringify(patchFromDraft(item));
    setSavedState("idle");
    setError(null);
  };

  const begin = async () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try { openDraft(await createEventDraft()); }
    catch (cause) { setError(humanError(cause)); }
    finally { setBusy(false); }
  };

  const update = (patch: Partial<AdminEventDraft>) => {
    setDraft((current) => current ? { ...current, ...patch } : current);
    setError(null);
  };

  useEffect(() => {
    if (!draft || busy) return;
    const payload = patchFromDraft(draft);
    const serialized = JSON.stringify(payload);
    if (serialized === lastSaved.current) return;
    const currentSequence = ++sequence.current;
    setSavedState("saving");
    const timer = window.setTimeout(() => {
      saveEventDraft(draft.id, payload)
        .then((saved) => {
          if (currentSequence !== sequence.current) return;
          lastSaved.current = JSON.stringify(patchFromDraft(saved));
          setDraft(saved);
          setSavedState("saved");
          window.setTimeout(() => { if (currentSequence === sequence.current) setSavedState("idle"); }, 1300);
        })
        .catch((cause) => {
          if (currentSequence !== sequence.current) return;
          setSavedState("error");
          setError(humanError(cause));
        });
    }, AUTOSAVE_DELAY);
    return () => window.clearTimeout(timer);
  }, [busy, draft]);

  const saveNow = async (nextStep?: number) => {
    if (!draft || busy) return false;
    ++sequence.current;
    setBusy(true);
    setSavedState("saving");
    setError(null);
    try {
      const saved = await saveEventDraft(draft.id, patchFromDraft(draft, nextStep ?? draft.wizard_step));
      lastSaved.current = JSON.stringify(patchFromDraft(saved));
      setDraft(saved);
      setSavedState("saved");
      return true;
    } catch (cause) {
      setSavedState("error");
      setError(humanError(cause));
      return false;
    } finally { setBusy(false); }
  };

  const next = async () => {
    if (!draft) return;
    const nextStep = Math.min(STEP_COUNT, draft.wizard_step + 1);
    await saveNow(nextStep);
  };
  const back = () => update({ wizard_step: Math.max(1, (draft?.wizard_step ?? 1) - 1) });

  const uploadPoster = async (file: File | null) => {
    if (!draft || !file || busy) return;
    if (!file.type.startsWith("image/")) { setError("Выберите изображение JPG, PNG или WebP."); return; }
    if (file.size > 5 * 1024 * 1024) { setError("Файл слишком большой. Максимум — 5 МБ."); return; }
    setBusy(true);
    setError(null);
    try {
      const saved = await uploadEventPoster(draft.id, file);
      if (localPosterUrl) URL.revokeObjectURL(localPosterUrl);
      setLocalPosterUrl(URL.createObjectURL(file));
      setDraft(saved);
      lastSaved.current = JSON.stringify(patchFromDraft(saved));
      setSavedState("saved");
    } catch (cause) { setError(humanError(cause)); }
    finally { setBusy(false); }
  };

  const deletePoster = async () => {
    if (!draft || busy) return;
    setBusy(true);
    try {
      const saved = await removeEventPoster(draft.id);
      setDraft(saved);
      if (localPosterUrl) URL.revokeObjectURL(localPosterUrl);
      setLocalPosterUrl(null);
      lastSaved.current = JSON.stringify(patchFromDraft(saved));
    } catch (cause) { setError(humanError(cause)); }
    finally { setBusy(false); }
  };

  const toggleReminder = (minutes: number) => {
    if (!draft) return;
    const current = new Set(draft.reminders);
    if (current.has(minutes)) current.delete(minutes); else current.add(minutes);
    update({ reminders: [...current].sort((a, b) => b - a) });
  };

  const addCustomReminder = () => {
    const minutes = Number(customReminder);
    if (!draft || !Number.isFinite(minutes) || minutes < 5) { setError("Укажите минимум 5 минут до начала."); return; }
    update({ reminders: Array.from(new Set([...draft.reminders, Math.round(minutes)])).sort((a, b) => b - a) });
    setCustomReminder("");
  };

  const publish = async () => {
    if (!draft || busy) return;
    const saved = await saveNow(STEP_COUNT);
    if (!saved) return;
    setBusy(true);
    setError(null);
    try {
      const published = await publishEventDraft(draft.id);
      setConfirmPublish(false);
      setDraft(null);
      setDrafts((items) => items.filter((item) => item.id !== published.id));
    } catch (cause) { setError(humanError(cause)); }
    finally { setBusy(false); }
  };

  if (loading) return <><SkeletonCard /><SkeletonCard /></>;

  if (!draft) {
    return (
      <div style={{ display: "grid", gap: "0.75rem" }}>
        <Card style={{ borderColor: "rgba(227,38,54,.14)" }}>
          <p className="era-kicker">Конструктор события</p>
          <h3 style={{ margin: "0.35rem 0 0", fontSize: "var(--era-text-xl)" }}>10 шагов · всё сохраняется автоматически</h3>
          <p style={{ margin: "0.4rem 0 0", color: "var(--era-text-muted)" }}>Публикация и рассылка никогда не происходят от случайного переключателя — финальное подтверждение обязательно.</p>
          <PrimaryButton busy={busy} onClick={() => void begin()} style={{ width: "100%", marginTop: "0.8rem" }}>Создать новое событие</PrimaryButton>
        </Card>
        {error && <EmptyState title="Не получилось загрузить черновики" description={error} actionLabel="Повторить" onAction={() => void reloadDrafts()} />}
        {drafts.length > 0 && <section className="era-section"><h3 style={{ margin: 0 }}>Продолжить создание</h3>{drafts.map((item) => <Card key={item.id} interactive onClick={() => openDraft(item)} ariaLabel={`${item.title}. Продолжить создание`} style={{ boxShadow: "none" }}><strong>{item.title}</strong><p style={{ margin: "0.3rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>Шаг {item.wizard_step} из {STEP_COUNT} · {item.event_date} · {item.event_time}</p></Card>)}</section>}
      </div>
    );
  }

  const step = draft.wizard_step;
  const stepTitle = ["Основа", "Дата и место", "Афиша", "Регистрация", "Что получит участник", "Программа", "Задания и баллы", "Напоминания", "Рассылка", "Проверка и публикация"][step - 1];

  return (
    <div style={{ display: "grid", gap: "0.85rem" }}>
      <StepHeader step={step} title={stepTitle} savedState={savedState} />
      {error && <Card style={{ borderColor: "rgba(101,90,115,.2)", background: "rgba(101,90,115,.05)", boxShadow: "none" }}><strong>Не получилось сохранить</strong><p style={{ margin: "0.3rem 0 0", color: "var(--era-text-muted)" }}>{error}</p><SecondaryButton onClick={() => void saveNow()} style={{ marginTop: "0.6rem" }}>Повторить</SecondaryButton></Card>}

      {step === 1 && <Card><Field label="Название"><input value={draft.title} onChange={(event) => update({ title: event.target.value })} placeholder="Название события" /></Field><Field label="Коротко — зачем идти"><textarea rows={3} value={draft.short_description} onChange={(event) => update({ short_description: event.target.value })} placeholder="1–2 предложения для карточки" /></Field><Field label="Полное описание"><textarea rows={7} value={draft.full_description} onChange={(event) => update({ full_description: event.target.value })} placeholder="Что будет, для кого, почему это важно" /></Field><Field label="Направление / тема"><input value={draft.category ?? ""} onChange={(event) => update({ category: event.target.value || null })} placeholder="Например: Медиа" /></Field></Card>}

      {step === 2 && <Card><div className="era-grid-2"><Field label="Дата"><input type="date" value={draft.event_date} onChange={(event) => update({ event_date: event.target.value })} /></Field><Field label="Начало"><input type="time" value={draft.event_time} onChange={(event) => update({ event_time: event.target.value })} /></Field></div><Field label="Окончание"><input type="time" value={draft.end_time ?? ""} onChange={(event) => update({ end_time: event.target.value || null })} /></Field><Field label="Формат"><select value={draft.attendance_mode} onChange={(event) => update({ attendance_mode: event.target.value as AdminEventDraft["attendance_mode"] })}><option value="offline">Офлайн</option><option value="online">Онлайн</option><option value="hybrid">Гибрид</option></select></Field><Field label="Площадка / название места"><input value={draft.location} onChange={(event) => update({ location: event.target.value })} placeholder="Дом Москвы в Ереване" /></Field><Field label="Адрес"><input value={draft.address ?? ""} onChange={(event) => update({ address: event.target.value || null })} placeholder="Полный адрес для навигации" /></Field></Card>}

      {step === 3 && <Card><p style={{ margin: 0, color: "var(--era-text-muted)" }}>JPG, PNG или WebP · до 5 МБ. После загрузки сразу показываем preview.</p>{localPosterUrl && <img src={localPosterUrl} alt="Предпросмотр афиши" style={{ width: "100%", maxHeight: 360, objectFit: "cover", borderRadius: 16, marginTop: "0.75rem" }} />}{draft.has_poster && !localPosterUrl && <div style={{ marginTop: "0.75rem", padding: "1rem", borderRadius: 16, background: "var(--era-tint-success)" }}><strong>✓ Афиша уже сохранена</strong><p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)" }}>Можно заменить её новым файлом или удалить.</p></div>}<label className="era-btn-primary" style={{ marginTop: "0.75rem", cursor: "pointer" }}>{busy ? "Загружаем…" : draft.has_poster ? "Заменить афишу" : "Загрузить афишу"}<input type="file" accept="image/*" disabled={busy} onChange={(event) => void uploadPoster(event.target.files?.[0] ?? null)} style={{ display: "none" }} /></label>{draft.has_poster && <button type="button" className="era-btn-danger" disabled={busy} onClick={() => void deletePoster()} style={{ width: "100%", marginTop: "0.55rem" }}>Удалить афишу</button>}</Card>}

      {step === 4 && <Card><Toggle label="Нужна регистрация" checked={draft.registration_required} onChange={(value) => update({ registration_required: value })} />{draft.registration_required && <><Field label="Лимит участников"><input type="number" min={1} max={5000} value={draft.participant_limit ?? ""} onChange={(event) => update({ participant_limit: event.target.value ? Number(event.target.value) : null })} placeholder="Без лимита" /></Field><Field label="Закрыть регистрацию"><input type="datetime-local" value={(draft.registration_close_at ?? "").slice(0, 16)} onChange={(event) => update({ registration_close_at: event.target.value || null })} /></Field><Toggle label="Лист ожидания" checked={draft.waitlist_enabled} onChange={(value) => update({ waitlist_enabled: value })} /><Field label="Кто может зарегистрироваться"><select value={draft.registration_audience} onChange={(event) => update({ registration_audience: event.target.value })}><option value="all">Все участники</option><option value="participants">Участники ЭРА</option><option value="leaders">Лидеры</option></select></Field></>}</Card>}

      {step === 5 && <Card><Field label="Организатор"><input value={draft.organizer ?? ""} onChange={(event) => update({ organizer: event.target.value || null })} placeholder="ЭРА / партнёр" /></Field><Field label="Что получит участник"><textarea rows={5} value={draft.participant_value ?? ""} onChange={(event) => update({ participant_value: event.target.value || null })} placeholder="Опыт, сертификат, кофе-брейк, команда, новые навыки…" /></Field><Field label="Ссылка на чат"><input value={draft.chat_url ?? ""} onChange={(event) => update({ chat_url: event.target.value || null })} placeholder="https://t.me/..." /></Field><Field label="Контакт ответственного"><input value={draft.contact ?? ""} onChange={(event) => update({ contact: event.target.value || null })} placeholder="@username или контакт" /></Field></Card>}

      {step === 6 && <Card><p style={{ margin: "0 0 0.6rem", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>Одна строка = один пункт. Формат: <strong>время | название | описание | ответственный</strong></p><textarea rows={9} value={programInput} onChange={(event) => { const value = event.target.value; setProgramInput(value); update({ program: parseProgram(value) }); }} placeholder="10:00 | Открытие | Знакомство и вводная | Давид" /></Card>}

      {step === 7 && <Card><Field label="Баллы за посещение"><input type="number" min={0} max={200} value={draft.points_for_visit} onChange={(event) => update({ points_for_visit: Math.max(0, Number(event.target.value) || 0) })} /></Field><p style={{ margin: "0.8rem 0 0.5rem", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>Дополнительные задания: <strong>название | описание | баллы</strong></p><textarea rows={8} value={tasksInput} onChange={(event) => { const value = event.target.value; setTasksInput(value); update({ participant_tasks: parseTasks(value) }); }} placeholder="Снять рилс | Опубликовать короткое видео после события | 10" /></Card>}

      {step === 8 && <Card><p style={{ margin: "0 0 0.75rem", color: "var(--era-text-muted)" }}>Участник после регистрации увидит, что бот напомнит ему заранее.</p><Reminder label="За день" minutes={1440} checked={draft.reminders.includes(1440)} onChange={() => toggleReminder(1440)} /><Reminder label="За 3 часа" minutes={180} checked={draft.reminders.includes(180)} onChange={() => toggleReminder(180)} /><Reminder label="За 1 час" minutes={60} checked={draft.reminders.includes(60)} onChange={() => toggleReminder(60)} /><div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: "0.5rem", marginTop: "0.75rem" }}><input type="number" min={5} value={customReminder} onChange={(event) => setCustomReminder(event.target.value)} placeholder="Свой вариант, минут" /><SecondaryButton onClick={addCustomReminder}>Добавить</SecondaryButton></div>{draft.reminders.filter((item) => ![1440, 180, 60].includes(item)).map((minutes) => <button key={minutes} type="button" className="era-btn-ghost" onClick={() => toggleReminder(minutes)} style={{ marginTop: "0.35rem" }}>{minutes} мин. до начала · убрать</button>)}</Card>}

      {step === 9 && <Card><Toggle label="Сделать рассылку после публикации" checked={draft.broadcast_enabled} onChange={(value) => update({ broadcast_enabled: value, broadcast_targets: value && draft.broadcast_targets.length === 0 ? ["bot"] : draft.broadcast_targets })} />{draft.broadcast_enabled && <><p style={{ margin: "0.8rem 0 0.5rem", color: "var(--era-text-muted)" }}>Куда отправить:</p><Reminder label="В личный бот участникам" minutes={0} checked={draft.broadcast_targets.includes("bot")} onChange={() => update({ broadcast_targets: toggleString(draft.broadcast_targets, "bot") })} /><Reminder label="В общий чат" minutes={0} checked={draft.broadcast_targets.includes("general")} onChange={() => update({ broadcast_targets: toggleString(draft.broadcast_targets, "general") })} /><Card style={{ marginTop: "0.75rem", boxShadow: "none", background: "var(--era-bg-subtle)" }}><p className="era-kicker">Preview сообщения</p><strong style={{ display: "block", marginTop: 5 }}>{draft.title}</strong><p style={{ margin: "0.3rem 0 0", whiteSpace: "pre-wrap" }}>{draft.short_description || draft.full_description || "Описание появится здесь"}</p><p style={{ margin: "0.45rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>{draft.event_date} · {draft.event_time} · {draft.location || "место не указано"}</p></Card><p style={{ margin: "0.6rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>{draft.broadcast_estimate > 0 ? `Оценка получателей в боте: ${draft.broadcast_estimate}` : "Получатели будут рассчитаны сервером при публикации."}</p></>}</Card>}

      {step === 10 && <><Card><p className="era-kicker">Финальный preview</p><h3 style={{ margin: "0.3rem 0 0", fontSize: "var(--era-text-xl)" }}>{draft.title}</h3><p style={{ color: "var(--era-text-muted)", whiteSpace: "pre-wrap" }}>{draft.full_description || "Описание не заполнено"}</p><PreviewRow label="Когда" value={`${draft.event_date} · ${draft.event_time}${draft.end_time ? `–${draft.end_time}` : ""}`} /><PreviewRow label="Где" value={[draft.location, draft.address].filter(Boolean).join(" · ") || "Не указано"} /><PreviewRow label="Регистрация" value={draft.registration_required ? `Да${draft.participant_limit ? ` · до ${draft.participant_limit} мест` : ""}` : "Не требуется"} /><PreviewRow label="Афиша" value={draft.has_poster ? "Загружена" : "Не загружена"} /><PreviewRow label="Программа" value={`${draft.program.length} пунктов`} /><PreviewRow label="Задания" value={`${draft.participant_tasks.length} · ${draft.points_for_visit} баллов за посещение`} /><PreviewRow label="Напоминания" value={draft.reminders.length ? draft.reminders.map((item) => `${item} мин`).join(", ") : "Не выбраны"} /><PreviewRow label="Рассылка" value={draft.broadcast_enabled ? `Да · ${draft.broadcast_targets.join(", ") || "аудитория не выбрана"}` : "Нет"} /></Card><PrimaryButton busy={busy} onClick={() => setConfirmPublish(true)}>Опубликовать событие</PrimaryButton></>}

      <div style={{ display: "grid", gridTemplateColumns: step > 1 ? "0.8fr 1.2fr" : "1fr", gap: "0.5rem" }}>
        {step > 1 && <SecondaryButton disabled={busy} onClick={back}>Назад</SecondaryButton>}
        {step < STEP_COUNT && <PrimaryButton busy={busy} busyLabel="Сохраняем…" onClick={() => void next()}>Продолжить</PrimaryButton>}
      </div>
      <SecondaryButton disabled={busy} onClick={() => { void saveNow().then((ok) => { if (ok) { setDraft(null); void reloadDrafts(); } }); }}>Сохранить и выйти</SecondaryButton>

      <BottomSheet open={confirmPublish} onClose={() => setConfirmPublish(false)} title={draft.broadcast_enabled ? "Опубликовать и запустить рассылку?" : "Опубликовать событие?"}>
        <p style={{ margin: 0, color: "var(--era-text-muted)" }}>{draft.broadcast_enabled ? "После подтверждения событие станет доступно участникам, а сервер отправит выбранную рассылку. Это действие не запускается обычным переключателем." : "После подтверждения событие станет доступно участникам. Рассылка отключена."}</p>
        <div style={{ display: "grid", gridTemplateColumns: "0.8fr 1.2fr", gap: "0.5rem", marginTop: "1rem" }}><SecondaryButton onClick={() => setConfirmPublish(false)}>Проверить ещё</SecondaryButton><PrimaryButton busy={busy} onClick={() => void publish()}><CheckIcon width={18} height={18} />Подтвердить</PrimaryButton></div>
      </BottomSheet>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) { return <label style={{ display: "block", marginTop: "0.75rem" }}><span style={{ display: "block", marginBottom: "0.35rem", fontSize: "var(--era-text-sm)", fontWeight: 850 }}>{label}</span>{children}</label>; }
function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) { return <label style={{ minHeight: 48, display: "flex", alignItems: "center", gap: "0.7rem" }}><input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} /><span style={{ fontWeight: 800 }}>{label}</span></label>; }
function Reminder({ label, checked, onChange }: { label: string; minutes: number; checked: boolean; onChange: () => void }) { return <label style={{ minHeight: 46, display: "flex", alignItems: "center", gap: "0.7rem" }}><input type="checkbox" checked={checked} onChange={onChange} /><span>{label}</span></label>; }
function PreviewRow({ label, value }: { label: string; value: string }) { return <div style={{ paddingTop: "0.65rem", marginTop: "0.65rem", borderTop: "1px solid var(--era-border)" }}><span className="era-kicker">{label}</span><strong style={{ display: "block", marginTop: 3 }}>{value}</strong></div>; }
function toggleString(values: string[], value: string): string[] { return values.includes(value) ? values.filter((item) => item !== value) : [...values, value]; }
