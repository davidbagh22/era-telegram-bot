import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  describeActionError,
  fetchEventParticipants,
} from "../../../api/client";
import { downloadEventParticipants, fetchEventShareText } from "../../../api/adminEvents";
import { Card } from "../../../components/Card";
import { EmptyState } from "../../../components/EmptyState";
import { StatusBadge } from "../../../components/StatusBadge";
import { useAsync } from "../../../hooks/useAsync";
import { RegistrantMessagePanel } from "./RegistrantMessagePanel";
import { EventDetailsEditor } from "./EventDetailsEditor";
import { EventPosterEditor } from "./EventPosterEditor";
import { EventLifecyclePanel } from "./EventLifecyclePanel";

const STATUS_LABELS: Record<string, string> = {
  registered: "Ждёт подтверждения",
  will_come: "Ждёт подтверждения",
  waitlist: "Лист ожидания",
  not_coming: "Отказался",
  attended: "Посещение подтверждено",
  no_show: "Не пришёл",
  cancelled: "Регистрация отменена",
};

const FILTERS = [
  { value: "all", label: "Все статусы" },
  { value: "active", label: "Зарегистрированы" },
  { value: "attended", label: "Подтвердили" },
  { value: "cancelled", label: "Отказались" },
  { value: "no_show", label: "Не пришли" },
  { value: "waitlist", label: "Лист ожидания" },
] as const;

type FilterValue = typeof FILTERS[number]["value"];

const GROUP_CHIPS: { value: FilterValue; label: string }[] = [
  { value: "all", label: "Все" },
  { value: "active", label: "Регистрации" },
  { value: "waitlist", label: "Лист ожидания" },
  { value: "attended", label: "Посетили" },
];

interface EventParticipantsPanelProps {
  eventId: number;
  onBack: () => void;
  /** Opened from «Участники · N»: scroll straight to the list. */
  focusParticipants?: boolean;
}

function formatRegisteredAt(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function matchesFilter(status: string, filter: FilterValue): boolean {
  if (filter === "all") return true;
  if (filter === "active") return ["registered", "will_come"].includes(status);
  if (filter === "cancelled") return ["not_coming", "cancelled"].includes(status);
  return status === filter;
}

export function EventParticipantsPanel({ eventId, onBack, focusParticipants = false }: EventParticipantsPanelProps) {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchEventParticipants(eventId), [eventId, refreshKey]);
  const [exporting, setExporting] = useState<"xlsx" | "csv" | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [editor, setEditor] = useState<"details" | "poster" | null>(null);
  const [shareBusy, setShareBusy] = useState(false);
  const [shareText, setShareText] = useState<string | null>(null);
  const [shareStatus, setShareStatus] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<FilterValue>("all");

  const listRef = useRef<HTMLDivElement | null>(null);
  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);
  useEffect(() => {
    if (focusParticipants && state.status === "ready") listRef.current?.scrollIntoView?.({ block: "start" });
  }, [focusParticipants, state.status]);

  const handleExport = async (format: "xlsx" | "csv") => {
    setExporting(format);
    setActionError(null);
    try {
      await downloadEventParticipants(eventId, format);
    } catch (error) {
      setActionError(describeActionError(error));
    } finally {
      setExporting(null);
    }
  };

  const copyAnnouncement = async () => {
    setShareBusy(true);
    setShareStatus("");
    try {
      // Fetch on every click: the text must reflect the latest published edit,
      // topic link and registration deep link.
      const { text } = await fetchEventShareText(eventId);
      setShareText(text);
      if (!navigator.clipboard?.writeText) {
        setShareStatus("Выделите текст ниже и скопируйте вручную.");
        return;
      }
      try {
        await navigator.clipboard.writeText(text);
        setShareStatus("Анонс со ссылками скопирован.");
      } catch {
        setShareStatus("Автокопирование недоступно. Выделите текст ниже.");
      }
    } catch (error) {
      setShareStatus(describeActionError(error));
    } finally {
      setShareBusy(false);
    }
  };

  const participants = state.status === "ready" ? state.data : [];
  const stats = useMemo(() => ({
    registrations: participants.filter((item) => ["registered", "will_come", "attended"].includes(item.status)).length,
    attended: participants.filter((item) => item.status === "attended").length,
    cancelled: participants.filter((item) => ["not_coming", "cancelled"].includes(item.status)).length,
    noShow: participants.filter((item) => item.status === "no_show").length,
    waitlist: participants.filter((item) => item.status === "waitlist").length,
  }), [participants]);

  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase("ru");
    return participants
      .filter((item) => {
        if (!matchesFilter(item.status, filter)) return false;
        return !normalized || item.participant_name.toLocaleLowerCase("ru").includes(normalized);
      })
      .sort((left, right) => {
        const byTime = Date.parse(right.registered_at ?? "") - Date.parse(left.registered_at ?? "");
        return Number.isNaN(byTime) || byTime === 0 ? right.registration_id - left.registration_id : byTime;
      });
  }, [filter, participants, query]);

  const chipCounts = useMemo(
    () => Object.fromEntries(GROUP_CHIPS.map((chip) => [chip.value, participants.filter((item) => matchesFilter(item.status, chip.value)).length])),
    [participants],
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <button type="button" onClick={onBack} style={{ alignSelf: "flex-start" }}>← К мероприятиям</button>

      <Card>
        <strong>Управление карточкой</strong>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: ".5rem", marginTop: ".75rem" }}>
          <button type="button" className="era-btn-primary" onClick={() => setEditor(editor === "details" ? null : "details")}>✎ Данные и ссылки</button>
          <button type="button" onClick={() => setEditor(editor === "poster" ? null : "poster")}>▧ Афиша</button>
        </div>
        {editor === "details" && <EventDetailsEditor eventId={eventId} onClose={() => { setEditor(null); refresh(); }} />}
        {editor === "poster" && <EventPosterEditor eventId={eventId} onBack={() => { setEditor(null); refresh(); }} />}
      </Card>

      <Card gradient>
        <p style={{ margin: "0 0 .3rem", fontSize: ".75rem", fontWeight: 800, color: "var(--era-text-secondary)" }}>УЧАСТНИКИ СОБЫТИЯ</p>
        <h2 style={{ margin: 0 }}>Присутствие подтверждает участник</h2>
        <p style={{ margin: ".4rem 0 0", color: "var(--era-text-secondary)" }}>
          Запустите событие, а в конце передайте присутствующим уникальный код. После ввода баллы начислятся автоматически.
        </p>
      </Card>

      <Card>
        <strong>Поделиться мероприятием</strong>
        <p style={{ margin: ".3rem 0 .7rem", color: "var(--era-text-muted)", fontSize: ".82rem" }}>
          Актуальные дата, место, ссылка на тему и прямая регистрация. Ничего не отправляется автоматически.
        </p>
        <button type="button" onClick={() => void copyAnnouncement()} disabled={shareBusy}>
          {shareBusy ? "Подготавливаем…" : "Скопировать анонс"}
        </button>
        {shareStatus && <p role="status">{shareStatus}</p>}
        {shareText && <textarea aria-label="Готовый анонс для копирования" readOnly value={shareText} rows={7} onFocus={(e) => e.currentTarget.select()}
          style={{ display: "block", width: "100%", boxSizing: "border-box", marginTop: ".65rem" }} />}
      </Card>
      <RegistrantMessagePanel key={eventId} eventId={eventId} />
      <EventLifecyclePanel eventId={eventId} onChanged={refresh} />

      {state.status === "ready" && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: ".5rem" }}>
          <Metric value={stats.registrations} label="Регистрации" />
          <Metric value={stats.attended} label="Подтвердили посещение" />
          <Metric value={stats.cancelled} label="Отказались" />
          <Metric value={stats.noShow} label="Не пришли" />
          {stats.waitlist > 0 && <Metric value={stats.waitlist} label="Лист ожидания" />}
        </div>
      )}

      <Card>
        <strong>Скачать список</strong>
        <p style={{ margin: ".3rem 0 .7rem", color: "var(--era-text-muted)", fontSize: ".82rem" }}>ФИО, телефон и организация из регистрационной формы. Доступно только организаторам.</p>
        <div style={{ display: "grid", gridTemplateColumns: "1.2fr .8fr", gap: ".5rem" }}>
          <button type="button" className="era-btn-primary" disabled={exporting !== null} onClick={() => void handleExport("xlsx")}>{exporting === "xlsx" ? "Готовим…" : "↓ XLSX"}</button>
          <button type="button" disabled={exporting !== null} onClick={() => void handleExport("csv")}>{exporting === "csv" ? "Готовим…" : "↓ CSV"}</button>
        </div>
      </Card>

      <div ref={listRef} style={{ scrollMarginTop: ".5rem" }}>
        <strong>Участники · {stats.registrations}</strong>
        <p style={{ margin: ".25rem 0 .5rem", color: "var(--era-text-muted)", fontSize: ".8rem" }}>Сначала новые регистрации. Список в Excel автоматически приходит владельцу в Telegram после каждой новой регистрации.</p>
        <div
          role="group"
          aria-label="Группы участников"
          data-testid="participant-filter-chips"
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
            gap: "0.5rem",
          }}
        >
          {GROUP_CHIPS.map((chip) => (
            <button
              key={chip.value}
              type="button"
              aria-pressed={filter === chip.value}
              className={filter === chip.value ? "era-btn-primary" : undefined}
              onClick={() => setFilter(chip.value)}
              style={{
                width: "100%",
                minHeight: "2.5rem",
                padding: "0.45rem 0.625rem",
                fontSize: "0.8125rem",
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              {chip.label} · {chipCounts[chip.value] ?? 0}
            </button>
          ))}
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 180px), 1fr))", gap: ".5rem", minWidth: 0 }}>
        <input aria-label="Поиск участника" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Поиск участника" style={{ width: "100%", minWidth: 0, boxSizing: "border-box" }} />
        <select aria-label="Фильтр участников" value={filter} onChange={(event) => setFilter(event.target.value as FilterValue)} style={{ width: "100%", minWidth: 0, boxSizing: "border-box" }}>
          {FILTERS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
        </select>
      </div>

      {actionError && <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{actionError}</p>}

      {state.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загрузка участников…</p>}
      {state.status === "error" && (
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: ".75rem" }}>
          <EmptyState text="Не удалось загрузить участников." />
          <button type="button" onClick={refresh}>Повторить загрузку участников</button>
        </div>
      )}
      {state.status === "ready" && (
        <button type="button" onClick={refresh} style={{ alignSelf: "flex-start" }}>Обновить участников</button>
      )}
      {state.status === "ready" && participants.length === 0 && <EmptyState text="Пока никто не зарегистрирован. Как только появится первая регистрация, участник будет здесь." />}
      {state.status === "ready" && participants.length > 0 && filtered.length === 0 && <EmptyState text="По этому поиску участников нет. Измените имя или фильтр." />}

      {filtered.map((participant) => {
        const contactParts = [participant.organization, participant.phone]
          .map((part) => (part ?? "").trim())
          .filter(Boolean);
        const registeredLabel = formatRegisteredAt(participant.registered_at);
        return (
          <Card key={participant.registration_id} style={{ padding: "0.8rem 0.9rem" }}>
            <div data-testid={`participant-row-${participant.registration_id}`} style={{ display: "flex", flexDirection: "column", gap: "0.3rem", minWidth: 0 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem", flexWrap: "wrap", minWidth: 0 }}>
                <strong style={{ flex: "1 1 8.5rem", minWidth: 0, lineHeight: 1.3, overflowWrap: "anywhere" }}>
                  {participant.participant_name}
                </strong>
                <StatusBadge
                  label={STATUS_LABELS[participant.status] ?? "Статус обновлён"}
                  tone={participant.status === "attended" ? "violet" : "neutral"}
                />
              </div>
              {contactParts.length > 0 && (
                <p style={{ margin: 0, color: "var(--era-text-secondary, var(--era-text-muted))", fontSize: "0.8125rem", lineHeight: 1.35, overflowWrap: "anywhere" }}>
                  {contactParts.join(" · ")}
                </p>
              )}
              {registeredLabel && (
                <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.75rem" }}>
                  Зарегистрирован {registeredLabel}
                </p>
              )}
            </div>
            {participant.status === "attended" && (
              <p style={{ margin: ".45rem 0 0", color: "var(--era-text-muted)", fontSize: ".78rem" }}>
                Подтверждено через уникальный код мероприятия.
              </p>
            )}
          </Card>
        );
      })}
    </div>
  );
}

function Metric({ value, label }: { value: number; label: string }) {
  return <Card style={{ padding: ".8rem" }}><div style={{ fontSize: "1.6rem", fontWeight: 900 }}>{value}</div><div style={{ color: "var(--era-text-muted)", fontSize: ".8rem" }}>{label}</div></Card>;
}
