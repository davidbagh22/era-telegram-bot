import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  createEventDraft,
  listEventDrafts,
  publishEventDraft,
  removeEventPoster,
  saveEventDraft,
  uploadEventPoster,
} from "../../../api/adminEvents";
import type {
  AdminEventDraft,
  AdminEventDraftPatch,
  EventProgramDraftItem,
  EventTaskDraftItem,
} from "../../../api/adminEvents";
import { describeActionError, fetchProjects } from "../../../api/client";
import { Card } from "../../../components/Card";
import { useAsync } from "../../../hooks/useAsync";

const STEP_TITLES = [
  "Основное",
  "Когда и где",
  "Афиша",
  "Регистрация",
  "Чат",
  "Активности",
  "Задания и баллы",
  "Напоминания",
  "Рассылка",
  "Проверка",
] as const;

const REMINDERS = [
  { value: 1440, label: "За 24 часа" },
  { value: 180, label: "За 3 часа" },
  { value: 60, label: "За 1 час" },
];

function patchFromDraft(draft: AdminEventDraft, wizardStep = draft.wizard_step): AdminEventDraftPatch {
  return {
    wizard_step: wizardStep,
    title: draft.title,
    short_description: draft.short_description,
    full_description: draft.full_description,
    project_id: draft.project_id,
    category: draft.category ?? "",
    event_date: draft.event_date,
    event_time: draft.event_time,
    end_time: draft.end_time ?? undefined,
    location: draft.location,
    address: draft.address ?? "",
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

function StepHeader({ step }: { step: number }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", color: "var(--era-text-muted)", fontSize: "0.78rem", fontWeight: 800 }}>
        <span>ШАГ {step} ИЗ 10</span>
        <span>{STEP_TITLES[step - 1]}</span>
      </div>
      <div style={{ height: 5, borderRadius: 99, background: "rgba(255,255,255,.08)", overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${step * 10}%`, background: "linear-gradient(90deg,#E51B36,#FF304D,#8A1FE0)", transition: "width .2s ease" }} />
      </div>
    </div>
  );
}

export function AdminEventCreatePanel() {
  const [drafts, setDrafts] = useState<AdminEventDraft[] | null>(null);
  const [draft, setDraft] = useState<AdminEventDraft | null>(null);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveLabel, setSaveLabel] = useState("Все изменения сохраняются автоматически");
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [customReminder, setCustomReminder] = useState("");
  const versionRef = useRef(0);
  const projectsState = useAsync(() => fetchProjects("open"), []);

  useEffect(() => {
    let active = true;
    listEventDrafts()
      .then((items) => { if (active) setDrafts(items); })
      .catch(() => { if (active) setDrafts([]); });
    return () => { active = false; };
  }, []);

  const mutate = useCallback((recipe: (current: AdminEventDraft) => AdminEventDraft) => {
    setDraft((current) => {
      if (!current) return current;
      versionRef.current += 1;
      setDirty(true);
      setSaveLabel("Сохраняем изменения…");
      return recipe(current);
    });
  }, []);

  const saveNow = useCallback(async (targetStep?: number): Promise<AdminEventDraft | null> => {
    if (!draft) return null;
    const capturedVersion = versionRef.current;
    setSaving(true);
    setError(null);
    try {
      const result = await saveEventDraft(draft.id, patchFromDraft(draft, targetStep ?? draft.wizard_step));
      if (capturedVersion === versionRef.current) {
        setDraft(result);
        setDirty(false);
        setSaveLabel("Сохранено ✓");
      }
      return result;
    } catch (reason) {
      setError(describeActionError(reason));
      setSaveLabel("Не удалось сохранить — данные остались на экране");
      return null;
    } finally {
      setSaving(false);
    }
  }, [draft]);

  useEffect(() => {
    if (!draft || !dirty) return;
    const timer = window.setTimeout(() => { void saveNow(); }, 700);
    return () => window.clearTimeout(timer);
  }, [dirty, draft, saveNow]);

  const begin = async () => {
    setBusy(true);
    setError(null);
    try {
      const item = await createEventDraft();
      setDraft(item);
      setSaveLabel("Черновик создан ✓");
    } catch (reason) {
      setError(describeActionError(reason));
    } finally {
      setBusy(false);
    }
  };

  const next = async () => {
    if (!draft || draft.wizard_step >= 10) return;
    const target = draft.wizard_step + 1;
    const result = await saveNow(target);
    if (result) setDraft({ ...result, wizard_step: target });
  };

  const back = async () => {
    if (!draft || draft.wizard_step <= 1) return;
    const target = draft.wizard_step - 1;
    const result = await saveNow(target);
    if (result) setDraft({ ...result, wizard_step: target });
  };

  const leaveDraft = async () => {
    if (dirty) await saveNow();
    setDraft(null);
    setDrafts(await listEventDrafts());
  };

  const publish = async () => {
    if (!draft) return;
    setBusy(true);
    setError(null);
    try {
      if (dirty) {
        const saved = await saveNow(10);
        if (!saved) return;
      }
      const result = await publishEventDraft(draft.id);
      setDraft(result);
      setSaveLabel("Опубликовано ✓");
    } catch (reason) {
      setError(describeActionError(reason));
    } finally {
      setBusy(false);
    }
  };

  if (drafts === null && draft === null) {
    return <Card><p style={{ margin: 0, color: "var(--era-text-muted)" }}>Загружаем черновики…</p></Card>;
  }

  if (!draft) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        <Card gradient>
          <p style={{ margin: "0 0 .3rem", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase", color: "rgba(255,255,255,.7)" }}>Конструктор события</p>
          <h2 style={{ margin: 0, fontSize: "var(--era-text-2xl)" }}>Создайте событие без огромной формы</h2>
          <p style={{ margin: ".5rem 0 0", color: "rgba(255,255,255,.82)" }}>Десять коротких шагов. Каждый шаг сохраняется автоматически — можно закрыть приложение и продолжить позже.</p>
        </Card>
        <button type="button" className="era-btn-primary" disabled={busy} onClick={() => void begin()} style={{ width: "100%" }}>
          {busy ? "Создаём…" : "＋ Создать мероприятие"}
        </button>
        {(drafts ?? []).length > 0 && (
          <section>
            <h3 style={{ margin: "0 0 .55rem" }}>Продолжить создание</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: ".5rem" }}>
              {(drafts ?? []).map((item) => (
                <button key={item.id} type="button" onClick={() => { setDraft(item); setSaveLabel("Черновик восстановлен ✓"); }} style={{ textAlign: "left", padding: ".85rem" }}>
                  <strong>{item.title || "Новое мероприятие"}</strong>
                  <span style={{ display: "block", marginTop: 3, color: "var(--era-text-muted)", fontSize: ".8rem" }}>Шаг {item.wizard_step} из 10 · {STEP_TITLES[item.wizard_step - 1]}</span>
                </button>
              ))}
            </div>
          </section>
        )}
      </div>
    );
  }

  if (draft.is_complete && draft.status !== "draft") {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: ".75rem" }}>
        <Card gradient><p style={{ margin: 0, fontSize: ".8rem", fontWeight: 800 }}>ОПУБЛИКОВАНО</p><h2 style={{ margin: ".35rem 0 0" }}>{draft.title}</h2></Card>
        <Card><strong>Событие уже в системе ✓</strong><p style={{ margin: ".35rem 0 0", color: "var(--era-text-muted)" }}>Регистрация, напоминания и выбранная рассылка работают из данных этого события.</p></Card>
        <button type="button" onClick={() => void leaveDraft()}>Создать ещё одно мероприятие</button>
      </div>
    );
  }

  const step = draft.wizard_step;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: ".75rem", paddingBottom: "1rem" }}>
      <StepHeader step={step} />
      <div style={{ display: "flex", justifyContent: "space-between", gap: ".5rem", alignItems: "center" }}>
        <button type="button" onClick={() => void leaveDraft()} style={{ padding: ".45rem .65rem" }}>← Черновики</button>
        <span style={{ color: saveLabel.includes("Не удалось") ? "var(--era-error)" : "var(--era-text-muted)", fontSize: ".75rem", textAlign: "right" }}>{saving ? "Сохраняем…" : saveLabel}</span>
      </div>

      <Card>
        {step === 1 && (
          <>
            <Question title="Что вы создаёте?" hint="Название и два уровня описания: короткий текст для карточки и полный — для страницы события." />
            <Field label="Название"><input value={draft.title === "Новое мероприятие" ? "" : draft.title} onChange={(event) => mutate((current) => ({ ...current, title: event.target.value }))} placeholder="Например: Медиа без скуки" /></Field>
            <Field label="Короткое описание"><textarea rows={3} value={draft.short_description} onChange={(event) => mutate((current) => ({ ...current, short_description: event.target.value }))} placeholder="Одна сильная мысль для карточки" /></Field>
            <Field label="Полное описание"><textarea rows={6} value={draft.full_description} onChange={(event) => mutate((current) => ({ ...current, full_description: event.target.value }))} placeholder="Что будет происходить, для кого и зачем" /></Field>
            <Field label="Категория"><input value={draft.category ?? ""} onChange={(event) => mutate((current) => ({ ...current, category: event.target.value }))} placeholder="Мастер-класс, игра, встреча…" /></Field>
            <Field label="Связанный проект" hint="Необязательно. Если событие является частью проекта — свяжите их.">
              <select value={draft.project_id ?? ""} onChange={(event) => mutate((current) => ({ ...current, project_id: event.target.value ? Number(event.target.value) : null }))}>
                <option value="">Без проекта</option>
                {projectsState.status === "ready" && projectsState.data.map((project) => <option key={project.id} value={project.id}>{project.title}</option>)}
              </select>
            </Field>
          </>
        )}

        {step === 2 && (
          <>
            <Question title="Когда и где встречаемся?" hint="Эти данные попадут в карточку, подтверждение регистрации и календарь участника." />
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: ".5rem" }}>
              <Field label="Дата"><input type="date" value={draft.event_date} onChange={(event) => mutate((current) => ({ ...current, event_date: event.target.value }))} /></Field>
              <Field label="Начало"><input type="time" value={draft.event_time} onChange={(event) => mutate((current) => ({ ...current, event_time: event.target.value }))} /></Field>
            </div>
            <Field label="Окончание"><input type="time" value={draft.end_time ?? ""} onChange={(event) => mutate((current) => ({ ...current, end_time: event.target.value || null }))} /></Field>
            <Field label="Место"><input value={draft.location} onChange={(event) => mutate((current) => ({ ...current, location: event.target.value }))} placeholder="Дом Москвы в Ереване" /></Field>
            <Field label="Адрес"><input value={draft.address ?? ""} onChange={(event) => mutate((current) => ({ ...current, address: event.target.value }))} placeholder="Улица, дом, этаж — если нужно" /></Field>
            <Field label="Формат">
              <select value={draft.attendance_mode} onChange={(event) => mutate((current) => ({ ...current, attendance_mode: event.target.value as AdminEventDraft["attendance_mode"] }))}>
                <option value="offline">Офлайн</option><option value="online">Онлайн</option><option value="hybrid">Гибрид</option>
              </select>
            </Field>
          </>
        )}

        {step === 3 && (
          <>
            <Question title="Добавим афишу?" hint="Фото сразу станет главным визуалом карточки и страницы события. До 5 МБ." />
            {draft.has_poster ? (
              <div style={{ display: "flex", flexDirection: "column", gap: ".65rem" }}>
                <div style={{ minHeight: 150, borderRadius: "1rem", background: "linear-gradient(135deg,#710016,#E51B36,#8A1FE0)", display: "grid", placeItems: "center", fontWeight: 900 }}>Афиша загружена ✓</div>
                <label className="era-btn-primary" style={{ textAlign: "center", cursor: "pointer" }}>Заменить афишу<input hidden type="file" accept="image/*" onChange={(event) => { const file = event.target.files?.[0]; if (file) void uploadEventPoster(draft.id, file).then(setDraft).catch((reason) => setError(describeActionError(reason))); }} /></label>
                <button type="button" onClick={() => void removeEventPoster(draft.id).then(setDraft).catch((reason) => setError(describeActionError(reason)))}>Удалить</button>
              </div>
            ) : (
              <label style={{ display: "grid", placeItems: "center", minHeight: 180, border: "1px dashed var(--era-border)", borderRadius: "1rem", cursor: "pointer", textAlign: "center", padding: "1rem" }}>
                <span><strong>＋ Загрузить афишу</strong><span style={{ display: "block", color: "var(--era-text-muted)", marginTop: 4, fontSize: ".82rem" }}>JPG, PNG, WEBP · до 5 МБ</span></span>
                <input hidden type="file" accept="image/*" onChange={(event) => { const file = event.target.files?.[0]; if (file) void uploadEventPoster(draft.id, file).then(setDraft).catch((reason) => setError(describeActionError(reason))); }} />
              </label>
            )}
          </>
        )}

        {step === 4 && (
          <>
            <Question title="Нужна регистрация?" hint="Настройте места один раз — Mini App сам покажет остаток и при необходимости включит лист ожидания." />
            <Toggle checked={draft.registration_required} onChange={(checked) => mutate((current) => ({ ...current, registration_required: checked }))} title="Регистрация нужна" />
            {draft.registration_required && (
              <>
                <Field label="Количество мест"><input inputMode="numeric" value={draft.participant_limit ?? ""} onChange={(event) => mutate((current) => ({ ...current, participant_limit: event.target.value ? Number(event.target.value) : null }))} placeholder="40" /></Field>
                <Field label="Закрыть регистрацию"><input type="datetime-local" value={(draft.registration_close_at ?? "").slice(0, 16)} onChange={(event) => mutate((current) => ({ ...current, registration_close_at: event.target.value || null }))} /></Field>
                <Toggle checked={draft.waitlist_enabled} onChange={(checked) => mutate((current) => ({ ...current, waitlist_enabled: checked }))} title="Разрешить лист ожидания" hint="Когда места закончатся, новые участники попадут в очередь. Освободившееся место перейдёт первому автоматически." />
                <Field label="Кто может регистрироваться"><select value={draft.registration_audience} onChange={(event) => mutate((current) => ({ ...current, registration_audience: event.target.value }))}><option value="all">Все одобренные участники ЭРА</option><option value="active">Только активные участники</option><option value="leaders">Лидеры и руководители</option></select></Field>
              </>
            )}
          </>
        )}

        {step === 5 && (
          <>
            <Question title="Есть отдельный чат мероприятия?" hint="Это отдельная сущность. Ссылка появится только на странице события и после регистрации." />
            <Toggle checked={Boolean(draft.chat_url)} onChange={(checked) => mutate((current) => ({ ...current, chat_url: checked ? "https://t.me/" : null }))} title="Да, есть чат" />
            {draft.chat_url !== null && <Field label="URL Telegram-чата"><input type="url" value={draft.chat_url} onChange={(event) => mutate((current) => ({ ...current, chat_url: event.target.value }))} placeholder="https://t.me/+..." /></Field>}
            <Field label="Организатор"><input value={draft.organizer ?? ""} onChange={(event) => mutate((current) => ({ ...current, organizer: event.target.value }))} placeholder="Команда ЭРА / имя ответственного" /></Field>
            <Field label="Контакт"><input value={draft.contact ?? ""} onChange={(event) => mutate((current) => ({ ...current, contact: event.target.value }))} placeholder="К кому обратиться по вопросам" /></Field>
            <Field label="Что получит участник"><textarea rows={4} value={draft.participant_value ?? ""} onChange={(event) => mutate((current) => ({ ...current, participant_value: event.target.value }))} placeholder="Практика, сертификат, новые знакомства, результат…" /></Field>
          </>
        )}

        {step === 6 && (
          <>
            <Question title="Есть программа или активности внутри мероприятия?" hint="Добавьте столько пунктов, сколько нужно. На странице они соберутся в понятную программу." />
            {draft.program.map((item, index) => (
              <ArrayCard key={index} title={`Активность ${index + 1}`} onRemove={() => mutate((current) => ({ ...current, program: current.program.filter((_, itemIndex) => itemIndex !== index) }))}>
                <Field label="Название"><input value={item.title} onChange={(event) => updateProgram(index, { ...item, title: event.target.value }, mutate)} /></Field>
                <div style={{ display: "grid", gridTemplateColumns: "100px 1fr", gap: ".5rem" }}><Field label="Время"><input type="time" value={item.time ?? ""} onChange={(event) => updateProgram(index, { ...item, time: event.target.value }, mutate)} /></Field><Field label="Ведущий"><input value={item.responsible ?? ""} onChange={(event) => updateProgram(index, { ...item, responsible: event.target.value }, mutate)} /></Field></div>
                <Field label="Описание"><textarea rows={3} value={item.description ?? ""} onChange={(event) => updateProgram(index, { ...item, description: event.target.value }, mutate)} /></Field>
              </ArrayCard>
            ))}
            <button type="button" onClick={() => mutate((current) => ({ ...current, program: [...current.program, { title: "" }] }))}>＋ Добавить активность</button>
          </>
        )}

        {step === 7 && (
          <>
            <Question title="Будут задания для участников?" hint="Задания показываются внутри события. Баллы за посещение задаются отдельно и могут быть равны нулю." />
            <Field label="Баллы за посещение"><input inputMode="numeric" value={draft.points_for_visit} onChange={(event) => mutate((current) => ({ ...current, points_for_visit: Math.max(0, Number(event.target.value) || 0) }))} /></Field>
            {draft.participant_tasks.map((item, index) => (
              <ArrayCard key={index} title={`Задание ${index + 1}`} onRemove={() => mutate((current) => ({ ...current, participant_tasks: current.participant_tasks.filter((_, itemIndex) => itemIndex !== index) }))}>
                <Field label="Название"><input value={item.title} onChange={(event) => updateTask(index, { ...item, title: event.target.value }, mutate)} /></Field>
                <Field label="Описание"><textarea rows={3} value={item.description ?? ""} onChange={(event) => updateTask(index, { ...item, description: event.target.value }, mutate)} /></Field>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 100px", gap: ".5rem" }}><Field label="Срок"><input type="datetime-local" value={(item.deadline ?? "").slice(0, 16)} onChange={(event) => updateTask(index, { ...item, deadline: event.target.value }, mutate)} /></Field><Field label="Баллы"><input inputMode="numeric" value={item.points ?? 0} onChange={(event) => updateTask(index, { ...item, points: Number(event.target.value) || 0 }, mutate)} /></Field></div>
                <Toggle checked={Boolean(item.confirmation_required)} onChange={(checked) => updateTask(index, { ...item, confirmation_required: checked }, mutate)} title="Требуется подтверждение" />
                {item.confirmation_required && <Field label="Кто подтверждает"><input value={item.reviewer ?? ""} onChange={(event) => updateTask(index, { ...item, reviewer: event.target.value }, mutate)} placeholder="Лидер / администратор" /></Field>}
              </ArrayCard>
            ))}
            <button type="button" onClick={() => mutate((current) => ({ ...current, participant_tasks: [...current.participant_tasks, { title: "", points: 0 }] }))}>＋ Добавить задание</button>
          </>
        )}

        {step === 8 && (
          <>
            <Question title="Отправлять напоминания зарегистрированным?" hint="Можно выбрать несколько моментов. Они сохраняются в событии и используются планировщиком уведомлений." />
            {REMINDERS.map((item) => <Toggle key={item.value} checked={draft.reminders.includes(item.value)} onChange={(checked) => mutate((current) => ({ ...current, reminders: checked ? [...current.reminders, item.value] : current.reminders.filter((value) => value !== item.value) }))} title={item.label} />)}
            <Field label="Своё время, минут до события"><div style={{ display: "flex", gap: ".5rem" }}><input inputMode="numeric" value={customReminder} onChange={(event) => setCustomReminder(event.target.value)} placeholder="Например, 30" /><button type="button" onClick={() => { const value = Number(customReminder); if (value > 0) { mutate((current) => ({ ...current, reminders: [...current.reminders.filter((item) => item !== value), value] })); setCustomReminder(""); } }}>Добавить</button></div></Field>
            {draft.reminders.length > 0 && <p style={{ color: "var(--era-text-muted)", fontSize: ".82rem", marginBottom: 0 }}>Сохранено: {draft.reminders.sort((a, b) => b - a).map((value) => value >= 60 ? `${value / 60} ч` : `${value} мин`).join(" · ")}</p>}
          </>
        )}

        {step === 9 && (
          <>
            <Question title="Сделать рассылку после публикации?" hint="Ничего не отправится до финальной кнопки «Опубликовать». Перед отправкой видно примерное количество получателей." />
            <Toggle checked={draft.broadcast_enabled} onChange={(checked) => mutate((current) => ({ ...current, broadcast_enabled: checked, broadcast_targets: checked ? (current.broadcast_targets.length ? current.broadcast_targets : ["bot"]) : [] }))} title="Сделать рассылку" />
            {draft.broadcast_enabled && (
              <>
                <Radio checked={draft.broadcast_targets.includes("bot") && !draft.broadcast_targets.includes("general")} onClick={() => mutate((current) => ({ ...current, broadcast_targets: ["bot"] }))} title="В бот всем участникам" />
                <Radio checked={draft.broadcast_targets.includes("audience:active")} onClick={() => mutate((current) => ({ ...current, broadcast_targets: ["bot", "audience:active"] }))} title="Выбранной аудитории — активным" />
                <Radio checked={draft.broadcast_targets.length === 1 && draft.broadcast_targets[0] === "general"} onClick={() => mutate((current) => ({ ...current, broadcast_targets: ["general"] }))} title="В общий чат" />
                <Radio checked={draft.broadcast_targets.includes("bot_and_chat")} onClick={() => mutate((current) => ({ ...current, broadcast_targets: ["bot_and_chat"] }))} title="Общий чат + бот" />
                <Card style={{ marginTop: ".6rem", background: "rgba(229,27,54,.08)" }}><strong>Примерный охват: {draft.broadcast_estimate}</strong><p style={{ margin: ".25rem 0 0", color: "var(--era-text-muted)", fontSize: ".82rem" }}>Точное число может измениться к моменту публикации.</p></Card>
                <div style={{ marginTop: ".75rem" }}><strong>Предпросмотр</strong><div style={{ marginTop: ".4rem", padding: ".8rem", borderRadius: ".9rem", background: "rgba(255,255,255,.04)" }}>🔥 <strong>{draft.title}</strong><br /><br />{draft.short_description || "Короткое описание появится здесь"}<br /><br />📅 {draft.event_date} · {draft.event_time}<br />📍 {draft.location || "Место"}</div></div>
              </>
            )}
          </>
        )}

        {step === 10 && (
          <>
            <Question title="Так событие увидят участники" hint="Проверьте главное. Вернуться на любой шаг можно кнопкой «Назад». Рассылка отправится только после публикации." />
            <div style={{ minHeight: 150, borderRadius: "1rem", background: draft.has_poster ? `url(/api/v1/event-posters/${draft.id}) center/cover` : "linear-gradient(135deg,#710016,#E51B36,#8A1FE0)", marginBottom: ".75rem" }} />
            <h2 style={{ margin: "0 0 .35rem", fontSize: "1.55rem" }}>{draft.title}</h2>
            <p style={{ margin: "0 0 .8rem", color: "var(--era-text-muted)" }}>{draft.short_description}</p>
            <Card style={{ padding: ".8rem" }}><strong>📅 {draft.event_date} · {draft.event_time}{draft.end_time ? `–${draft.end_time}` : ""}</strong><p style={{ margin: ".25rem 0 0" }}>📍 {draft.location}</p><p style={{ margin: ".25rem 0 0" }}>{draft.participant_limit ? `${draft.participant_limit} мест` : "Без ограничения мест"} · {draft.points_for_visit} баллов</p></Card>
            {draft.program.length > 0 && <p style={{ marginBottom: 0 }}>Программа: {draft.program.length} пунктов</p>}
            {draft.participant_tasks.length > 0 && <p style={{ margin: ".25rem 0 0" }}>Задания: {draft.participant_tasks.length}</p>}
            {draft.reminders.length > 0 && <p style={{ margin: ".25rem 0 0" }}>Напоминаний: {draft.reminders.length}</p>}
            {draft.broadcast_enabled && <p style={{ margin: ".25rem 0 0" }}>Рассылка: включена · ≈{draft.broadcast_estimate} получателей</p>}
          </>
        )}
      </Card>

      {error && <p style={{ margin: 0, color: "var(--era-error)" }}>{error}</p>}

      <div style={{ display: "grid", gridTemplateColumns: step === 1 ? "1fr" : "0.8fr 1.2fr", gap: ".5rem" }}>
        {step > 1 && <button type="button" disabled={saving || busy} onClick={() => void back()}>Назад</button>}
        {step < 10 ? (
          <button type="button" className="era-btn-primary" disabled={saving || busy} onClick={() => void next()}>Продолжить</button>
        ) : (
          <button type="button" className="era-btn-primary" disabled={saving || busy} onClick={() => void publish()}>{busy ? "Публикуем…" : "Опубликовать"}</button>
        )}
      </div>
      <button type="button" disabled={saving} onClick={() => void leaveDraft()}>Сохранить черновик и выйти</button>
    </div>
  );
}

function updateProgram(index: number, value: EventProgramDraftItem, mutate: (recipe: (current: AdminEventDraft) => AdminEventDraft) => void) {
  mutate((current) => ({ ...current, program: current.program.map((item, itemIndex) => itemIndex === index ? value : item) }));
}

function updateTask(index: number, value: EventTaskDraftItem, mutate: (recipe: (current: AdminEventDraft) => AdminEventDraft) => void) {
  mutate((current) => ({ ...current, participant_tasks: current.participant_tasks.map((item, itemIndex) => itemIndex === index ? value : item) }));
}

function Question({ title, hint }: { title: string; hint: string }) {
  return <div style={{ marginBottom: "1rem" }}><h3 style={{ margin: 0, fontSize: "1.22rem" }}>{title}</h3><p style={{ margin: ".35rem 0 0", color: "var(--era-text-muted)", lineHeight: 1.45 }}>{hint}</p></div>;
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return <label style={{ display: "flex", flexDirection: "column", gap: ".35rem", marginBottom: ".8rem" }}><strong>{label}</strong>{hint && <span style={{ color: "var(--era-text-muted)", fontSize: ".8rem" }}>{hint}</span>}{children}</label>;
}

function Toggle({ checked, onChange, title, hint }: { checked: boolean; onChange: (value: boolean) => void; title: string; hint?: string }) {
  return <label style={{ display: "flex", gap: ".65rem", alignItems: "flex-start", padding: ".7rem 0" }}><input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} /><span><strong>{title}</strong>{hint && <span style={{ display: "block", marginTop: 3, color: "var(--era-text-muted)", fontSize: ".8rem", lineHeight: 1.35 }}>{hint}</span>}</span></label>;
}

function Radio({ checked, onClick, title }: { checked: boolean; onClick: () => void; title: string }) {
  return <button type="button" onClick={onClick} style={{ width: "100%", display: "flex", alignItems: "center", gap: ".6rem", textAlign: "left", marginTop: ".45rem" }}><span style={{ width: 18, height: 18, borderRadius: "50%", border: "1px solid var(--era-border)", display: "grid", placeItems: "center" }}>{checked ? "●" : ""}</span><strong>{title}</strong></button>;
}

function ArrayCard({ title, onRemove, children }: { title: string; onRemove: () => void; children: ReactNode }) {
  return <div style={{ border: "1px solid var(--era-border)", borderRadius: "1rem", padding: ".8rem", marginBottom: ".65rem" }}><div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: ".65rem" }}><strong>{title}</strong><button type="button" onClick={onRemove} style={{ padding: ".35rem .55rem" }}>Удалить</button></div>{children}</div>;
}
