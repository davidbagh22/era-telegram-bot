import { useCallback, useEffect, useMemo, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import {
  createAutoContentHoliday,
  fetchAutoContentCalendar,
  fetchAutoContentHistory,
  fetchAutoContentOverview,
  patchAutoContentItem,
  patchAutoContentSettings,
  previewAutoContent,
  sendAutoContentItemNow,
  skipAutoContentItem,
} from "../../../api/autocontent";
import { describeActionError } from "../../../api/client";
import { Card } from "../../../components/Card";
import { StatusBadge } from "../../../components/StatusBadge";
import type {
  AutoContentCalendarEntry,
  AutoContentHistoryEntry,
  AutoContentOverview,
  AutoContentPlannedItem,
  AutoContentSettings,
} from "../../../types/autocontent";

const inputStyle = {
  width: "100%",
  fontFamily: "var(--era-font-body)",
  padding: "0.625rem 0.75rem",
  borderRadius: "0.75rem",
  border: "1px solid var(--era-border)",
  background: "var(--era-bg)",
  color: "var(--era-text)",
  boxSizing: "border-box",
} satisfies CSSProperties;

const subtleButtonStyle = {
  minHeight: "2.25rem",
  padding: "0.45rem 0.7rem",
  borderRadius: "0.65rem",
  border: "1px solid var(--era-border)",
  background: "var(--era-surface)",
  color: "var(--era-text)",
} satisfies CSSProperties;

const TYPE_LABELS: Record<string, string> = {
  morning_quote: "Утренняя мысль",
  evening_quote: "Вечерняя мысль",
  weekly_challenge: "Вызов недели",
  monthly_theme: "Тема месяца",
  holiday: "Особая дата",
};

const STATUS_LABELS: Record<string, string> = {
  planned: "Запланировано",
  sent: "Отправлено",
  claimed: "Готовится",
  sending: "Отправляется",
  in_progress: "В процессе",
  retryable_failed: "Повторим",
  failed: "Ошибка",
  skipped_late: "Пропущено: поздно",
  missed: "Пропущено",
  skipped_admin: "Пропущено админом",
  disabled: "Отключено",
  no_content: "Нет сообщения",
};

function statusTone(status: string): "violet" | "red" | undefined {
  if (status === "sent") return "violet";
  if (status === "failed" || status === "missed") return "red";
  return undefined;
}

function dayLabel(value: string): string {
  const [year, month, day] = value.split("-").map(Number);
  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "long",
    weekday: "short",
  }).format(new Date(year, month - 1, day));
}

function timeLabel(slot: "morning" | "evening"): string {
  return slot === "morning" ? "09:00" : "18:00";
}

function TelegramPreviewText({ text }: { text: string }) {
  const parts = text.split(/(<b>[\s\S]*?<\/b>)/g).filter(Boolean);
  return (
    <div
      style={{
        whiteSpace: "pre-wrap",
        lineHeight: 1.45,
        borderRadius: "0.85rem",
        padding: "0.85rem",
        background: "var(--era-bg)",
        border: "1px solid var(--era-border)",
      }}
    >
      {parts.map((part, index) =>
        part.startsWith("<b>") && part.endsWith("</b>") ? (
          <strong key={`${index}-${part.slice(0, 12)}`}>{part.slice(3, -4)}</strong>
        ) : (
          <span key={`${index}-${part.slice(0, 12)}`}>{part}</span>
        ),
      )}
    </div>
  );
}

function SectionTitle({ children, hint }: { children: ReactNode; hint?: string }) {
  return (
    <div>
      <h3 style={{ margin: 0, fontSize: "var(--era-text-lg)" }}>{children}</h3>
      {hint ? (
        <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
          {hint}
        </p>
      ) : null}
    </div>
  );
}

function MessageEditor({
  item,
  onChanged,
}: {
  item: AutoContentPlannedItem;
  onChanged: () => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(item.effective_text);
  const [previewing, setPreviewing] = useState(false);
  const [previewMeta, setPreviewMeta] = useState<{ characters: number; lines: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);

  useEffect(() => {
    setText(item.effective_text);
    setEditing(false);
    setPreviewing(false);
    setPreviewMeta(null);
  }, [item.content_id, item.effective_text]);

  const act = useCallback(
    async (action: () => Promise<unknown>, success: string) => {
      setBusy(true);
      setError(null);
      setResult(null);
      try {
        await action();
        setResult(success);
        await onChanged();
      } catch (err) {
        setError(describeActionError(err));
      } finally {
        setBusy(false);
      }
    },
    [onChanged],
  );

  const handlePreview = async () => {
    setError(null);
    try {
      const data = await previewAutoContent(text.trim());
      setPreviewMeta({ characters: data.characters, lines: data.lines });
      setPreviewing(true);
    } catch (err) {
      setError(describeActionError(err));
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.55rem" }}>
      {error ? <p style={{ margin: 0, color: "var(--era-error)", fontSize: "0.8125rem" }}>{error}</p> : null}
      {result ? <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>{result}</p> : null}
      {editing ? (
        <>
          <textarea value={text} onChange={(event) => setText(event.target.value)} rows={7} style={inputStyle} />
          <div style={{ display: "flex", gap: "0.45rem", flexWrap: "wrap" }}>
            <button
              type="button"
              className="era-btn-primary"
              disabled={busy || !text.trim()}
              onClick={() => void act(
                () => patchAutoContentItem(item.content_id, { text: text.trim(), is_enabled: true, is_skipped: false }),
                "Текст сохранён",
              )}
            >
              Сохранить
            </button>
            <button type="button" style={subtleButtonStyle} disabled={!text.trim()} onClick={() => void handlePreview()}>
              Предпросмотр в Telegram
            </button>
            <button type="button" style={subtleButtonStyle} onClick={() => setEditing(false)}>
              Отмена
            </button>
          </div>
        </>
      ) : (
        <>
          <p style={{ margin: 0, whiteSpace: "pre-wrap", lineHeight: 1.45 }}>{item.effective_text}</p>
          <div style={{ display: "flex", gap: "0.45rem", flexWrap: "wrap" }}>
            <button type="button" style={subtleButtonStyle} onClick={() => setEditing(true)}>
              Изменить текст
            </button>
            <button type="button" style={subtleButtonStyle} onClick={() => void handlePreview()}>
              Предпросмотр
            </button>
            <button
              type="button"
              style={subtleButtonStyle}
              disabled={busy}
              onClick={() => void act(() => skipAutoContentItem(item.content_id), "Сообщение пропущено")}
            >
              Пропустить
            </button>
            <button
              type="button"
              style={subtleButtonStyle}
              disabled={busy}
              onClick={() => void act(
                () => patchAutoContentItem(item.content_id, { is_enabled: false }),
                "Сообщение отключено",
              )}
            >
              Отключить
            </button>
            <button
              type="button"
              className="era-btn-primary"
              disabled={busy}
              onClick={() => {
                if (window.confirm("Отправить это сообщение в общий чат ЭРА прямо сейчас?")) {
                  void act(() => sendAutoContentItemNow(item.content_id), "Сообщение отправлено");
                }
              }}
            >
              Отправить сейчас
            </button>
          </div>
        </>
      )}
      {previewing ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.45rem" }}>
          <div style={{ display: "flex", gap: "0.35rem", flexWrap: "wrap" }}>
            <StatusBadge label="Telegram · HTML" tone="violet" />
            {previewMeta ? <StatusBadge label={`${previewMeta.characters} символов · ${previewMeta.lines} строк`} /> : null}
          </div>
          <TelegramPreviewText text={text} />
          <button type="button" style={{ ...subtleButtonStyle, alignSelf: "flex-start" }} onClick={() => setPreviewing(false)}>
            Закрыть предпросмотр
          </button>
        </div>
      ) : null}
    </div>
  );
}

function ScheduleCard({
  entry,
  onChanged,
}: {
  entry: AutoContentCalendarEntry;
  onChanged: () => Promise<void>;
}) {
  return (
    <Card>
      <div style={{ display: "flex", justifyContent: "space-between", gap: "0.65rem", alignItems: "flex-start" }}>
        <div>
          <strong>{timeLabel(entry.slot)}</strong>
          <p style={{ margin: "0.2rem 0 0", color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
            {entry.planned ? TYPE_LABELS[entry.planned.content_type] ?? entry.planned.content_type : "Нет активного сообщения"}
          </p>
        </div>
        <StatusBadge label={STATUS_LABELS[entry.status] ?? entry.status} tone={statusTone(entry.status)} />
      </div>
      {entry.error_code ? (
        <p style={{ margin: "0.5rem 0 0", color: "var(--era-error)", fontSize: "0.8125rem" }}>
          Ошибка: {entry.error_code}
        </p>
      ) : null}
      {entry.planned ? (
        <div style={{ marginTop: "0.7rem" }}>
          <MessageEditor item={entry.planned} onChanged={onChanged} />
        </div>
      ) : null}
    </Card>
  );
}

export function AutoContentPanel() {
  const [overview, setOverview] = useState<AutoContentOverview | null>(null);
  const [calendar, setCalendar] = useState<AutoContentCalendarEntry[] | null>(null);
  const [history, setHistory] = useState<AutoContentHistoryEntry[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [busySetting, setBusySetting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newHoliday, setNewHoliday] = useState({ date_key: "", title: "", text: "" });
  const [addingHoliday, setAddingHoliday] = useState(false);

  const loadOverview = useCallback(async () => {
    setError(null);
    try {
      const data = await fetchAutoContentOverview();
      setOverview(data);
    } catch (err) {
      setError(describeActionError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadOverview();
  }, [loadOverview]);

  const dates = useMemo(() => {
    if (!overview) return [];
    return Array.from(new Set(overview.items.map((item) => item.date)));
  }, [overview]);

  const updateSetting = async (key: keyof AutoContentSettings, value: boolean) => {
    setBusySetting(key);
    setError(null);
    try {
      await patchAutoContentSettings({ [key]: value });
      await loadOverview();
      if (calendar) {
        const start = calendar[0]?.date ?? new Date().toISOString().slice(0, 10);
        setCalendar(await fetchAutoContentCalendar(start, 31));
      }
    } catch (err) {
      setError(describeActionError(err));
    } finally {
      setBusySetting(null);
    }
  };

  const loadCalendar = async () => {
    const start = overview?.items[0]?.date ?? new Date().toISOString().slice(0, 10);
    setError(null);
    try {
      setCalendar(await fetchAutoContentCalendar(start, 31));
    } catch (err) {
      setError(describeActionError(err));
    }
  };

  const loadHistory = async () => {
    setError(null);
    try {
      setHistory(await fetchAutoContentHistory(100));
    } catch (err) {
      setError(describeActionError(err));
    }
  };

  const refreshAll = useCallback(async () => {
    await loadOverview();
    if (calendar) await loadCalendar();
    if (history) await loadHistory();
  // loadCalendar/loadHistory intentionally depend on current display state.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadOverview, calendar !== null, history !== null]);

  const handleAddHoliday = async () => {
    setAddingHoliday(true);
    setError(null);
    try {
      await createAutoContentHoliday({
        date_key: newHoliday.date_key.trim(),
        title: newHoliday.title.trim(),
        text: newHoliday.text.trim(),
      });
      setNewHoliday({ date_key: "", title: "", text: "" });
      await refreshAll();
    } catch (err) {
      setError(describeActionError(err));
    } finally {
      setAddingHoliday(false);
    }
  };

  if (loading) {
    return <p style={{ color: "var(--era-text-muted)" }}>Загружаем автоконтент…</p>;
  }

  if (!overview) {
    return (
      <Card>
        <strong>Не удалось открыть автоконтент</strong>
        <p style={{ color: "var(--era-text-muted)" }}>{error ?? "Попробуйте ещё раз."}</p>
        <button type="button" className="era-btn-primary" onClick={() => void loadOverview()}>
          Повторить
        </button>
      </Card>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem", minWidth: 0 }}>
      {error ? (
        <Card>
          <p style={{ margin: 0, color: "var(--era-error)" }}>{error}</p>
        </Card>
      ) : null}

      <Card>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "center" }}>
          <div>
            <strong>Ритм общего чата</strong>
            <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
              09:00 и 18:00 · {overview.timezone}. Не более двух сообщений в сутки.
            </p>
          </div>
          <button
            type="button"
            className={overview.settings.paused ? "era-btn-primary" : undefined}
            style={overview.settings.paused ? undefined : subtleButtonStyle}
            disabled={busySetting === "paused"}
            onClick={() => void updateSetting("paused", !overview.settings.paused)}
          >
            {overview.settings.paused ? "Возобновить" : "Пауза"}
          </button>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.5rem", marginTop: "0.75rem" }}>
          {([
            ["quotes", "Цитаты"],
            ["challenges", "Вызовы"],
            ["themes", "Темы месяца"],
            ["holidays", "Праздники"],
          ] as const).map(([key, label]) => (
            <label
              key={key}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.45rem",
                padding: "0.6rem",
                border: "1px solid var(--era-border)",
                borderRadius: "0.75rem",
              }}
            >
              <input
                type="checkbox"
                checked={overview.settings[key]}
                disabled={busySetting !== null}
                onChange={(event) => void updateSetting(key, event.target.checked)}
              />
              <span style={{ fontSize: "0.875rem" }}>{label}</span>
            </label>
          ))}
        </div>
      </Card>

      {dates.map((dateValue, dateIndex) => (
        <section key={dateValue} style={{ display: "flex", flexDirection: "column", gap: "0.55rem" }}>
          <SectionTitle hint={dateIndex === 0 ? "Текущий редакционный день" : "Предпросмотр следующего дня"}>
            {dateIndex === 0 ? "Сегодня" : "Завтра"} · {dayLabel(dateValue)}
          </SectionTitle>
          {overview.items
            .filter((item) => item.date === dateValue)
            .map((entry) => (
              <ScheduleCard key={`${entry.date}-${entry.slot}`} entry={entry} onChanged={refreshAll} />
            ))}
        </section>
      ))}

      <section style={{ display: "flex", flexDirection: "column", gap: "0.55rem" }}>
        <SectionTitle hint="Дополнительные даты сохраняются в базе и не исчезают после deploy.">Особые даты</SectionTitle>
        {overview.custom_holidays.map((holiday) => (
          <Card key={holiday.content_id}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem" }}>
              <div>
                <strong>{holiday.title ?? "Особая дата"}</strong>
                <p style={{ margin: "0.2rem 0 0", color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
                  {holiday.date_key} · {holiday.is_skipped ? "пропущено" : holiday.is_enabled ? "активно" : "отключено"}
                </p>
              </div>
              <button
                type="button"
                style={subtleButtonStyle}
                onClick={() => void patchAutoContentItem(holiday.content_id, {
                  is_enabled: !holiday.is_enabled,
                  is_skipped: false,
                }).then(refreshAll).catch((err) => setError(describeActionError(err)))}
              >
                {holiday.is_enabled ? "Отключить" : "Включить"}
              </button>
            </div>
            <p style={{ whiteSpace: "pre-wrap", marginBottom: 0 }}>{holiday.text}</p>
          </Card>
        ))}
        <Card>
          <strong>Добавить дату</strong>
          <p style={{ margin: "0.25rem 0 0.65rem", color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
            Формат MM-DD для ежегодной даты или YYYY-MM-DD для одного конкретного года.
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <input
              value={newHoliday.date_key}
              onChange={(event) => setNewHoliday((current) => ({ ...current, date_key: event.target.value }))}
              placeholder="08-30 или 2027-08-30"
              style={inputStyle}
            />
            <input
              value={newHoliday.title}
              onChange={(event) => setNewHoliday((current) => ({ ...current, title: event.target.value }))}
              placeholder="Название даты"
              style={inputStyle}
            />
            <textarea
              value={newHoliday.text}
              onChange={(event) => setNewHoliday((current) => ({ ...current, text: event.target.value }))}
              placeholder="Текст сообщения"
              rows={5}
              style={inputStyle}
            />
            <button
              type="button"
              className="era-btn-primary"
              disabled={addingHoliday || !newHoliday.date_key.trim() || !newHoliday.title.trim() || !newHoliday.text.trim()}
              onClick={() => void handleAddHoliday()}
            >
              Добавить в календарь
            </button>
          </div>
        </Card>
      </section>

      <section style={{ display: "flex", flexDirection: "column", gap: "0.55rem" }}>
        <SectionTitle hint="Показывает фактический тип сообщения после всех приоритетов и замен.">Календарь</SectionTitle>
        {calendar ? (
          <>
            {Array.from(new Set(calendar.map((item) => item.date))).map((dateValue) => (
              <Card key={dateValue}>
                <strong>{dayLabel(dateValue)}</strong>
                <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem", marginTop: "0.55rem" }}>
                  {calendar.filter((item) => item.date === dateValue).map((entry) => (
                    <div key={`${entry.date}-${entry.slot}`} style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem" }}>
                      <span style={{ fontSize: "0.875rem" }}>
                        {timeLabel(entry.slot)} · {entry.planned ? TYPE_LABELS[entry.planned.content_type] : "—"}
                      </span>
                      <span style={{ color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
                        {STATUS_LABELS[entry.status] ?? entry.status}
                      </span>
                    </div>
                  ))}
                </div>
              </Card>
            ))}
            <button type="button" style={{ ...subtleButtonStyle, alignSelf: "flex-start" }} onClick={() => setCalendar(null)}>
              Свернуть календарь
            </button>
          </>
        ) : (
          <button type="button" style={{ ...subtleButtonStyle, alignSelf: "flex-start" }} onClick={() => void loadCalendar()}>
            Показать 31 день
          </button>
        )}
      </section>

      <section style={{ display: "flex", flexDirection: "column", gap: "0.55rem" }}>
        <SectionTitle hint="Ручные и автоматические отправки, пропуски и ошибки доставки.">История и ошибки</SectionTitle>
        {history ? (
          <>
            {history.length === 0 ? <Card>История пока пуста.</Card> : null}
            {history.map((entry) => (
              <Card key={entry.id}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: "0.65rem" }}>
                  <div>
                    <strong>{TYPE_LABELS[entry.content_type] ?? entry.content_type}</strong>
                    <p style={{ margin: "0.2rem 0 0", color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
                      {new Date(entry.planned_at).toLocaleString("ru-RU")} · попыток: {entry.attempts}
                      {entry.is_manual ? " · вручную" : ""}
                    </p>
                  </div>
                  <StatusBadge label={STATUS_LABELS[entry.status] ?? entry.status} tone={statusTone(entry.status)} />
                </div>
                {entry.error_code ? (
                  <p style={{ margin: "0.5rem 0 0", color: "var(--era-error)", fontSize: "0.8125rem" }}>
                    {entry.error_code}
                  </p>
                ) : null}
              </Card>
            ))}
            <button type="button" style={{ ...subtleButtonStyle, alignSelf: "flex-start" }} onClick={() => setHistory(null)}>
              Свернуть историю
            </button>
          </>
        ) : (
          <button type="button" style={{ ...subtleButtonStyle, alignSelf: "flex-start" }} onClick={() => void loadHistory()}>
            Показать историю
          </button>
        )}
      </section>
    </div>
  );
}
