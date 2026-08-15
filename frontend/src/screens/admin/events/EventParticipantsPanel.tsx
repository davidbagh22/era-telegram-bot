import { useCallback, useMemo, useState } from "react";
import {
  awardEventAttendancePoints,
  describeActionError,
  fetchEventParticipants,
  setEventAttendance,
} from "../../../api/client";
import { downloadEventParticipants } from "../../../api/adminEvents";
import { Card } from "../../../components/Card";
import { EmptyState } from "../../../components/EmptyState";
import { StatusBadge } from "../../../components/StatusBadge";
import { useAsync } from "../../../hooks/useAsync";

const STATUS_LABELS: Record<string, string> = {
  registered: "Зарегистрирован",
  will_come: "Подтвердил участие",
  waitlist: "Лист ожидания",
  not_coming: "Отказался",
  attended: "Пришёл",
  no_show: "Не пришёл",
  cancelled: "Регистрация отменена",
};

const FILTERS = [
  { value: "all", label: "Все статусы" },
  { value: "active", label: "Зарегистрированы" },
  { value: "attended", label: "Пришли" },
  { value: "cancelled", label: "Отказались" },
  { value: "no_show", label: "No-show" },
  { value: "waitlist", label: "Лист ожидания" },
] as const;

type FilterValue = typeof FILTERS[number]["value"];

interface EventParticipantsPanelProps {
  eventId: number;
  onBack: () => void;
}

function matchesFilter(status: string, filter: FilterValue): boolean {
  if (filter === "all") return true;
  if (filter === "active") return ["registered", "will_come"].includes(status);
  if (filter === "cancelled") return ["not_coming", "cancelled"].includes(status);
  return status === filter;
}

export function EventParticipantsPanel({ eventId, onBack }: EventParticipantsPanelProps) {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchEventParticipants(eventId), [eventId, refreshKey]);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [awarding, setAwarding] = useState(false);
  const [exporting, setExporting] = useState<"xlsx" | "csv" | null>(null);
  const [awardResult, setAwardResult] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<FilterValue>("all");

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const handleAttendance = useCallback(async (registrationId: number, attended: boolean) => {
    setBusyId(registrationId);
    setActionError(null);
    try {
      await setEventAttendance(eventId, registrationId, attended);
      refresh();
    } catch (error) {
      setActionError(describeActionError(error));
    } finally {
      setBusyId(null);
    }
  }, [eventId, refresh]);

  const handleAward = useCallback(async () => {
    setAwarding(true);
    setActionError(null);
    setAwardResult(null);
    try {
      const result = await awardEventAttendancePoints(eventId);
      setAwardResult(`Баллы начислены новым посетителям: ${result.awarded_count}`);
      refresh();
    } catch (error) {
      setActionError(describeActionError(error));
    } finally {
      setAwarding(false);
    }
  }, [eventId, refresh]);

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
    return participants.filter((item) => {
      if (!matchesFilter(item.status, filter)) return false;
      return !normalized || item.participant_name.toLocaleLowerCase("ru").includes(normalized);
    });
  }, [filter, participants, query]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <button type="button" onClick={onBack} style={{ alignSelf: "flex-start" }}>← К мероприятиям</button>

      <Card gradient>
        <p style={{ margin: "0 0 .3rem", fontSize: ".75rem", fontWeight: 800, color: "rgba(255,255,255,.7)" }}>УЧАСТНИКИ СОБЫТИЯ</p>
        <h2 style={{ margin: 0 }}>Регистрации под контролем</h2>
        <p style={{ margin: ".4rem 0 0", color: "rgba(255,255,255,.8)" }}>Поиск, посещаемость, очередь и выгрузка — из одной реальной базы.</p>
      </Card>

      {state.status === "ready" && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: ".5rem" }}>
          <Metric value={stats.registrations} label="Регистрации" />
          <Metric value={stats.attended} label="Пришли" />
          <Metric value={stats.cancelled} label="Отказались" />
          <Metric value={stats.noShow} label="No-show" />
          {stats.waitlist > 0 && <Metric value={stats.waitlist} label="Лист ожидания" />}
        </div>
      )}

      <Card>
        <strong>Скачать список</strong>
        <p style={{ margin: ".3rem 0 .7rem", color: "var(--era-text-muted)", fontSize: ".82rem" }}>Только Имя, Фамилия и номер телефона из профиля. Никаких лишних персональных данных.</p>
        <div style={{ display: "grid", gridTemplateColumns: "1.2fr .8fr", gap: ".5rem" }}>
          <button type="button" className="era-btn-primary" disabled={exporting !== null} onClick={() => void handleExport("xlsx")}>{exporting === "xlsx" ? "Готовим…" : "↓ XLSX"}</button>
          <button type="button" disabled={exporting !== null} onClick={() => void handleExport("csv")}>{exporting === "csv" ? "Готовим…" : "↓ CSV"}</button>
        </div>
      </Card>

      <div style={{ display: "grid", gridTemplateColumns: "1.25fr .75fr", gap: ".5rem" }}>
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Поиск участника" />
        <select value={filter} onChange={(event) => setFilter(event.target.value as FilterValue)}>
          {FILTERS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
        </select>
      </div>

      {actionError && <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{actionError}</p>}
      {awardResult && <Card style={{ borderColor: "rgba(67,211,154,.35)" }}><strong>{awardResult}</strong></Card>}

      <button type="button" disabled={awarding || stats.attended === 0} onClick={handleAward}>
        {awarding ? "Начисляем…" : "Начислить баллы посетившим"}
      </button>

      {state.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загрузка участников…</p>}
      {state.status === "error" && <EmptyState text="Не удалось загрузить участников." />}
      {state.status === "ready" && participants.length === 0 && <EmptyState text="Пока никто не зарегистрирован. Как только появится первая регистрация, участник будет здесь." />}
      {state.status === "ready" && participants.length > 0 && filtered.length === 0 && <EmptyState text="По этому поиску участников нет. Измените имя или фильтр." />}

      {filtered.map((participant) => (
        <Card key={participant.registration_id} style={{ padding: "0.8rem 0.9rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem", alignItems: "center" }}>
            <strong>{participant.participant_name}</strong>
            <StatusBadge label={STATUS_LABELS[participant.status] ?? "Статус обновлён"} tone={participant.status === "attended" ? "violet" : "neutral"} />
          </div>
          {!["not_coming", "cancelled", "waitlist"].includes(participant.status) && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem", marginTop: "0.65rem" }}>
              <button type="button" disabled={busyId === participant.registration_id} onClick={() => void handleAttendance(participant.registration_id, true)}>Пришёл</button>
              <button type="button" disabled={busyId === participant.registration_id} onClick={() => void handleAttendance(participant.registration_id, false)}>Не пришёл</button>
            </div>
          )}
        </Card>
      ))}
    </div>
  );
}

function Metric({ value, label }: { value: number; label: string }) {
  return <Card style={{ padding: ".8rem" }}><div style={{ fontSize: "1.6rem", fontWeight: 900 }}>{value}</div><div style={{ color: "var(--era-text-muted)", fontSize: ".8rem" }}>{label}</div></Card>;
}
