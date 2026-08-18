import { useCallback, useState } from "react";
import {
  completeCommunityVerificationCampaign,
  describeActionError,
  fetchCommunityVerificationNotRegistered,
  fetchCommunityVerificationStatus,
  remindCommunityVerificationSelected,
  removeCommunityVerificationSelected,
  sendCommunityVerificationLaunch,
  startCommunityVerificationCampaign,
} from "../../api/client";
import { BottomSheet } from "../../components/BottomSheet";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { MonoLabel } from "../../components/MonoLabel";
import { StatusBadge } from "../../components/StatusBadge";
import { useAsync } from "../../hooks/useAsync";
import type { CommunityVerificationLaunchWave } from "../../types/admin";

const WINDOW_OPTIONS: { hours: number; label: string }[] = [
  { hours: 24, label: "24 часа" },
  { hours: 48, label: "48 часов" },
  { hours: 72, label: "72 часа" },
  { hours: 120, label: "5 дней" },
  { hours: 168, label: "7 дней" },
];

const STATUS_LABELS: Record<string, string> = {
  not_started: "Не запущена",
  active: "Активна",
  completed: "Завершена",
};

const PIN_STATUS_LABELS: Record<string, string> = {
  posted: "опубликован сейчас",
  already_posted: "уже был опубликован раньше",
  failed: "не получилось опубликовать — проверьте права бота в чате",
  no_chat_bound: "общий чат не подключён",
};

function formatDateTime(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function MetricTile({ label, value, muted = false }: { label: string; value: number | string; muted?: boolean }) {
  return (
    <div
      style={{
        padding: "0.75rem",
        borderRadius: "var(--era-radius-md)",
        background: "var(--era-surface-2)",
        opacity: muted ? 0.7 : 1,
      }}
    >
      <MonoLabel>{label}</MonoLabel>
      <strong style={{ display: "block", marginTop: "0.25rem", fontSize: "1.2rem" }}>{value}</strong>
    </div>
  );
}

export function AdminCommunityVerificationScreen() {
  const [refreshKey, setRefreshKey] = useState(0);
  const status = useAsync(() => fetchCommunityVerificationStatus(), [refreshKey]);
  const notRegistered = useAsync(() => fetchCommunityVerificationNotRegistered(), [refreshKey]);
  const [windowHours, setWindowHours] = useState(72);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [lastWave, setLastWave] = useState<CommunityVerificationLaunchWave | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [lastActionSummary, setLastActionSummary] = useState<string | null>(null);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const toggleSelected = useCallback((telegramId: number) => {
    setSelected((previous) => {
      const next = new Set(previous);
      if (next.has(telegramId)) next.delete(telegramId);
      else next.add(telegramId);
      return next;
    });
  }, []);

  const handleRemindSelected = useCallback(async () => {
    const ids = Array.from(selected);
    if (ids.length === 0) return;
    setBusy(true);
    setActionError(null);
    try {
      const result = await remindCommunityVerificationSelected(ids);
      setLastActionSummary(`Напоминание отправлено: ${result.sent} из ${result.requested}`);
      setSelected(new Set());
      refresh();
    } catch (error) {
      setActionError(describeActionError(error));
    } finally {
      setBusy(false);
    }
  }, [selected, refresh]);

  const handleRemoveSelected = useCallback(async () => {
    const ids = Array.from(selected);
    if (ids.length === 0) return;
    setBusy(true);
    setActionError(null);
    try {
      const result = await removeCommunityVerificationSelected(ids);
      setLastActionSummary(`Удалено из чата: ${result.removed} из ${result.requested}`);
      setSelected(new Set());
      setConfirmingDelete(false);
      refresh();
    } catch (error) {
      setActionError(describeActionError(error));
    } finally {
      setBusy(false);
    }
  }, [selected, refresh]);

  const handleSendLaunch = useCallback(async () => {
    setBusy(true);
    setActionError(null);
    try {
      const wave = await sendCommunityVerificationLaunch();
      setLastWave(wave);
      refresh();
    } catch (error) {
      setActionError(describeActionError(error));
    } finally {
      setBusy(false);
    }
  }, [refresh]);

  const handleStart = useCallback(async () => {
    setBusy(true);
    setActionError(null);
    try {
      // ToR §76 DoD reads campaign-start as one admin action that produces
      // both the pin and the personal DMs -- chained here, but each half
      // stays independently idempotent server-side so a failure partway
      // through (e.g. this second call times out) is always safely retryable
      // via the "Отправить рассылку ещё раз" button below.
      await startCommunityVerificationCampaign(windowHours);
      const wave = await sendCommunityVerificationLaunch();
      setLastWave(wave);
      refresh();
    } catch (error) {
      setActionError(describeActionError(error));
    } finally {
      setBusy(false);
    }
  }, [windowHours, refresh]);

  const handleComplete = useCallback(async () => {
    setBusy(true);
    setActionError(null);
    try {
      await completeCommunityVerificationCampaign();
      refresh();
    } catch (error) {
      setActionError(describeActionError(error));
    } finally {
      setBusy(false);
    }
  }, [refresh]);

  if (status.status === "loading") {
    return <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>;
  }
  if (status.status === "error") {
    return <EmptyState text="Не удалось загрузить статус верификации." />;
  }

  const { campaign, segments } = status.data;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem", minWidth: 0 }}>
      <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
        Общий чат остаётся обычным — верификация не блокирует переписку, а даёт существующим
        участникам время зарегистрироваться и подтвердиться вручную.
      </p>

      {actionError && <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{actionError}</p>}

      <Card style={{ padding: "1.1rem", display: "flex", flexDirection: "column", gap: "0.85rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.75rem" }}>
          <div>
            <MonoLabel tone="violet">Кампания верификации</MonoLabel>
            <strong style={{ display: "block", marginTop: "0.3rem", fontSize: "1.05rem" }}>
              {STATUS_LABELS[campaign?.status ?? "not_started"]}
            </strong>
          </div>
          {campaign && <StatusBadge label={STATUS_LABELS[campaign.status]} tone={campaign.status === "active" ? "violet" : "neutral"} />}
        </div>

        {campaign ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.3rem", fontSize: "0.8125rem", color: "var(--era-text-muted)" }}>
            <span>Начата: {formatDateTime(campaign.started_at)}</span>
            <span>Окончание волны: {formatDateTime(campaign.ends_at)}</span>
            {campaign.completed_at && <span>Завершена: {formatDateTime(campaign.completed_at)}</span>}
          </div>
        ) : (
          <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
            Кампания ещё не запускалась.
          </p>
        )}

        {campaign?.status !== "active" ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
            <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
              {WINDOW_OPTIONS.map((option) => (
                <button
                  key={option.hours}
                  type="button"
                  onClick={() => setWindowHours(option.hours)}
                  style={{
                    padding: "0.4rem 0.7rem",
                    borderRadius: "var(--era-radius-pill)",
                    border: windowHours === option.hours ? "1px solid var(--era-violet)" : "1px solid var(--era-border)",
                    background: windowHours === option.hours ? "var(--era-tint-violet)" : "var(--era-surface)",
                    color: windowHours === option.hours ? "var(--era-violet)" : "var(--era-text)",
                    fontSize: "0.8rem",
                    fontWeight: 700,
                  }}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <button type="button" className="era-btn-primary" disabled={busy} onClick={handleStart}>
              Запустить первую волну
            </button>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              <button type="button" disabled={busy} onClick={handleSendLaunch}>
                Отправить рассылку ещё раз
              </button>
              <button type="button" disabled={busy} onClick={handleComplete}>
                Завершить волну вручную
              </button>
            </div>
            {lastWave && (
              <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.78rem" }}>
                Закреп: {PIN_STATUS_LABELS[lastWave.pin_status]} · Отправлено: {lastWave.sent} · Заблокировали
                бота: {lastWave.blocked} · Недоступны: {lastWave.unreachable}
                {lastWave.failed > 0 && ` · Ошибка отправки: ${lastWave.failed}`}
              </p>
            )}
          </div>
        )}
      </Card>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.65rem" }}>
        <MetricTile label="Участников Telegram-чата" value={segments.chat_members_total ?? "—"} />
        <MetricTile label="Известно системе" value={segments.known_to_system} />
        <MetricTile label="Подтверждены" value={segments.approved} />
        <MetricTile label="На рассмотрении" value={segments.pending} />
        <MetricTile label="Отклонены" value={segments.rejected} />
        <MetricTile label="Нужна информация" value={segments.needs_info} muted />
        <MetricTile label="Оповещены" value={segments.notified} />
        <MetricTile label="Недоступны для ЛС" value={segments.unreachable} />
      </div>
      {segments.not_registered_estimate !== null && (
        <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.78rem" }}>
          Оценочно не зарегистрировано: {segments.not_registered_estimate}. Это разница между
          составом чата и тем, что известно системе — не список конкретных людей.
        </p>
      )}

      <section style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.6rem" }}>
          <MonoLabel>Не зарегистрированы</MonoLabel>
          {selected.size > 0 && (
            <span style={{ color: "var(--era-text-muted)", fontSize: "0.78rem" }}>Выбрано: {selected.size}</span>
          )}
        </div>
        {lastActionSummary && (
          <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.78rem" }}>{lastActionSummary}</p>
        )}
        {notRegistered.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>}
        {notRegistered.status === "error" && <EmptyState text="Не удалось загрузить список." />}
        {notRegistered.status === "ready" && notRegistered.data.length === 0 && (
          <EmptyState text="Пока пусто — либо кампания не запускалась, либо все, кому написал бот, уже зарегистрированы." />
        )}
        {notRegistered.status === "ready" && notRegistered.data.length > 0 && (
          <>
            <Card style={{ padding: "0.5rem 0" }}>
              {notRegistered.data.map((entry, index) => (
                <label
                  key={entry.telegram_id}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    gap: "0.6rem",
                    padding: "0.6rem 1rem",
                    borderBottom: index < notRegistered.data.length - 1 ? "1px solid var(--era-border)" : "none",
                    cursor: "pointer",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
                    <input
                      type="checkbox"
                      checked={selected.has(entry.telegram_id)}
                      onChange={() => toggleSelected(entry.telegram_id)}
                      aria-label={`Выбрать ID ${entry.telegram_id}`}
                    />
                    <div>
                      <strong>ID {entry.telegram_id}</strong>
                      <div style={{ color: "var(--era-text-muted)", fontSize: "0.78rem" }}>
                        Отправлено: {formatDateTime(entry.notified_at)}
                      </div>
                    </div>
                  </div>
                  <StatusBadge label={entry.delivery_status} tone="neutral" />
                </label>
              ))}
            </Card>
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              <button type="button" disabled={busy || selected.size === 0} onClick={handleRemindSelected}>
                Напомнить выбранным
              </button>
              <button
                type="button"
                disabled={busy || selected.size === 0}
                onClick={() => setConfirmingDelete(true)}
                style={{ color: "var(--era-error)" }}
              >
                Удалить выбранных
              </button>
            </div>
          </>
        )}
        <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.78rem" }}>
          Напоминание уходит автоматически за 24 часа до конца волны, только тем, кто ещё не
          зарегистрировался. Оставить — просто ничего не выбирать.
        </p>
      </section>

      <BottomSheet open={confirmingDelete} onClose={() => setConfirmingDelete(false)} title="Удалить из чата">
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          <p style={{ margin: 0 }}>
            Выбранные аккаунты ({selected.size}) будут удалены из общего чата ЭРА. Это необратимо —
            им нужно будет отправить новый запрос на вступление, чтобы вернуться.
          </p>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button type="button" onClick={() => setConfirmingDelete(false)} style={{ flex: 1 }}>
              Отмена
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={handleRemoveSelected}
              style={{ flex: 1, background: "var(--era-error)", color: "#fff" }}
            >
              Подтвердить удаление
            </button>
          </div>
        </div>
      </BottomSheet>
    </div>
  );
}
