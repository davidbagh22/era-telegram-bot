import { useCallback, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import {
  confirmEventAttendance,
  fetchEventAttendanceState,
  submitAttendanceProof,
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
    if (error.message === "proof_must_be_image") return "Прикрепите фото JPG, PNG или WEBP.";
    if (error.message === "proof_too_large") return "Фото должно быть не больше 5 МБ.";
    if (error.message === "event_not_started") return "Фото можно отправить в день мероприятия или позже.";
  }
  return "Не удалось подтвердить участие. Проверьте соединение и попробуйте снова.";
}

export function EventAttendancePanel({ eventId }: { eventId: number }) {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchEventAttendanceState(eventId), [eventId, refreshKey]);
  const [code, setCode] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
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
          ? `Участие подтверждено ✓ · +${result.awarded_now} баллов`
          : "Участие уже подтверждено ✓",
        "success",
      );
    } catch (requestError) {
      setError(confirmationError(requestError));
    } finally {
      setSubmitting(false);
    }
  }, [code, eventId, toast]);

  const onFile = useCallback(async (file: File | undefined) => {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      await submitAttendanceProof(eventId, file);
      successHaptic();
      setRefreshKey((value) => value + 1);
      toast.show("Фото отправлено админу на проверку", "success");
    } catch (requestError) {
      setError(confirmationError(requestError));
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }, [eventId, toast]);

  if (state.status === "loading" || state.status === "error") return null;
  if (!state.data.eligible) return null;

  if (state.data.confirmed) {
    return (
      <Card style={{ borderColor: "rgba(85,189,130,.28)", background: "rgba(85,189,130,.055)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: ".75rem", alignItems: "center" }}>
          <div>
            <strong>✓ Посещение подтверждено</strong>
            <p style={{ margin: ".3rem 0 0", color: "var(--era-text-muted)", fontSize: ".84rem" }}>
              Баллы начислены. Сертификат участника появится после проверки / автовыдачи.
            </p>
          </div>
          {state.data.points_for_visit > 0 && state.data.points_awarded && (
            <strong style={{ color: "var(--era-gold-ink)", whiteSpace: "nowrap" }}>+{state.data.points_for_visit}</strong>
          )}
        </div>
      </Card>
    );
  }

  const proofPending = state.data.proof_status === "pending";
  const showProof = Boolean(state.data.can_submit_proof) || proofPending;
  const showCode = state.data.confirmation_open;

  if (!showProof && !showCode) {
    if (state.data.confirmation_closed) {
      return (
        <Card style={{ borderColor: "var(--era-border)", background: "var(--era-surface-2)" }}>
          <strong>Подтверждение участия закрыто</strong>
        </Card>
      );
    }
    return null;
  }

  return (
    <Card style={{ borderColor: "var(--era-border-strong)", background: "linear-gradient(145deg, rgba(188, 33, 132,.12), rgba(255, 165, 234,.06))" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: ".7rem" }}>
        <div>
          <strong style={{ fontSize: "1.03rem" }}>Подтвердить участие</strong>
          <p style={{ margin: ".3rem 0 0", color: "var(--era-text-muted)", fontSize: ".86rem", lineHeight: 1.45 }}>
            Пришлите фото с места — админ проверит и начислит баллы. Можно также ввести код ведущих, если он открыт.
          </p>
        </div>

        {showProof && (
          <div style={{ display: "grid", gap: ".45rem" }}>
            <input
              ref={fileRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              hidden
              onChange={(event) => void onFile(event.target.files?.[0])}
            />
            {proofPending ? (
              <div style={{ padding: ".7rem .8rem", borderRadius: ".85rem", background: "var(--era-surface-2)", fontSize: ".84rem", fontWeight: 750 }}>
                Фото на проверке у админа
              </div>
            ) : (
              <button type="button" className="era-btn-primary" disabled={uploading} onClick={() => fileRef.current?.click()}>
                {uploading ? "Отправляем…" : "📎 Прикрепить фото с места"}
              </button>
            )}
          </div>
        )}

        {showCode && (
          <>
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
            <button type="button" disabled={submitting || !code.trim()} onClick={() => void confirm()}>
              {submitting ? "Проверяем…" : "Подтвердить кодом"}
            </button>
          </>
        )}

        {error && <p style={{ color: "var(--era-error)", margin: 0, fontSize: ".82rem" }}>{error}</p>}
      </div>
    </Card>
  );
}
