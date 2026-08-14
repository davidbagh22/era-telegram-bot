import { useCallback, useEffect, useState } from "react";
import type { CSSProperties } from "react";
import {
  describeActionError,
  fetchBroadcastAudienceOptions,
  fetchBroadcastPreviewCount,
  sendChatBroadcast,
  sendPersonalBroadcast,
} from "../../../api/client";
import { BottomSheet } from "../../../components/BottomSheet";
import { Card } from "../../../components/Card";
import { StatusBadge } from "../../../components/StatusBadge";
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

const pickerButtonStyle = {
  width: "100%",
  textAlign: "left",
  fontFamily: "var(--era-font-body)",
  minHeight: "2.75rem",
  padding: "0.625rem 0.75rem",
  borderRadius: "0.75rem",
  border: "1px solid var(--era-border)",
  background: "var(--era-surface)",
  color: "var(--era-text)",
} satisfies CSSProperties;

const optionRowStyle = {
  display: "flex",
  alignItems: "center",
  gap: "0.5rem",
  width: "100%",
  textAlign: "left",
  fontFamily: "var(--era-font-body)",
  fontSize: "0.9375rem",
  padding: "0.625rem 0.25rem",
  border: "none",
  borderBottom: "1px solid var(--era-border)",
  background: "transparent",
  color: "var(--era-text)",
} satisfies CSSProperties;

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
// 2026-08 master spec section 33: audience/destination pickers use the same
// BottomSheet chip pattern as OpenTasksTab's chat-destination picker, and
// the confirm step shows a live recipient count fetched from
// /broadcast/preview-count before anything actually sends.
export function BroadcastPanel() {
  const options = useAsync(() => fetchBroadcastAudienceOptions(), []);

  const [audience, setAudience] = useState<BroadcastAudience>("all");
  const [filterValue, setFilterValue] = useState("");
  const [personalText, setPersonalText] = useState("");
  const [showAudienceSheet, setShowAudienceSheet] = useState(false);
  const [personalConfirming, setPersonalConfirming] = useState(false);
  const [personalSending, setPersonalSending] = useState(false);
  const [personalResult, setPersonalResult] = useState<{
    total: number;
    sent: number;
    failed: number;
    duplicates: number;
  } | null>(null);
  const [personalError, setPersonalError] = useState<string | null>(null);
  const [recipientCount, setRecipientCount] = useState<number | null>(null);
  const [countLoading, setCountLoading] = useState(false);

  const [chatKey, setChatKey] = useState<ChatBroadcastKey>("general");
  const [showChatSheet, setShowChatSheet] = useState(false);
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

  // Live recipient count -- refetches whenever the audience or its filter
  // changes, so the admin sees "Получателей: N" while still picking rather
  // than only after committing to send.
  useEffect(() => {
    if (needsFilter && !filterValue) {
      setRecipientCount(null);
      return;
    }
    let cancelled = false;
    setCountLoading(true);
    fetchBroadcastPreviewCount(audience, needsFilter ? filterValue : null)
      .then((result) => {
        if (!cancelled) setRecipientCount(result.count);
      })
      .catch(() => {
        if (!cancelled) setRecipientCount(null);
      })
      .finally(() => {
        if (!cancelled) setCountLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [audience, needsFilter, filterValue]);

  const filterValueLabel =
    audience === "city"
      ? filterValue
      : filterOptions.find((option) => option.value === filterValue)?.label ?? filterValue;

  const handlePersonalSend = useCallback(async () => {
    setPersonalSending(true);
    setPersonalError(null);
    try {
      const result = await sendPersonalBroadcast({
        audience,
        filter_value: needsFilter ? filterValue || null : null,
        text: personalText.trim(),
      });
      setPersonalResult(result);
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
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.375rem", margin: "0 0 0.5rem" }}>
            <StatusBadge label={`Получателей: ${personalResult.total}`} />
            <StatusBadge label={`Доставлено: ${personalResult.sent}`} tone="violet" />
            {personalResult.failed > 0 && (
              <StatusBadge label={`Ошибок: ${personalResult.failed}`} tone="red" />
            )}
            {personalResult.duplicates > 0 && (
              <StatusBadge label={`Дублей: ${personalResult.duplicates}`} />
            )}
          </div>
        )}
        {!personalConfirming ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <button type="button" style={pickerButtonStyle} onClick={() => setShowAudienceSheet(true)}>
              {AUDIENCE_LABELS[audience]}
              {needsFilter && filterValueLabel ? ` · ${filterValueLabel}` : ""}
            </button>
            <p style={{ margin: 0, fontSize: "0.8125rem", color: "var(--era-text-muted)" }}>
              {countLoading
                ? "Считаем получателей…"
                : recipientCount !== null
                  ? `Получателей: ${recipientCount}`
                  : needsFilter
                    ? "Выберите значение фильтра, чтобы увидеть число получателей."
                    : ""}
            </p>
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
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
              <strong>{AUDIENCE_LABELS[audience]}</strong>
              {needsFilter && filterValueLabel ? <span>· {filterValueLabel}</span> : null}
              {recipientCount !== null && <StatusBadge label={`Получателей: ${recipientCount}`} tone="violet" />}
            </div>
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

      <BottomSheet open={showAudienceSheet} onClose={() => setShowAudienceSheet(false)} title="Выберите аудиторию">
        <div style={{ display: "flex", flexDirection: "column" }}>
          {Object.entries(AUDIENCE_LABELS).map(([value, label]) => (
            <button
              key={value}
              type="button"
              style={optionRowStyle}
              onClick={() => {
                setAudience(value as BroadcastAudience);
                setFilterValue("");
              }}
            >
              <input type="radio" readOnly checked={audience === value} />
              {label}
            </button>
          ))}
          {needsFilter && (
            <div style={{ marginTop: "0.75rem" }}>
              {audience === "city" ? (
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
              )}
            </div>
          )}
          <button
            type="button"
            className="era-btn-primary"
            style={{ marginTop: "0.75rem" }}
            onClick={() => setShowAudienceSheet(false)}
          >
            Готово
          </button>
        </div>
      </BottomSheet>

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
            <button type="button" style={pickerButtonStyle} onClick={() => setShowChatSheet(true)}>
              {CHAT_LABELS[chatKey]}
            </button>
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

      <BottomSheet open={showChatSheet} onClose={() => setShowChatSheet(false)} title="Выберите чат">
        <div style={{ display: "flex", flexDirection: "column" }}>
          {Object.entries(CHAT_LABELS).map(([value, label]) => (
            <button
              key={value}
              type="button"
              style={optionRowStyle}
              onClick={() => {
                setChatKey(value as ChatBroadcastKey);
                setShowChatSheet(false);
              }}
            >
              <input type="radio" readOnly checked={chatKey === value} />
              {label}
            </button>
          ))}
        </div>
      </BottomSheet>
    </div>
  );
}
