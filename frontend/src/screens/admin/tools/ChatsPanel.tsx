import { useCallback, useState } from "react";
import {
  describeActionError,
  fetchChatRegistry,
  publishChatFaq,
  runChatsHealthCheck,
} from "../../../api/client";
import { Card } from "../../../components/Card";
import { EmptyState } from "../../../components/EmptyState";
import { StatusBadge } from "../../../components/StatusBadge";
import { useAsync } from "../../../hooks/useAsync";
import type { ChatHealthResult } from "../../../types/admin";

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

const BIND_COMMANDS: Record<string, string> = {
  general: "/bind general",
  internal: "/bind internal",
  external: "/bind external",
  leaders: "/bind leaders",
};

export function ChatsPanel() {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchChatRegistry(), [refreshKey]);
  const [health, setHealth] = useState<Record<string, ChatHealthResult>>({});
  const [checking, setChecking] = useState(false);
  const [checkError, setCheckError] = useState<string | null>(null);
  const [publishingFaq, setPublishingFaq] = useState(false);
  const [faqResult, setFaqResult] = useState<string | null>(null);
  const [faqError, setFaqError] = useState<string | null>(null);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const handleHealthCheck = useCallback(async () => {
    setChecking(true);
    setCheckError(null);
    try {
      const results = await runChatsHealthCheck();
      setHealth(Object.fromEntries(results.map((result) => [result.chat_key, result])));
    } catch (error) {
      setCheckError(describeActionError(error));
    } finally {
      setChecking(false);
    }
  }, []);

  const handlePublishFaq = useCallback(async () => {
    setPublishingFaq(true);
    setFaqError(null);
    setFaqResult(null);
    try {
      const result = await publishChatFaq();
      setFaqResult(
        result.pinned
          ? "FAQ обновлён и закреплён наверху общего чата ✅"
          : "FAQ обновлён, но Telegram не дал закрепить его — проверьте право бота «Закреплять сообщения».",
      );
      refresh();
    } catch (error) {
      setFaqError(describeActionError(error));
    } finally {
      setPublishingFaq(false);
    }
  }, [refresh]);

  if (state.status === "loading") return <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>;
  if (state.status === "error") return <EmptyState text="Не удалось загрузить реестр чатов." />;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <Card style={{ background: "linear-gradient(135deg, rgba(255,48,72,0.10), rgba(107,60,255,0.12)), var(--era-surface)", border: "1px solid rgba(255,48,72,0.16)" }}>
        <strong>Чаты привязываются из самого Telegram</strong>
        <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
          Добавьте бота администратором нужного чата и отправьте указанную команду прямо там. ЭРА сохранит реальный chat_id в БД — вручную вводить или угадывать ID не нужно.
        </p>
      </Card>

      <button type="button" disabled={checking} onClick={handleHealthCheck}>{checking ? "Проверяем…" : "🔍 Проверить чаты"}</button>
      {checkError && <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{checkError}</p>}
      {state.data.length === 0 && <EmptyState text="Чаты пока не настроены." />}
      {state.data.map((chat) => {
        const result = health[chat.chat_key];
        const bindCommand = BIND_COMMANDS[chat.chat_key] ?? `/bind ${chat.chat_key}`;
        return (
          <Card key={chat.chat_key}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem", alignItems: "flex-start" }}>
              <strong>{chat.title}</strong>
              <div style={{ display: "flex", gap: "0.375rem", flexWrap: "wrap", justifyContent: "flex-end" }}>
                <StatusBadge label={chat.is_bound ? "привязан" : "не привязан"} tone={chat.is_bound ? "violet" : "neutral"} />
                {result && <StatusBadge label={result.ok ? "чат в порядке" : `ошибка: ${result.detail}`} tone={result.ok ? "violet" : "red"} />}
              </div>
            </div>
            <p style={{ margin: "0.375rem 0 0", fontSize: "0.8125rem", color: "var(--era-text-muted)" }}>Доступ: {chat.permission_description}</p>
            <p style={{ margin: "0.25rem 0 0", fontSize: "0.8125rem", color: "var(--era-text-muted)" }}>
              Приветствие: {chat.greeting_enabled === null ? "не настроено" : chat.greeting_enabled ? "включено" : "выключено"}
            </p>
            <p style={{ margin: "0.25rem 0 0", fontSize: "0.8125rem", color: "var(--era-text-muted)" }}>
              Последняя рассылка: {formatDate(chat.last_sent_at)}
              {chat.last_error_at && <span style={{ color: "var(--era-error)" }}> · Последняя ошибка: {formatDate(chat.last_error_at)}</span>}
            </p>
            {!chat.is_bound && (
              <div style={{ marginTop: "0.625rem", padding: "0.65rem", borderRadius: "var(--era-radius-control)", background: "var(--era-surface-2)" }}>
                <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>Команда для этого чата:</p>
                <code style={{ display: "block", marginTop: "0.25rem", color: "var(--era-text)" }}>{bindCommand}</code>
              </div>
            )}
            {chat.chat_key === "general" && chat.is_bound && (
              <div style={{ marginTop: "0.7rem", paddingTop: "0.65rem", borderTop: "1px solid var(--era-border)" }}>
                <strong style={{ fontSize: "var(--era-text-sm)" }}>📌 FAQ общего чата</strong>
                <p style={{ margin: "0.25rem 0 0.55rem", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>
                  Бот автоматически поддерживает одну FAQ-карточку закреплённой. Ответы по быстрым кнопкам приходят человеку в личные сообщения.
                </p>
                <button type="button" disabled={publishingFaq} onClick={handlePublishFaq}>{publishingFaq ? "Обновляем…" : "📌 Обновить и закрепить FAQ"}</button>
                {faqResult && <p style={{ margin: "0.375rem 0 0", fontSize: "0.8125rem", color: "var(--era-text-muted)" }}>{faqResult}</p>}
                {faqError && <p style={{ margin: "0.375rem 0 0", fontSize: "0.8125rem", color: "var(--era-error)" }}>{faqError}</p>}
              </div>
            )}
          </Card>
        );
      })}
      <button type="button" onClick={refresh} style={{ alignSelf: "flex-start" }}>Обновить</button>
    </div>
  );
}
