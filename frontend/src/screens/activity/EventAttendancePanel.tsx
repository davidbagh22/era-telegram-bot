import { useCallback, useState } from "react";
import { ApiError } from "../../api/client";
import {
  confirmEventAttendance,
  fetchEventAttendanceState,
} from "../../api/eventAttendance";
import { Card } from "../../components/Card";
import { useToast } from "../../components/Toast";
import { useAsync } from "../../hooks/useAsync";
import { successHaptic } from "../../telegram/webApp";

function confirmationError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.message === "invalid_attendance_code") return "Код не подошёл. Проверьте символы и попробуйте ещё раз.";
    if (error.message === "attendance_not_open") return "Подтверждение ещё не открыто или уже недоступно.";
    if (error.message === "not_registered") return "Подтвердить посещение могут только зарегистрированные участники.";
    if (error.message === "registration_not_active") return "Эта регистрация больше не активна.";
  }
  return "Не удалось подтвердить участие. Проверьте соединение и попробуйте снова.";
}

export function EventAttendancePanel({ eventId }: { eventId: number }) {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchEventAttendanceState(eventId), [eventId, refreshKey]);
  const [code, setCode] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();

  const confirm = useCallback(async () => {
    const normalized = code.trim();
    if (!normalized) {
      setError("Введите код, который дали ведущие мероприятия.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const result = await confirmEventAttendance(eventId, normalized);
      successHaptic();
      setCode("");
      setRefreshKey((value) => value + 1);
      toast.show(
        result.awarded_now > 0
          ? `Посещение подтверждено · +${result.awarded_now} баллов`
          : "Посещение подтверждено",
        "success",
      );
    } catch (requestError) {
      setError(confirmationError(requestError));
    } finally {
      setSubmitting(false);
    }
  }, [code, eventId, toast]);

  if (state.status === "loading" || state.status === "error") return null;
  if (!state.data.eligible) return null;

  if (state.data.confirmed) {
    return (
      <Card style={{ borderColor: "rgba(85,189,130,.28)", background: "rgba(85,189,130,.055)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: ".75rem", alignItems: "center" }}>
          <div>
            <strong>✓ Посещение подтверждено</strong>
            <p style={{ margin: ".3rem 0 0", color: "var(--era-text-muted)", fontSize: ".84rem" }}>
              Ваше присутствие сохранено в истории ЭРА.
            </p>
          </div>
          {state.data.points_for_visit > 0 && state.data.points_awarded && (
            <strong style={{ color: "var(--era-gold-ink)", whiteSpace: "nowrap" }}>+{state.data.points_for_visit}</strong>
          )}
        </div>
      </Card>
    );
  }

  if (!state.data.confirmation_open) {
    if (state.data.event_status !== "active") return null;
    return (
      <Card style={{ borderColor: "rgba(255,255,255,.09)" }}>
        <strong>Подтверждение после мероприятия</strong>
        <p style={{ margin: ".35rem 0 0", color: "var(--era-text-muted)", fontSize: ".86rem", lineHeight: 1.45 }}>
          В конце ведущие дадут код присутствующим. Поле для ввода откроется здесь после завершения события.
        </p>
      </Card>
    );
  }

  return (
    <Card style={{ borderColor: "rgba(197,162,100,.3)", background: "linear-gradient(145deg, rgba(197,162,100,.09), rgba(227,38,54,.055))" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: ".7rem" }}>
        <div>
          <strong style={{ fontSize: "1.03rem" }}>Подтвердить участие</strong>
          <p style={{ margin: ".3rem 0 0", color: "var(--era-text-muted)", fontSize: ".86rem", lineHeight: 1.45 }}>
            Были на мероприятии? Введите код, который дали ведущие. После подтверждения баллы начислятся автоматически.
          </p>
        </div>
        <input
          value={code}
          onChange={(event) => setCode(event.target.value.toUpperCase())}
          onKeyDown={(event) => { if (event.key === "Enter" && !submitting) void confirm(); }}
          placeholder="Код мероприятия"
          autoCapitalize="characters"
          autoCorrect="off"
          spellCheck={false}
          maxLength={12}
          style={{ textTransform: "uppercase", letterSpacing: ".16em", fontWeight: 850, textAlign: "center" }}
          aria-label="Код подтверждения участия"
        />
        {error && <p style={{ color: "var(--era-error)", margin: 0, fontSize: ".82rem" }}>{error}</p>}
        <button type="button" className="era-btn-primary" disabled={submitting || !code.trim()} onClick={() => void confirm()}>
          {submitting
            ? "Проверяем…"
            : state.data.points_for_visit > 0
              ? `Подтвердить · +${state.data.points_for_visit} баллов`
              : "Подтвердить участие"}
        </button>
        <span style={{ color: "var(--era-text-muted)", fontSize: ".75rem" }}>
          Код выдаётся только присутствующим и действует только для этого мероприятия.
        </span>
      </div>
    </Card>
  );
}
