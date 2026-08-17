import { useCallback, useEffect, useMemo, useState } from "react";
import { ActionCell } from "../components/ActionCell";
import { Card } from "../components/Card";
import {
  createMediaTasks,
  fetchMediaAnalytics,
  fetchMediaChannelHealth,
  fetchMediaConfig,
  fetchMediaContentPlan,
  fetchMediaHub,
  fetchMediaLibrary,
  fetchMediaToday,
  pauseMedia,
  publishMediaContentNow,
  resumeMedia,
  setMediaAuto,
  skipMediaContent,
  submitMediaIdea,
  type MediaAnalytics,
  type MediaConfig,
  type MediaContent,
  type MediaHub,
  type MediaLibraryItem,
  type MediaTask,
} from "../api/media";

interface MediaScreenProps {
  onBack?: () => void;
}

type DeskView =
  | "home"
  | "today"
  | "plan"
  | "tasks"
  | "team"
  | "chat"
  | "channel"
  | "files"
  | "analytics"
  | "settings";

const buttonStyle = (primary = false): React.CSSProperties => ({
  border: primary ? "1px solid rgba(255,255,255,0.14)" : "1px solid var(--era-border)",
  background: primary ? "var(--era-accent, #7c3aed)" : "var(--era-surface-2, rgba(255,255,255,0.05))",
  color: "var(--era-text, #fff)",
  borderRadius: 14,
  padding: "0.75rem 0.9rem",
  fontWeight: 800,
  cursor: "pointer",
});

function formatDate(value: string | null): string {
  if (!value) return "Без даты";
  const date = new Date(value);
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function openExternal(url: string): void {
  if (!url) return;
  window.open(url, "_blank", "noopener,noreferrer");
}

function TaskList({ tasks, empty }: { tasks: MediaTask[]; empty: string }) {
  if (!tasks.length) return <p style={{ margin: 0, color: "var(--era-text-muted)" }}>{empty}</p>;
  return (
    <div style={{ display: "grid", gap: "0.65rem" }}>
      {tasks.map((task) => (
        <button
          key={task.id}
          type="button"
          onClick={() => { window.location.hash = `#/tasks/${task.id}`; }}
          style={{ ...buttonStyle(false), textAlign: "left", padding: "0.9rem" }}
        >
          <span style={{ display: "block", fontSize: "0.98rem" }}>{task.title}</span>
          <span style={{ display: "block", marginTop: 5, color: "var(--era-text-muted)", fontSize: "0.8rem", fontWeight: 600 }}>
            до {formatDate(task.deadline)} · +{task.points} баллов
          </span>
        </button>
      ))}
    </div>
  );
}

function ContentCard({
  item,
  manager,
  onChanged,
}: {
  item: MediaContent;
  manager: boolean;
  onChanged: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const action = async (kind: "publish" | "skip" | "tasks") => {
    setBusy(true);
    setMessage(null);
    try {
      if (kind === "publish") {
        const result = await publishMediaContentNow(item.id);
        setMessage(result.ok ? "Опубликовано" : result.code);
      } else if (kind === "skip") {
        await skipMediaContent(item.id);
        setMessage("Пропущено");
      } else {
        await createMediaTasks(item.id, item.kind === "poll" ? ["text", "design"] : ["text", "design"]);
        setMessage("Задачи созданы");
      }
      await onChanged();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Не удалось выполнить действие");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card style={{ display: "grid", gap: "0.65rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start" }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontWeight: 900 }}>{item.rubric || item.theme || "Контент ЭРА"}</div>
          <div style={{ color: "var(--era-text-muted)", fontSize: "0.8rem", marginTop: 4 }}>
            {formatDate(item.scheduled_at)} · {item.kind === "poll" ? "Опрос" : "Публикация"}
          </div>
        </div>
        <span style={{ fontSize: "0.72rem", fontWeight: 900, opacity: 0.72, textTransform: "uppercase" }}>{item.status}</span>
      </div>
      <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.5, fontSize: "0.91rem" }}>
        {item.kind === "poll" ? item.poll_question : item.body}
      </div>
      {item.kind === "poll" && item.poll_options.length > 0 ? (
        <div style={{ display: "grid", gap: 5 }}>
          {item.poll_options.map((option) => <div key={option} style={{ color: "var(--era-text-muted)", fontSize: "0.82rem" }}>• {option}</div>)}
        </div>
      ) : null}
      {manager && item.status !== "published" && item.status !== "skipped" ? (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          <button disabled={busy} type="button" onClick={() => void action("tasks")} style={buttonStyle(false)}>Разложить на задачи</button>
          <button disabled={busy} type="button" onClick={() => void action("publish")} style={buttonStyle(true)}>Опубликовать сейчас</button>
          <button disabled={busy} type="button" onClick={() => void action("skip")} style={buttonStyle(false)}>Пропустить</button>
        </div>
      ) : null}
      {message ? <div style={{ color: "var(--era-text-muted)", fontSize: "0.8rem" }}>{message}</div> : null}
    </Card>
  );
}

export function MediaScreen({ onBack }: MediaScreenProps) {
  const [hub, setHub] = useState<MediaHub | null>(null);
  const [library, setLibrary] = useState<MediaLibraryItem[]>([]);
  const [today, setToday] = useState<MediaContent[]>([]);
  const [plan, setPlan] = useState<MediaContent[]>([]);
  const [config, setConfig] = useState<MediaConfig | null>(null);
  const [analytics, setAnalytics] = useState<MediaAnalytics | null>(null);
  const [channelHealth, setChannelHealth] = useState<{ ok: boolean; detail: string } | null>(null);
  const [idea, setIdea] = useState("");
  const [ideaStatus, setIdeaStatus] = useState<string | null>(null);
  const [view, setView] = useState<DeskView>("home");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const loadHub = useCallback(async () => {
    const [hubResult, libraryResult] = await Promise.all([fetchMediaHub(), fetchMediaLibrary()]);
    setHub(hubResult);
    setLibrary(libraryResult);
    return hubResult;
  }, []);

  const loadDesk = useCallback(async () => {
    const [todayResult, planResult, configResult, analyticsResult, healthResult] = await Promise.all([
      fetchMediaToday(),
      fetchMediaContentPlan(),
      fetchMediaConfig(),
      fetchMediaAnalytics(),
      fetchMediaChannelHealth(),
    ]);
    setToday(todayResult);
    setPlan(planResult);
    setConfig(configResult);
    setAnalytics(analyticsResult);
    setChannelHealth(healthResult);
  }, []);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const nextHub = await loadHub();
      if (nextHub.can_manage) await loadDesk();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось открыть Медиа");
    } finally {
      setLoading(false);
    }
  }, [loadDesk, loadHub]);

  useEffect(() => { void refresh(); }, [refresh]);

  const files = useMemo(() => library.filter((item) => item.kind !== "chat" && item.kind !== "channel"), [library]);

  const submitIdea = async () => {
    const text = idea.trim();
    if (text.length < 10) {
      setIdeaStatus("Опиши идею чуть подробнее — минимум 10 символов.");
      return;
    }
    setBusy(true);
    setIdeaStatus(null);
    try {
      await submitMediaIdea(text);
      setIdea("");
      setIdeaStatus("Идея попала в Media Desk.");
    } catch (cause) {
      setIdeaStatus(cause instanceof Error ? cause.message : "Не удалось отправить идею");
    } finally {
      setBusy(false);
    }
  };

  const updateConfig = async (action: "auto" | "pause" | "resume") => {
    setBusy(true);
    setError(null);
    try {
      const result = action === "auto"
        ? await setMediaAuto(!config?.auto_enabled)
        : action === "pause"
          ? await pauseMedia(true)
          : await resumeMedia();
      setConfig(result);
      if (hub?.can_manage) setChannelHealth(await fetchMediaChannelHealth());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось изменить настройку");
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <div className="era-page" style={{ padding: "1.25rem" }}>Загружаем Media Hub…</div>;
  if (!hub) return <div className="era-page" style={{ padding: "1.25rem" }}>{error || "Media Hub недоступен"}</div>;

  const header = (
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      {(view !== "home" || onBack) ? (
        <button
          type="button"
          onClick={() => view !== "home" ? setView("home") : onBack?.()}
          style={{ ...buttonStyle(false), padding: "0.55rem 0.7rem" }}
          aria-label="Назад"
        >←</button>
      ) : null}
      <div>
        <div style={{ fontSize: "0.72rem", color: "var(--era-text-muted)", fontWeight: 900, textTransform: "uppercase" }}>ЭРА · Медиа</div>
        <h1 style={{ margin: "0.15rem 0 0", fontSize: "var(--era-text-3xl)", lineHeight: 1.05 }}>
          {view === "home" ? "Media Hub" : view === "today" ? "Сегодня" : view === "plan" ? "Контент-план" : view === "tasks" ? "Задачи" : view === "team" ? "Команда" : view === "chat" ? "Media Chat" : view === "channel" ? "Канал" : view === "files" ? "Файлы" : view === "analytics" ? "Аналитика" : "Настройки"}
        </h1>
      </div>
    </div>
  );

  let body: React.ReactNode;
  if (view === "today") {
    body = <div style={{ display: "grid", gap: 10 }}>{today.length ? today.map((item) => <ContentCard key={item.id} item={item} manager onChanged={loadDesk} />) : <Card>На сегодня публикаций нет.</Card>}</div>;
  } else if (view === "plan") {
    body = <div style={{ display: "grid", gap: 10 }}>{plan.map((item) => <ContentCard key={item.id} item={item} manager onChanged={loadDesk} />)}</div>;
  } else if (view === "tasks") {
    body = <Card style={{ display: "grid", gap: 12 }}><strong>Открытые медиа-задачи</strong><TaskList tasks={hub.open_tasks} empty="Все задачи уже разобраны." /><strong style={{ marginTop: 8 }}>Мои задачи</strong><TaskList tasks={hub.my_tasks} empty="У тебя пока нет взятых медиа-задач." /></Card>;
  } else if (view === "team") {
    body = (
      <Card style={{ display: "grid", gap: 10 }}>
        <strong>Команда формируется через реальные задачи</strong>
        <p style={{ margin: 0, color: "var(--era-text-muted)", lineHeight: 1.5 }}>
          Кто берёт медиа-задачу, автоматически попадает в рабочий поток. Выполненные материалы остаются в истории задач и учитываются в прогрессе Медиа.
        </p>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          <Card><div style={{ fontSize: 24, fontWeight: 900 }}>{hub.my_tasks.length}</div><div style={{ color: "var(--era-text-muted)", fontSize: 12 }}>моих активных</div></Card>
          <Card><div style={{ fontSize: 24, fontWeight: 900 }}>{hub.open_tasks.length}</div><div style={{ color: "var(--era-text-muted)", fontSize: 12 }}>свободных</div></Card>
        </div>
      </Card>
    );
  } else if (view === "chat") {
    body = <ActionCell title="Открыть Media Chat" description="Координация, задачи и материалы команды" leading={<span>💬</span>} onClick={() => openExternal(hub.chat_url)} />;
  } else if (view === "channel") {
    body = (
      <div style={{ display: "grid", gap: 10 }}>
        <Card>
          <div style={{ fontWeight: 900 }}>Состояние канала</div>
          <div style={{ marginTop: 5, color: channelHealth?.ok ? "#42d392" : "var(--era-text-muted)" }}>
            {channelHealth?.ok ? "Готов к публикации" : `Нужна настройка: ${channelHealth?.detail || "не проверено"}`}
          </div>
        </Card>
        <ActionCell title="Открыть @era_leaders1" description="Публичный канал ЭРА" leading={<span>↗</span>} onClick={() => openExternal(hub.channel_url)} />
      </div>
    );
  } else if (view === "files") {
    body = <div style={{ display: "grid", gap: 10 }}>{files.map((item) => <ActionCell key={item.id} title={item.title} description={item.description || item.kind} leading={<span>◫</span>} onClick={() => openExternal(item.url)} />)}</div>;
  } else if (view === "analytics") {
    body = analytics ? (
      <div style={{ display: "grid", gap: 10 }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          <Card><div style={{ fontSize: 28, fontWeight: 950 }}>{analytics.published}</div><div style={{ color: "var(--era-text-muted)", fontSize: 12 }}>опубликовано</div></Card>
          <Card><div style={{ fontSize: 28, fontWeight: 950 }}>{analytics.planned}</div><div style={{ color: "var(--era-text-muted)", fontSize: 12 }}>в плане</div></Card>
          <Card><div style={{ fontSize: 28, fontWeight: 950 }}>{analytics.tasks_completed}/{analytics.tasks_created}</div><div style={{ color: "var(--era-text-muted)", fontSize: 12 }}>задач выполнено</div></Card>
          <Card><div style={{ fontSize: 28, fontWeight: 950 }}>{analytics.on_time_rate == null ? "—" : `${analytics.on_time_rate}%`}</div><div style={{ color: "var(--era-text-muted)", fontSize: 12 }}>в срок</div></Card>
        </div>
        {analytics.failed > 0 ? <Card><strong>Требуют внимания: {analytics.failed}</strong><div style={{ color: "var(--era-text-muted)", marginTop: 5 }}>Система не делает слепой повтор, чтобы не создать дубль публикации.</div></Card> : null}
      </div>
    ) : <Card>Аналитика пока пуста.</Card>;
  } else if (view === "settings") {
    body = (
      <div style={{ display: "grid", gap: 10 }}>
        <Card style={{ display: "grid", gap: 10 }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}>
            <div><strong>AUTO</strong><div style={{ color: "var(--era-text-muted)", fontSize: 12, marginTop: 3 }}>Только утверждённый 26-недельный пакет</div></div>
            <span style={{ fontWeight: 900 }}>{config?.auto_enabled ? "ON" : "OFF"}</span>
          </div>
          <button disabled={busy} type="button" style={buttonStyle(Boolean(!config?.auto_enabled))} onClick={() => void updateConfig("auto")}>{config?.auto_enabled ? "Выключить AUTO" : "Включить AUTO"}</button>
        </Card>
        <Card style={{ display: "grid", gap: 10 }}>
          <strong>Пауза публикаций</strong>
          <div style={{ color: "var(--era-text-muted)", fontSize: 12 }}>{config?.paused_indefinitely ? "Публикации остановлены" : config?.paused_until ? `Пауза до ${formatDate(config.paused_until)}` : "Паузы нет"}</div>
          {config?.paused_indefinitely || config?.paused_until ? <button disabled={busy} type="button" style={buttonStyle(true)} onClick={() => void updateConfig("resume")}>Продолжить</button> : <button disabled={busy} type="button" style={buttonStyle(false)} onClick={() => void updateConfig("pause")}>Поставить на паузу</button>}
        </Card>
        <Card><strong>Защита от дублей включена</strong><div style={{ color: "var(--era-text-muted)", marginTop: 5, fontSize: 12, lineHeight: 1.5 }}>Перед отправкой создаётся durable delivery claim. При неоднозначной ошибке AUTO не публикует повторно без решения человека.</div></Card>
      </div>
    );
  } else {
    body = (
      <>
        <Card gradient style={{ position: "relative", overflow: "hidden", minHeight: 178 }}>
          <div style={{ position: "relative", display: "grid", gap: 12 }}>
            <div style={{ width: 48, height: 48, borderRadius: 16, display: "grid", placeItems: "center", background: "rgba(255,255,255,0.14)", fontSize: 24 }}>◉</div>
            <div>
              <div style={{ fontSize: "0.72rem", textTransform: "uppercase", fontWeight: 900, color: "rgba(255,255,255,0.65)" }}>Не наблюдай — делай</div>
              <h2 style={{ margin: "0.2rem 0 0", fontSize: "var(--era-text-3xl)" }}>Медиа — точка входа в реальный проект</h2>
              <p style={{ margin: "0.55rem 0 0", color: "rgba(255,255,255,0.78)", lineHeight: 1.45 }}>Возьми задачу, сделай материал, попади в команду и собери портфолио внутри ЭРА.</p>
            </div>
          </div>
        </Card>

        <Card style={{ display: "grid", gap: 12 }}>
          <div><strong>Открытые задачи</strong><div style={{ color: "var(--era-text-muted)", fontSize: 12, marginTop: 3 }}>Можно взять сразу — без отдельной заявки.</div></div>
          <TaskList tasks={hub.open_tasks.slice(0, 5)} empty="Сейчас свободных задач нет." />
          {hub.open_tasks.length > 5 ? <button type="button" style={buttonStyle(false)} onClick={() => setView("tasks")}>Все задачи</button> : null}
        </Card>

        {hub.my_tasks.length ? <Card style={{ display: "grid", gap: 12 }}><strong>Мои медиа-задачи</strong><TaskList tasks={hub.my_tasks.slice(0, 4)} empty="" /></Card> : null}

        <Card style={{ display: "grid", gap: 9 }}>
          <strong>Есть идея?</strong>
          <textarea value={idea} onChange={(event) => setIdea(event.target.value)} placeholder="Что можно снять, рассказать или попробовать?" rows={4} style={{ width: "100%", resize: "vertical", boxSizing: "border-box", borderRadius: 14, border: "1px solid var(--era-border)", background: "var(--era-surface-2, rgba(255,255,255,0.04))", color: "var(--era-text)", padding: "0.8rem", font: "inherit" }} />
          <button disabled={busy} type="button" onClick={() => void submitIdea()} style={buttonStyle(true)}>Отправить в Media Desk</button>
          {ideaStatus ? <div style={{ color: "var(--era-text-muted)", fontSize: 12 }}>{ideaStatus}</div> : null}
        </Card>

        <div style={{ display: "grid", gap: 10 }}>
          <ActionCell title="Media Chat" description="Рабочая координация и команда" leading={<span>💬</span>} onClick={() => openExternal(hub.chat_url)} />
          <ActionCell title="Канал ЭРА" description="Смотри, что выходит в публичное пространство" leading={<span>↗</span>} onClick={() => openExternal(hub.channel_url)} />
          <ActionCell title="Шаблоны и файлы" description="Canva, гайды и рабочие материалы" leading={<span>◫</span>} onClick={() => setView("files")} />
        </div>

        {hub.can_manage ? (
          <Card style={{ display: "grid", gap: 10 }}>
            <div><div style={{ fontSize: "0.72rem", textTransform: "uppercase", fontWeight: 900, color: "var(--era-text-muted)" }}>Управление</div><h2 style={{ margin: "0.2rem 0 0" }}>Media Desk</h2></div>
            {([
              ["today", "Сегодня", "Что выходит и что должно быть готово", "●"],
              ["plan", "Контент-план", "26 недель + ручные публикации", "▦"],
              ["tasks", "Задачи", "Свободные и взятые материалы", "✓"],
              ["team", "Команда", "Рабочий поток через задачи", "◎"],
              ["chat", "Чат", "Media Chat", "💬"],
              ["channel", "Канал", "Права бота и @era_leaders1", "↗"],
              ["files", "Файлы", "Шаблоны и гайды", "◫"],
              ["analytics", "Аналитика", "Публикации, сроки, выполнение", "↗"],
              ["settings", "Настройки", "AUTO, пауза и безопасность", "⚙"],
            ] as const).map(([key, title, description, icon]) => (
              <ActionCell key={key} title={title} description={description} leading={<span>{icon}</span>} onClick={() => setView(key)} />
            ))}
          </Card>
        ) : null}
      </>
    );
  }

  return (
    <div className="era-page" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem", minWidth: 0 }}>
      {header}
      {error ? <Card><strong>Нужно внимание</strong><div style={{ color: "var(--era-text-muted)", marginTop: 5 }}>{error}</div></Card> : null}
      {body}
    </div>
  );
}
