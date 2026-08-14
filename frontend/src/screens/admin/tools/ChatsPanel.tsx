import { useCallback, useState } from "react";
import { describeActionError, fetchChatRegistry, runChatsHealthCheck } from "../../../api/client";
import { Card } from "../../../components/Card";
import { EmptyState } from "../../../components/EmptyState";
import { StatusBadge } from "../../../components/StatusBadge";
import { useAsync } from "../../../hooks/useAsync";
import type { ChatHealthResult } from "../../../types/admin";

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

// Chat Infrastructure Registry (2026-08 master spec section 30): one card
// per org chat -- binding, who has access, greeting state, and recent
// send/error history from the audit log (app/services/chat_registry_service.py)
// -- plus a "Проверить чаты" button that runs a real, read-only Telegram
// check (bot.get_chat_member) only when pressed, never automatically.
export function ChatsPanel() {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchChatRegistry(), [refreshKey]);
  const [health, setHealth] = useState<Record<string, ChatHealthResult>>({});
  const [checking, setChecking] = useState(false);
  const [checkError, setCheckError] = useState<string | null>(null);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const handleHealthCheck = useCallback(async () => {
    setChecking(true);
    setCheckError(null);
    try {
      const results = await runChatsHealthCheck();
      setHealth(Object.fromEntries(results.map((r) => [r.chat_key, r])));
    } catch (error) {
      setCheckError(describeActionError(error));
    } finally {
      setChecking(false);
    }
  }, []);

  if (state.status === "loading") {
    return <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>;
  }
  if (state.status === "error") {
    return <EmptyState text="Не удалось загрузить реестр чатов." />;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <button type="button" disabled={checking} onClick={handleHealthCheck}>
        {checking ? "Проверяем…" : "🔍 Проверить чаты"}
      </button>
      {checkError && <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{checkError}</p>}
      {state.data.length === 0 && <EmptyState text="Чаты пока не настроены." />}
      {state.data.map((chat) => {
        const result = health[chat.chat_key];
        return (
          <Card key={chat.chat_key}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem", alignItems: "flex-start" }}>
              <strong>{chat.title}</strong>
              <div style={{ display: "flex", gap: "0.375rem", flexWrap: "wrap", justifyContent: "flex-end" }}>
                <StatusBadge label={chat.is_bound ? "привязан" : "не привязан"} tone={chat.is_bound ? "violet" : "neutral"} />
                {result && (
                  <StatusBadge label={result.ok ? "чат в порядке" : `ошибка: ${result.detail}`} tone={result.ok ? "violet" : "red"} />
                )}
              </div>
            </div>
            <p style={{ margin: "0.375rem 0 0", fontSize: "0.8125rem", color: "var(--era-text-muted)" }}>
              Доступ: {chat.permission_description}
            </p>
            <p style={{ margin: "0.25rem 0 0", fontSize: "0.8125rem", color: "var(--era-text-muted)" }}>
              Приветствие:{" "}
              {chat.greeting_enabled === null ? "не настроено" : chat.greeting_enabled ? "включено" : "выключено"}
            </p>
            <p style={{ margin: "0.25rem 0 0", fontSize: "0.8125rem", color: "var(--era-text-muted)" }}>
              Последняя рассылка: {formatDate(chat.last_sent_at)}
              {chat.last_error_at && (
                <span style={{ color: "var(--era-error)" }}> · Последняя ошибка: {formatDate(chat.last_error_at)}</span>
              )}
            </p>
            {!chat.is_bound && (
              <p style={{ margin: "0.375rem 0 0", color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
                Перешлите любое сообщение из этого чата боту с /bind
              </p>
            )}
          </Card>
        );
      })}
      <button type="button" onClick={refresh} style={{ alignSelf: "flex-start" }}>
        Обновить
      </button>
    </div>
  );
}
