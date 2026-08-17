import { useCallback, useState } from "react";
import { ApiError } from "../../../api/client";
import {
  completeAdminEvent,
  fetchAdminEventAttendanceState,
  startAdminEvent,
} from "../../../api/eventAttendance";
import { Card } from "../../../components/Card";
import { useToast } from "../../../components/Toast";
import { useAsync } from "../../../hooks/useAsync";
import { successHaptic } from "../../../telegram/webApp";

function actionError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.message === "event_cannot_start") return "Это мероприятие сейчас нельзя запустить. Проверьте его статус.";
    if (error.message === "event_not_active") return "Сначала запустите мероприятие.";
    if (error.message === "event_not_found") return "Мероприятие больше не найдено.";
  }
  return "Не удалось изменить статус мероприятия. Попробуйте ещё раз.";
}

function formatCode(value: string): string {
  return value.length === 8 ? `${value.slice(0, 4)}-${value.slice(4)}` : value;
}

interface EventLifecyclePanelProps {
  eventId: number;
  onChanged?: () => void;
}

export function EventLifecyclePanel({ eventId, onChanged }: EventLifecyclePanelProps) {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchAdminEventAttendanceState(eventId), [eventId, refreshKey]);
  const [busy, setBusy] = useState<"start" | "complete" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();

  const refresh = useCallback(() => {
    setRefreshKey((value) => value + 1);
    onChanged?.();
  }, [onChanged]);

  const start = useCallback(async () => {
    setBusy("start");
    setError(null);
    try {
      const result = await startAdminEvent(eventId);
      successHaptic();
      toast.show(
        result.notified_count > 0
          ? `Мероприятие начато · уведомлено ${result.notified_count}`
          : "Мероприятие начато",
        "success",
      );
      refresh();
    } catch (requestError) {
      setError(actionError(requestError));
    } finally {
      setBusy(null);
    }
  }, [eventId, refresh, toast]);

  const complete = useCallback(async () => {
    setBusy("complete");
    setError(null);
    try {
      const result = await completeAdminEvent(eventId);
      successHaptic();
      toast.show(
        result.notified_count > 0
          ? `Подтверждение открыто · уведомлено ${result.notified_count}`
          : "Мероприятие завершено · подтверждение открыто",
        "success",
      );
      refresh();
    } catch (requestError) {
      setError(actionError(requestError));
    } finally {
      setBusy(null);
    }
  }, [eventId, refresh, toast]);

  if (state.status === "loading") {
    return <Card><span style={{ color: "var(--era-text-muted)" }}>Загружаем управление мероприятием…</span></Card>;
  }
  if (state.status === "error") {
    return <Card><span style={{ color: "var(--era-error)" }}>Не удалось загрузить управление мероприятием.</span></Card>;
  }

  const item = state.data;
  const started = Boolean(item.started_at);
  const completed = Boolean(item.completed_at);

  return (
    <Card style={{ borderColor: item.confirmation_open ? "rgba(197,162,100,.32)" : "rgba(255,255,255,.09)" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: ".8rem" }}>
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", gap: ".65rem", alignItems: "center" }}>
            <strong style={{ fontSize: "1.03rem" }}>Управление мероприятием</strong>
            <span style={{ color: completed ? "var(--era-gold-ink)" : started ? "var(--era-success)" : "var(--era-text-muted)", fontSize: ".78rem", fontWeight: 850 }}>
              {completed ? "ЗАВЕРШЕНО" : started ? "ИДЁТ СЕЙЧАС" : "ГОТОВО К СТАРТУ"}
            </span>
          </div>
          <p style={{ margin: ".35rem 0 0", color: "var(--era-text-muted)", fontSize: ".84rem", lineHeight: 1.45 }}>
            Старт отправит напоминание всем зарегистрированным. После завершения участникам откроется ввод кода присутствия.
          </p>
        </div>

        {item.attendance_code && (
          <div style={{ border: "1px solid rgba(197,162,100,.24)", borderRadius: "1rem", padding: ".9rem", background: "rgba(197,162,100,.055)" }}>
            <span style={{ display: "block", color: "var(--era-text-muted)", fontSize: ".72rem", fontWeight: 800, letterSpacing: ".06em" }}>КОД ДЛЯ ВЕДУЩИХ</span>
            <div style={{ marginTop: ".35rem", fontSize: "clamp(1.6rem,8vw,2.25rem)", fontWeight: 950, letterSpacing: ".12em", color: "var(--era-gold-ink)" }}>
              {formatCode(item.attendance_code)}
            </div>
            <p style={{ margin: ".35rem 0 0", color: "var(--era-text-muted)", fontSize: ".78rem", lineHeight: 1.4 }}>
              Этот код видит только управление. Передайте его участникам, которые реально были на месте, в конце мероприятия.
            </p>
          </div>
        )}

        {item.can_start && (
          <button type="button" className="era-btn-primary" disabled={busy !== null} onClick={() => void start()}>
            {busy === "start" ? "Запускаем…" : "▶ Начать мероприятие"}
          </button>
        )}

        {item.can_complete && (
          <button type="button" className="era-btn-primary" disabled={busy !== null} onClick={() => void complete()}>
            {busy === "complete" ? "Завершаем…" : "Завершить и открыть ввод кода"}
          </button>
        )}

        {item.confirmation_open && (
          <div style={{ padding: ".75rem .8rem", borderRadius: ".9rem", background: "rgba(85,189,130,.06)", color: "var(--era-success)", fontSize: ".84rem", fontWeight: 800 }}>
            ✓ Ввод кода открыт зарегистрированным участникам
          </div>
        )}

        {error && <p style={{ margin: 0, color: "var(--era-error)", fontSize: ".82rem" }}>{error}</p>}
      </div>
    </Card>
  );
}
