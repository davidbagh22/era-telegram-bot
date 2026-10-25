import { useCallback, useEffect, useState } from "react";
import { Card } from "../components/Card";
import { createMediaCalendarEntry, fetchMediaCalendar, fetchMediaMembers, fetchMediaWorkspaces, updateMediaCalendarEntry, type MediaCalendarEntry, type MediaMember, type MediaWorkspace } from "../api/media";

const statuses: Record<string, string> = { idea: "Идея", planned: "В подготовке", assigned: "Назначено", in_progress: "В работе", review: "На согласовании", ready: "Готово", scheduled: "Запланировано", published: "Опубликовано", skipped: "Отменено", failed: "Ошибка доставки" };
const platforms: Record<string, string> = { telegram: "Telegram", instagram: "Instagram", facebook: "Facebook", tiktok: "TikTok", youtube: "YouTube" };
const button: React.CSSProperties = { border: "1px solid var(--era-border)", background: "var(--era-surface-2)", color: "var(--era-text)", borderRadius: 12, padding: ".7rem .9rem", fontWeight: 700, cursor: "pointer" };
const input: React.CSSProperties = { width: "100%", boxSizing: "border-box", background: "var(--era-surface-2)", color: "var(--era-text)", border: "1px solid var(--era-border)", borderRadius: 10, padding: ".7rem", font: "inherit" };
const dateLabel = (value: string | null) => value ? new Intl.DateTimeFormat("ru-RU", { timeZone: "Asia/Yerevan", day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" }).format(new Date(value)) : "Без даты";

function Entry({ item, area, manager, members, onChanged }: { item: MediaCalendarEntry; area: string; manager: boolean; members: MediaMember[]; onChanged: () => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [url, setUrl] = useState("");
  const [date, setDate] = useState("");
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(item.title);
  const [body, setBody] = useState(item.body);
  const [responsible, setResponsible] = useState(String(item.responsible_id ?? ""));
  const terminal = ["published", "skipped"].includes(item.status);
  const change = async (values: object) => {
    setBusy(true); setError("");
    try { await updateMediaCalendarEntry(area, item.id, { revision: item.revision, ...values }); await onChanged(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось сохранить"); }
    finally { setBusy(false); }
  };
  return <Card style={{ display: "grid", gap: ".75rem" }}>
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}><strong>{item.title}</strong><span style={{ color: "var(--era-text-muted)", fontSize: ".8rem" }}>{statuses[item.status] ?? "Неизвестный статус"}</span></div>
    <div style={{ color: "var(--era-text-secondary)", fontSize: ".85rem" }}>{dateLabel(item.scheduled_at)} · {platforms[item.platform] ?? item.platform}</div>
    {item.body && <p style={{ margin: 0, whiteSpace: "pre-wrap", maxHeight: expanded ? undefined : "4.5em", overflow: "hidden" }}>{item.body}</p>}
    <small>Ответственный: {members.find(member => member.id === item.responsible_id)?.name ?? (item.responsible_id ? "назначен" : "пока не назначен")}</small>
    <button style={button} onClick={() => setExpanded(!expanded)}>{expanded ? "Свернуть материал" : "Открыть материал"}</button>
    {expanded && item.materials && <p style={{ margin: 0, whiteSpace: "pre-wrap", color: "var(--era-text-secondary)" }}>Материалы: {item.materials}</p>}
    {item.publication_url && <><a href={item.publication_url} target="_blank" rel="noopener noreferrer">Открыть публикацию ↗</a><small>Ссылка подтверждена руководителем. Это не автоматическая проверка внешнего сервиса.</small></>}
    {manager && !terminal && expanded && <>
      <button style={button} disabled={busy} onClick={() => setEditing(!editing)}>{editing ? "Закрыть редактор" : "Изменить материал / ответственного"}</button>
      {editing && <div style={{ display: "grid", gap: 10 }}>
        <label>Название материала<input style={input} value={title} maxLength={255} onChange={event => setTitle(event.target.value)} /></label>
        <label>Текст материала<textarea style={input} value={body} maxLength={4096} onChange={event => setBody(event.target.value)} /></label>
        <label>Новый ответственный<select aria-label="Новый ответственный" style={input} value={responsible} onChange={event => setResponsible(event.target.value)}><option value="">Пока не назначен</option>{members.map(member => <option key={member.id} value={member.id}>{member.name}</option>)}</select></label>
        <button style={button} disabled={busy || title.trim().length < 2} onClick={() => void change({ title: title.trim(), body, responsible_id: responsible ? Number(responsible) : null })}>Сохранить изменения</button>
      </div>}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {["planned", "assigned", "idea"].includes(item.status) && <button style={button} disabled={busy} onClick={() => void change({ status: item.status === "idea" ? "planned" : "in_progress" })}>{item.status === "idea" ? "В подготовку" : "Начать работу"}</button>}
        {["planned", "assigned", "in_progress"].includes(item.status) && <button style={button} disabled={busy} onClick={() => void change({ status: "review" })}>На согласование</button>}
        {["planned", "assigned", "in_progress", "review", "scheduled", "failed"].includes(item.status) && <button style={button} disabled={busy} onClick={() => void change({ status: "ready" })}>Утвердить</button>}
        {item.status === "review" && <button style={button} disabled={busy} onClick={() => void change({ status: "in_progress" })}>На доработку</button>}
        <button style={button} disabled={busy} onClick={() => void change({ status: "skipped" })}>Отменить</button>
      </div>
      <label>Перенести дату · время Еревана<input aria-label={`Новая дата: ${item.title}`} type="datetime-local" value={date} onChange={event => setDate(event.target.value)} style={input} /></label>
      <button style={button} disabled={busy || !date} onClick={() => void change({ scheduled_at: new Date(`${date}+04:00`).toISOString() })}>Сохранить дату</button>
      {["ready", "scheduled"].includes(item.status) && <><label>Ссылка на вышедший материал<input type="url" placeholder="https://…" style={input} value={url} onChange={event => setUrl(event.target.value)} /></label><button style={button} disabled={busy || !url.trim()} onClick={() => void change({ status: "published", publication_url: url.trim() })}>Подтвердить публикацию по ссылке</button></>}
    </>}
    {error && <p role="alert" style={{ margin: 0 }}>{error}</p>}
  </Card>;
}

export function MediaWorkspaceScreen({ area, onBack }: { area: "era" | "ksoors"; onBack: () => void }) {
  const [workspace, setWorkspace] = useState<MediaWorkspace | null>(null);
  const [items, setItems] = useState<MediaCalendarEntry[]>([]);
  const [members, setMembers] = useState<MediaMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [date, setDate] = useState("");
  const [platform, setPlatform] = useState("telegram");
  const [responsible, setResponsible] = useState("");
  const [materials, setMaterials] = useState("");
  const [requestKey, setRequestKey] = useState(() => crypto.randomUUID());
  const [filter, setFilter] = useState("active");
  const reload = useCallback(async () => { setItems(await fetchMediaCalendar(area)); }, [area]);
  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const workspaces = await fetchMediaWorkspaces();
        const current = workspaces.find(item => item.id === area) ?? null;
        const [entries, team] = await Promise.all([fetchMediaCalendar(area), current?.can_manage ? fetchMediaMembers() : Promise.resolve([])]);
        if (alive) { setWorkspace(current); setItems(entries); setMembers(team); }
      } catch (cause) { if (alive) setError(cause instanceof Error ? cause.message : "Не удалось открыть календарь"); }
      finally { if (alive) setLoading(false); }
    })();
    return () => { alive = false; };
  }, [area]);
  const save = async (event: React.FormEvent) => {
    event.preventDefault(); setBusy(true); setError("");
    try {
      await createMediaCalendarEntry(area, { request_key: requestKey, title: title.trim(), body, platform, scheduled_at: date ? new Date(`${date}+04:00`).toISOString() : null, responsible_id: responsible ? Number(responsible) : null, materials });
      setRequestKey(crypto.randomUUID()); setTitle(""); setBody(""); setDate(""); setMaterials(""); setShowForm(false); await reload();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось добавить материал"); }
    finally { setBusy(false); }
  };
  return <div className="era-page" style={{ display: "grid", gap: "1rem", padding: "1rem 1rem var(--era-page-bottom-safe)" }}>
    <button style={{ ...button, justifySelf: "start" }} onClick={onBack}>← Медиаотдел</button>
    <div><small>Медиа · {area === "era" ? "ЭРА" : "КСООРС"}</small><h1 style={{ margin: ".3rem 0" }}>Контент-план</h1><p style={{ color: "var(--era-text-secondary)" }}>Время Еревана. Запланированные материалы не считаются опубликованными.</p></div>
    {loading && <p>Загружаем календарь…</p>}
    {error && <p role="alert">{error}</p>}
    {workspace && <>
      <Card><strong>Площадки направления</strong><div style={{ display: "flex", flexWrap: "wrap", gap: 14, marginTop: 10 }}>{Object.entries(workspace.platforms).map(([key, url]) => <a key={key} href={url} target="_blank" rel="noopener noreferrer">{platforms[key]} ↗</a>)}</div></Card>
      {workspace.can_manage && <button style={button} onClick={() => setShowForm(!showForm)}>{showForm ? "Закрыть форму" : "+ Добавить материал"}</button>}
      {showForm && workspace.can_manage && <Card><form onSubmit={event => void save(event)} style={{ display: "grid", gap: 12 }}>
        <label>Название<input required minLength={2} maxLength={255} value={title} onChange={event => setTitle(event.target.value)} style={input} /></label>
        <label>Текст / замысел<textarea maxLength={4096} rows={4} value={body} onChange={event => setBody(event.target.value)} style={input} /></label>
        <label>Площадка<select aria-label="Площадка" value={platform} onChange={event => setPlatform(event.target.value)} style={input}>{Object.entries(platforms).map(([key, name]) => <option key={key} value={key}>{name}</option>)}</select></label>
        <label>Дата и время · Ереван<input type="datetime-local" value={date} onChange={event => setDate(event.target.value)} style={input} /></label>
        <label>Ответственный<select aria-label="Ответственный" value={responsible} onChange={event => setResponsible(event.target.value)} style={input}><option value="">Пока не назначен</option>{members.map(member => <option key={member.id} value={member.id}>{member.name}</option>)}</select></label>
        <label>Материалы и ссылки<textarea maxLength={3000} value={materials} onChange={event => setMaterials(event.target.value)} style={input} /></label>
        <button style={button} disabled={busy || title.trim().length < 2} type="submit">{busy ? "Сохраняем…" : "Сохранить в календаре"}</button>
      </form></Card>}
      <label>Показать<select aria-label="Показать" style={input} value={filter} onChange={event => setFilter(event.target.value)}><option value="active">В работе</option><option value="published">Опубликованные</option><option value="all">Все материалы</option></select></label>
      {items.filter(item => filter === "all" || (filter === "published" ? item.status === "published" : !["published", "skipped"].includes(item.status))).map(item => <Entry key={item.id} area={area} item={item} manager={workspace.can_manage} members={members} onChanged={reload} />)}
      {!items.length && <Card>Материалов пока нет. Руководитель может добавить первый.</Card>}
      <small>Показаны последние 100 материалов. Публикации во внешние сервисы автоматически не отправляются.</small>
    </>}
  </div>;
}
