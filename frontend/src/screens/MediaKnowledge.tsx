import { useCallback, useEffect, useState } from "react";
import { createMediaLibraryItem, fetchMediaLibrary, updateMediaLibraryItem, type MediaLibraryItem } from "../api/media";
import { Card } from "../components/Card";
import { safeEvidenceUrl } from "../utils/safeEvidenceUrl";

const categories: Record<string, string> = { photo: "Фото и съёмка", editing: "Монтаж", journalism: "Журналистика и интервью", texts: "Тексты", design: "Дизайн", short_video: "Сторис и короткие видео", standards: "Стандарты ЭРА", publishing: "Инструкции публикации", logos: "Логотипы", canva: "Шаблоны Canva", video: "Видео", fonts_visual: "Шрифты и визуал", guides: "Инструкции", examples: "Примеры", partner_materials: "Материалы партнёров", archive: "Архив" };
const button: React.CSSProperties = { background: "var(--era-surface-2)", color: "var(--era-text)", border: "1px solid var(--era-border)", borderRadius: 12, padding: ".7rem", fontWeight: 700, cursor: "pointer" };
const input: React.CSSProperties = { ...button, width: "100%", boxSizing: "border-box", font: "inherit", cursor: "auto" };

type Draft = { id?: number; revision?: number; title: string; description: string; url: string; category: string; kind: string; pinned: boolean; request_key: string };
const blank = (): Draft => ({ title: "", description: "", url: "", category: "guides", kind: "text", pinned: false, request_key: crypto.randomUUID() });

export function MediaKnowledge({ manager, onGuide }: { manager: boolean; onGuide: () => void }) {
  const [items, setItems] = useState<MediaLibraryItem[]>([]);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [archived, setArchived] = useState(false);
  const [loading, setLoading] = useState(true);
  const [retryKey, setRetryKey] = useState(0);
  const [loadedScope, setLoadedScope] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);
  const [expanded, setExpanded] = useState<number | null>(null);
  // A cached archived/manager response must never render under a different role
  // or visibility scope, even for the frame before a new effect runs.
  const scope = `${manager ? "manager" : "reader"}:${manager && archived ? "archived" : "active"}`;
  const reload = useCallback(async () => {
    const value = await fetchMediaLibrary(manager && archived);
    setItems(value);
    setLoadedScope(scope);
  }, [manager, archived, scope]);
  useEffect(() => {
    let alive = true;
    setLoading(true); setError(""); setItems([]); setLoadedScope(null);
    void fetchMediaLibrary(manager && archived)
      .then(value => { if (alive) { setItems(value); setLoadedScope(scope); setError(""); } })
      .catch(cause => { if (alive) setError(cause instanceof Error ? cause.message : "Не удалось открыть базу знаний"); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [manager, archived, scope, retryKey]);
  useEffect(() => { if (!manager) setDraft(null); }, [manager]);
  const save = async (event: React.FormEvent) => {
    event.preventDefault(); if (!draft) return; setBusy(true); setError("");
    try {
      const { id, request_key, revision, ...values } = draft;
      if (id) await updateMediaLibraryItem(id, { ...values, revision });
      else await createMediaLibraryItem({ ...values, request_key });
      setDraft(null); await reload();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось сохранить материал"); }
    finally { setBusy(false); }
  };
  const change = async (item: MediaLibraryItem, values: object) => {
    setBusy(true); setError("");
    try { await updateMediaLibraryItem(item.id, { revision: item.revision, ...values }); await reload(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось изменить материал"); }
    finally { setBusy(false); }
  };
  const visible = (loadedScope === scope ? items : []).filter(item => !["chat", "channel"].includes(item.kind) && (!category || item.category === category) && `${item.title} ${item.description ?? ""}`.toLocaleLowerCase("ru").includes(query.trim().toLocaleLowerCase("ru")));
  return <div style={{ display: "grid", gap: 12, minWidth: 0 }}>
    <p style={{ margin: 0 }}>Всё для работы команды: инструкции, примеры, шаблоны и полезные ссылки.</p>
    <label>Поиск в базе знаний<input type="search" style={input} value={query} onChange={event => setQuery(event.target.value)} /></label>
    <label>Категория<select aria-label="Категория" style={input} value={category} onChange={event => setCategory(event.target.value)}><option value="">Все категории</option>{Object.entries(categories).map(([key, title]) => <option key={key} value={key}>{title}</option>)}</select></label>
    {manager && <><button style={button} onClick={() => { setDraft(blank()); setError(""); }}>Добавить материал в базу</button><label><input type="checkbox" checked={archived} onChange={event => setArchived(event.target.checked)} /> Показывать скрытые материалы</label></>}
    {draft && manager && <Card><form onSubmit={event => void save(event)} style={{ display: "grid", gap: 12 }}>
      <strong>{draft.id ? "Редактирование материала" : "Новый материал"}</strong>
      <label>Название материала<input required minLength={2} maxLength={255} style={input} value={draft.title} onChange={event => setDraft({ ...draft, title: event.target.value })} /></label>
      <label>Вид материала<select style={input} value={draft.kind} onChange={event => setDraft({ ...draft, kind: event.target.value })}>{Object.entries({ text: "Текстовая инструкция", link: "Полезная ссылка", document: "Документ", video: "Видео", template: "Шаблон", photo: "Фото", file: "Файл", guide: "Руководство", brand_asset: "Фирменный материал" }).map(([key, title]) => <option key={key} value={key}>{title}</option>)}</select></label>
      <label>Категория материала<select aria-label="Категория материала" style={input} value={draft.category} onChange={event => setDraft({ ...draft, category: event.target.value })}>{Object.entries(categories).map(([key, title]) => <option key={key} value={key}>{title}</option>)}</select></label>
      <label>Текст или описание<textarea aria-label="Текст или описание" rows={5} required={draft.kind === "text"} maxLength={6000} style={input} value={draft.description} onChange={event => setDraft({ ...draft, description: event.target.value })} /></label>
      <label>Ссылка на материал<input type="url" required={draft.kind !== "text" && !draft.id} maxLength={1000} placeholder="https://…" style={input} value={draft.url.startsWith("media/") ? "" : draft.url} onChange={event => setDraft({ ...draft, url: event.target.value })} /></label>
      <label><input type="checkbox" checked={draft.pinned} onChange={event => setDraft({ ...draft, pinned: event.target.checked })} /> Закрепить в начале списка</label>
      <button style={button} disabled={busy} type="submit">{busy ? "Сохраняем…" : "Сохранить материал"}</button><button style={button} disabled={busy} type="button" onClick={() => setDraft(null)}>Отмена</button>
    </form></Card>}
    {error && <p role="alert">{error}</p>}
    {!loading && error && <button type="button" style={button} onClick={() => setRetryKey(key => key + 1)}>Повторить загрузку базы знаний</button>}
    {!loading && !error && <button type="button" style={button} onClick={() => setRetryKey(key => key + 1)}>Обновить базу знаний</button>}
    {loading ? <p>Загружаем материалы…</p> : !error && !visible.length && <Card>По этим условиям материалов пока нет.</Card>}
    {visible.map(item => <Card key={item.id} style={{ display: "grid", gap: 10, overflowWrap: "anywhere" }}>
      <strong>{item.pinned ? "Закреплено · " : ""}{item.title}{!item.is_active ? " · скрыт" : ""}</strong><small>{categories[item.category] ?? "Рабочие материалы"}</small>
      {item.description && <><p style={{ margin: 0, whiteSpace: "pre-wrap", maxHeight: expanded === item.id ? undefined : "4.5em", overflow: "hidden" }}>{item.description}</p><button style={button} onClick={() => setExpanded(expanded === item.id ? null : item.id)}>{expanded === item.id ? "Свернуть текст" : "Читать полностью"}</button></>}
      {item.url && (item.destination_type === "internal_route" ? <button style={button} onClick={onGuide}>Открыть руководство</button> : safeEvidenceUrl(item.url) ? <a href={safeEvidenceUrl(item.url) ?? undefined} target="_blank" rel="noopener noreferrer">Открыть материал ↗</a> : <small>Ссылка материала имеет неподдерживаемый формат.</small>)}
      {manager && <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}><button style={button} disabled={busy} onClick={() => setDraft({ id: item.id, revision: item.revision, title: item.title, description: item.description ?? "", url: item.url, category: item.category, kind: item.kind, pinned: item.pinned, request_key: crypto.randomUUID() })}>Изменить: {item.title}</button><button style={button} disabled={busy} onClick={() => void change(item, { pinned: !item.pinned })}>{item.pinned ? "Открепить" : "Закрепить"}</button><button style={button} disabled={busy} onClick={() => void change(item, { is_active: !item.is_active })}>{item.is_active ? "Скрыть материал" : "Вернуть в каталог"}</button></div>}
    </Card>)}
  </div>;
}
