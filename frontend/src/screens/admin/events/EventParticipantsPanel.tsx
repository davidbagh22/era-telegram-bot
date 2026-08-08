import { useCallback, useState } from "react";
import {
  awardEventAttendancePoints,
  describeActionError,
  fetchEventParticipants,
  setEventAttendance,
} from "../../../api/client";
import { Card } from "../../../components/Card";
import { EmptyState } from "../../../components/EmptyState";
import { StatusBadge } from "../../../components/StatusBadge";
import { useAsync } from "../../../hooks/useAsync";

const STATUS_LABELS: Record<string, string> = {
  registered: "Зарегистрирован",
  will_come: "Подтвердил участие",
  not_coming: "Не сможет прийти",
  attended: "Был",
  no_show: "Не пришёл",
  cancelled: "Регистрация отменена",
};

interface EventParticipantsPanelProps {
  eventId: number;
  onBack: () => void;
}

export function EventParticipantsPanel({ eventId, onBack }: EventParticipantsPanelProps) {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchEventParticipants(eventId), [eventId, refreshKey]);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [awarding, setAwarding] = useState(false);
  const [awardResult, setAwardResult] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const handleAttendance = useCallback(
    async (registrationId: number, attended: boolean) => {
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
    },
    [eventId, refresh],
  );

  const handleAward = useCallback(async () => {
    setAwarding(true);
    setActionError(null);
    setAwardResult(null);
    try {
      const result = await awardEventAttendancePoints(eventId);
      setAwardResult(`Начислено баллов новым посетителям: ${result.awarded_count}`);
      refresh();
    } catch (error) {
      setActionError(describeActionError(error));
    } finally {
      setAwarding(false);
    }
  }, [eventId, refresh]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <button type="button" onClick={onBack} style={{ alignSelf: "flex-start" }}>
        ← К мероприятиям
      </button>

      {actionError && (
        <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{actionError}</p>
      )}
      {awardResult && (
        <p style={{ color: "var(--era-violet)", fontSize: "0.8125rem", margin: 0 }}>{awardResult}</p>
      )}

      <button type="button" className="era-btn-primary" disabled={awarding} onClick={handleAward}>
        Начислить баллы посетившим
      </button>

      {state.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>}
      {state.status === "error" && <EmptyState text="Не удалось загрузить участников." />}
      {state.status === "ready" && state.data.length === 0 && (
        <EmptyState text="Пока никто не зарегистрирован." />
      )}
      {state.status === "ready" &&
        state.data.map((participant) => (
          <Card key={participant.registration_id} style={{ padding: "0.75rem 1rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem", alignItems: "center" }}>
              <strong>{participant.participant_name}</strong>
              <StatusBadge label={STATUS_LABELS[participant.status] ?? participant.status} tone="neutral" />
            </div>
            <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.5rem" }}>
              <button
                type="button"
                disabled={busyId === participant.registration_id}
                onClick={() => handleAttendance(participant.registration_id, true)}
              >
                Был
              </button>
              <button
                type="button"
                disabled={busyId === participant.registration_id}
                onClick={() => handleAttendance(participant.registration_id, false)}
              >
                Не пришёл
              </button>
            </div>
          </Card>
        ))}
    </div>
  );
}
