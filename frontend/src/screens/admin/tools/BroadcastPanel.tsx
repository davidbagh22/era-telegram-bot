import { useCallback, useState } from "react";
import {
  describeActionError,
  fetchBroadcastAudienceOptions,
  sendChatBroadcast,
  sendPersonalBroadcast,
} from "../../../api/client";
import { Card } from "../../../components/Card";
import { useAsync } from "../../../hooks/useAsync";
import type { BroadcastAudience, ChatBroadcastKey } from "../../../types/admin";

const inputStyle = {
  width: "100%",
  fontFamily: "var(--era-font-body)",
  padding: "0.5rem",
  borderRadius: "0.5rem",
  border: "1px solid var(--era-border)",
  background: "var(--era-bg)",
  color: "var(--era-text)",
} as const;

const AUDIENCE_LABELS: Record<BroadcastAudience, string> = {
  all: "Все участники",
  role: "По роли",
  department: "По департаменту",
  direction: "По направлению",
  age: "По возрасту",
  city: "По городу",
};

const CHAT_LABELS: Record<ChatBroadcastKey, string> = {
  general: "Общий чат",
  internal: "Внутренние связи",
  external: "Внешние связи",
  leaders: "Чат лидеров",
};

// Mini App equivalent of the bot's "📨 Рассылка в личные сообщения" and
// "📣 Сообщение в выбранные чаты" flows (app/handlers/admin/panel.py,
// app/handlers/admin/management_ready.py) — see
// app/services/admin_broadcast_service.py. Both send real messages to real
// people, so both go through an explicit review step before anything is
// sent, mirroring the bot's own "Проверьте рассылку" confirmation screen.
export function BroadcastPanel() {
  const options = useAsync(() => fetchBroadcastAudienceOptions(), []);

  const [audience, setAudience] = useState<BroadcastAudience>("all");
  const [filterValue, setFilterValue] = useState("");
  const [personalText, setPersonalText] = useState("");
  const [personalConfirming, setPersonalConfirming] = useState(false);
  const [personalSending, setPersonalSending] = useState(false);
  const [personalResult, setPersonalResult] = useState<string | null>(null);
  const [personalError, setPersonalError] = useState<string | null>(null);

  const [chatKey, setChatKey] = useState<ChatBroadcastKey>("general");
  const [chatText, setChatText] = useState("");
  const [chatConfirming, setChatConfirming] = useState(false);
  const [chatSending, setChatSending] = useState(false);
  const [chatResult, setChatResult] = useState<string | null>(null);
  const [chatError, setChatError] = useState<string | null>(null);

  const needsFilter = audience !== "all";
  const filterOptions =
    audience === "role" ? options.status === "ready" ? options.data.roles : []
    : audience === "department" ? options.status === "ready" ? options.data.departments : []
    : audience === "direction" ? options.status === "ready" ? options.data.directions : []
    : audience === "age" ? options.status === "ready" ? options.data.ages : []
    : [];

  const handlePersonalSend = useCallback(async () => {
    setPersonalSending(true);
    setPersonalError(null);
    try {
      const result = await sendPersonalBroadcast({
        audience,
        filter_value: needsFilter ? filterValue || null : null,
        text: personalText.trim(),
      });
      setPersonalResult(
        `Получателей: ${result.total}. Доставлено: ${result.sent}. Ошибок: ${result.failed}. ` +
          `Дублей пропущено: ${result.duplicates}.`,
      );
      setPersonalText("");
      setPersonalConfirming(false);
    } catch (error) {
      setPersonalError(describeActionError(error));
    } finally {
      setPersonalSending(false);
    }
  }, [audience, needsFilter, filterValue, personalText]);

  const handleChatSend = useCallback(async () => {
    setChatSending(true);
    setChatError(null);
    try {
      await sendChatBroadcast(chatKey, chatText.trim());
      setChatResult("Сообщение отправлено ✅");
      setChatText("");
      setChatConfirming(false);
    } catch (error) {
      setChatError(describeActionError(error));
    } finally {
      setChatSending(false);
    }
  }, [chatKey, chatText]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <Card>
        <strong>Личные сообщения</strong>
        <p style={{ margin: "0.25rem 0 0.5rem", color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
          Рассылка придёт в личные сообщения выбранной аудитории от имени бота.
        </p>
        {personalError && (
          <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: "0 0 0.5rem" }}>{personalError}</p>
        )}
        {personalResult && (
          <p style={{ color: "var(--era-text-muted)", fontSize: "0.8125rem", margin: "0 0 0.5rem" }}>
            {personalResult}
          </p>
        )}
        {!personalConfirming ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <select
              value={audience}
              onChange={(e) => {
                setAudience(e.target.value as BroadcastAudience);
                setFilterValue("");
              }}
              style={inputStyle}
            >
              {Object.entries(AUDIENCE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
            {needsFilter &&
              (audience === "city" ? (
                <input
                  placeholder="Город так, как он указан в анкетах"
                  value={filterValue}
                  onChange={(e) => setFilterValue(e.target.value)}
                  style={inputStyle}
                />
              ) : (
                <select value={filterValue} onChange={(e) => setFilterValue(e.target.value)} style={inputStyle}>
                  <option value="">Выберите значение</option>
                  {filterOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              ))}
            <textarea
              placeholder="Текст рассылки"
              value={personalText}
              onChange={(e) => setPersonalText(e.target.value)}
              rows={3}
              style={inputStyle}
            />
            <button
              type="button"
              className="era-btn-primary"
              disabled={!personalText.trim() || (needsFilter && !filterValue.trim())}
              onClick={() => setPersonalConfirming(true)}
            >
              Далее
            </button>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <p style={{ margin: 0 }}>
              <strong>{AUDIENCE_LABELS[audience]}</strong>
              {needsFilter && filterValue ? ` · ${filterValue}` : ""}
            </p>
            <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{personalText}</p>
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <button type="button" className="era-btn-primary" disabled={personalSending} onClick={handlePersonalSend}>
                Подтвердить отправку
              </button>
              <button type="button" disabled={personalSending} onClick={() => setPersonalConfirming(false)}>
                Назад
              </button>
            </div>
          </div>
        )}
      </Card>

      <Card>
        <strong>Сообщение в чат</strong>
        <p style={{ margin: "0.25rem 0 0.5rem", color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
          Отправляется только в чаты, уже привязанные к боту через /bind.
        </p>
        {chatError && (
          <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: "0 0 0.5rem" }}>{chatError}</p>
        )}
        {chatResult && (
          <p style={{ color: "var(--era-text-muted)", fontSize: "0.8125rem", margin: "0 0 0.5rem" }}>{chatResult}</p>
        )}
        {!chatConfirming ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <select value={chatKey} onChange={(e) => setChatKey(e.target.value as ChatBroadcastKey)} style={inputStyle}>
              {Object.entries(CHAT_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
            <textarea
              placeholder="Текст сообщения"
              value={chatText}
              onChange={(e) => setChatText(e.target.value)}
              rows={3}
              style={inputStyle}
            />
            <button
              type="button"
              className="era-btn-primary"
              disabled={!chatText.trim()}
              onClick={() => setChatConfirming(true)}
            >
              Далее
            </button>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <p style={{ margin: 0 }}>
              <strong>{CHAT_LABELS[chatKey]}</strong>
            </p>
            <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{chatText}</p>
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <button type="button" className="era-btn-primary" disabled={chatSending} onClick={handleChatSend}>
                Подтвердить отправку
              </button>
              <button type="button" disabled={chatSending} onClick={() => setChatConfirming(false)}>
                Назад
              </button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
