import { useCallback, useState } from "react";
import {
  createEventActivities,
  describeActionError,
  fetchAdminEventActivities,
  sendEventActivities,
} from "../../../api/client";
import { Card } from "../../../components/Card";
import { EmptyState } from "../../../components/EmptyState";
import { StatusBadge } from "../../../components/StatusBadge";
import { useAsync } from "../../../hooks/useAsync";

interface EventActivitiesPanelProps {
  eventId: number;
  onBack: () => void;
}

// Create/send activities for one event — the Mini App equivalent of the
// *live* admin:event:activities:create/send handlers (see
// app/services/event_activity_service.py's docstring for which files
// actually win the router-precedence race). Reviewing submitted proof
// happens separately, in ActivitySubmissionsPanel — that queue spans all
// events, not just this one.
export function EventActivitiesPanel({ eventId, onBack }: EventActivitiesPanelProps) {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchAdminEventActivities(eventId), [eventId, refreshKey]);
  const [lines, setLines] = useState("");
  const [creating, setCreating] = useState(false);
  const [sending, setSending] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<string | null>(null);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const handleCreate = useCallback(async () => {
    if (!lines.trim()) return;
    setCreating(true);
    setActionError(null);
    try {
      const result = await createEventActivities(eventId, lines);
      setLastResult(`Создано: ${result.created}. Пропущено строк: ${result.rejected}.`);
      setLines("");
      refresh();
    } catch (error) {
      setActionError(describeActionError(error));
    } finally {
      setCreating(false);
    }
  }, [eventId, lines, refresh]);

  const handleSend = useCallback(async () => {
    setSending(true);
    setActionError(null);
    try {
      const result = await sendEventActivities(eventId);
      setLastResult(`Активности отправлены: ${result.sent}. Повторная отправка заблокирована.`);
    } catch (error) {
      setActionError(describeActionError(error));
    } finally {
      setSending(false);
    }
  }, [eventId]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <button type="button" onClick={onBack}>
        ← Мероприятия
      </button>

      {actionError && (
        <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{actionError}</p>
      )}
      {lastResult && (
        <p style={{ color: "var(--era-text-muted)", fontSize: "0.8125rem", margin: 0 }}>{lastResult}</p>
      )}

      <Card>
        <strong>Новые активности</strong>
        <p style={{ margin: "0.25rem 0 0.5rem", color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
          Одна строка — одна активность. Формат: Название | баллы | тип | описание
          <br />
          Типы: photo, link, text, file, manual, video
        </p>
        <textarea
          value={lines}
          onChange={(event) => setLines(event.target.value)}
          rows={4}
          placeholder={"Выложить сторис | 30 | link | Отправьте ссылку на публикацию\nПомочь на регистрации | 40 | manual | Проверка организатором"}
          style={{
            width: "100%",
            fontFamily: "var(--era-font-body)",
            padding: "0.5rem",
            borderRadius: "0.5rem",
            border: "1px solid var(--era-border)",
            background: "var(--era-bg)",
            color: "var(--era-text)",
          }}
        />
        <button
          type="button"
          className="era-btn-primary"
          disabled={creating || !lines.trim()}
          onClick={handleCreate}
          style={{ marginTop: "0.5rem" }}
        >
          Добавить активности
        </button>
      </Card>

      {state.status === "ready" && state.data.length > 0 && (
        <button type="button" className="era-btn-primary" disabled={sending} onClick={handleSend}>
          📤 Отправить участникам
        </button>
      )}

      {state.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>}
      {state.status === "error" && <EmptyState text="Не удалось загрузить активности." />}
      {state.status === "ready" && state.data.length === 0 && <EmptyState text="Активностей пока нет." />}
      {state.status === "ready" &&
        state.data.map((activity) => (
          <Card key={activity.id}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
              <strong>{activity.title}</strong>
              <StatusBadge label={activity.is_active ? "активна" : "скрыта"} tone="violet" />
            </div>
            <p style={{ margin: "0.25rem 0 0.5rem", color: "var(--era-text-muted)" }}>{activity.description}</p>
            <p style={{ margin: 0, fontSize: "0.875rem" }}>
              {activity.points} баллов · формат: {activity.submission_type}
            </p>
          </Card>
        ))}
    </div>
  );
}
