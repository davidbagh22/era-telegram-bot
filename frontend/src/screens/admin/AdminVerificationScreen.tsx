import { useEffect, useMemo, useState } from "react";
import {
  fetchVerificationCampaign,
  remindVerificationSelection,
  removeVerificationSelection,
  retainVerificationSelection,
  startVerificationCampaign,
  type VerificationCampaign,
} from "../../api/adminVerification";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { MonoLabel } from "../../components/MonoLabel";
import { StatusBanner } from "../../components/StatusBanner";
import { useToast } from "../../components/Toast";

const PRESETS = [24, 48, 72, 120, 168] as const;

function durationLabel(hours: number): string {
  if (hours === 24) return "24 часа";
  if (hours === 48) return "48 часов";
  if (hours === 72) return "72 часа";
  if (hours === 120) return "5 дней";
  if (hours === 168) return "7 дней";
  return `${hours} ч.`;
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    pending: "Ожидает",
    sent: "Доставлено",
    failed: "Ошибка",
    blocked: "Бот заблокирован",
    unreachable: "Недоступен",
    skipped: "Не требуется",
    approved: "Одобрен",
    rejected: "Отклонён",
    needs_info: "Нужно уточнение",
    not_started: "Не зарегистрирован",
  };
  return labels[status] ?? status;
}

export function AdminVerificationScreen() {
  const [campaign, setCampaign] = useState<VerificationCampaign | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [duration, setDuration] = useState<number>(48);
  const [customDuration, setCustomDuration] = useState("");
  const [pin, setPin] = useState(true);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [filter, setFilter] = useState<"all" | "not_verified" | "unreachable">("all");
  const toast = useToast();

  async function refresh() {
    try {
      const next = await fetchVerificationCampaign();
      setCampaign(next);
      setError(false);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  const rows = useMemo(() => {
    const source = campaign?.rows ?? [];
    if (filter === "not_verified") {
      return source.filter((row) => ["not_started", "pending", "needs_info"].includes(row.registration_status));
    }
    if (filter === "unreachable") {
      return source.filter((row) => ["blocked", "unreachable", "failed"].includes(row.delivery_status));
    }
    return source;
  }, [campaign, filter]);

  const selectedIds = [...selected];

  async function start() {
    const requested = customDuration ? Number(customDuration) : duration;
    if (!Number.isInteger(requested) || requested < 1 || requested > 720) {
      toast.show("Укажите длительность от 1 до 720 часов", "error");
      return;
    }
    setBusy(true);
    try {
      const next = await startVerificationCampaign(requested, pin);
      setCampaign(next);
      setSelected(new Set());
      toast.show("Проверка состава запущена", "success");
    } catch {
      toast.show("Не удалось запустить проверку состава", "error");
    } finally {
      setBusy(false);
    }
  }

  async function runSelection(action: "remind" | "retain" | "remove") {
    if (!selectedIds.length) return;
    setBusy(true);
    try {
      const result = action === "remind"
        ? await remindVerificationSelection(selectedIds)
        : action === "retain"
          ? await retainVerificationSelection(selectedIds)
          : await removeVerificationSelection(selectedIds);
      toast.show(
        action === "remove"
          ? `Удалено из чата: ${result.changed}${result.failed ? ` · ошибок: ${result.failed}` : ""}`
          : action === "retain"
            ? `Оставлено в составе: ${result.changed}`
            : `Напоминаний отправлено: ${result.changed}${result.failed ? ` · ошибок: ${result.failed}` : ""}`,
        result.failed ? "error" : "success",
      );
      setSelected(new Set());
      setConfirmRemove(false);
      await refresh();
    } catch {
      toast.show("Действие не выполнено", "error");
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <p style={{ color: "var(--era-text-muted)" }}>Загружаем проверку состава…</p>;
  if (error) return <StatusBanner title="Не удалось загрузить проверку состава" description="Обновите экран и попробуйте ещё раз." />;

  if (!campaign || campaign.status === "completed") {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        {campaign && (
          <Card>
            <MonoLabel>ПОСЛЕДНЯЯ КАМПАНИЯ</MonoLabel>
            <strong style={{ display: "block", marginTop: ".35rem" }}>Завершена</strong>
            <span style={{ color: "var(--era-text-muted)" }}>
              {new Date(campaign.started_at).toLocaleString("ru-RU")} → {new Date(campaign.ends_at).toLocaleString("ru-RU")}
            </span>
          </Card>
        )}
        <Card gradient>
          <MonoLabel tone="violet">COMMUNITY VERIFICATION</MonoLabel>
          <h2 style={{ margin: ".4rem 0 0" }}>Проверить актуальный состав</h2>
          <p style={{ margin: ".5rem 0 0", color: "var(--era-text-secondary)" }}>
            Система отправит одно сообщение в общий чат и личные сообщения известным участникам. После окончания периода никто не удаляется автоматически.
          </p>
        </Card>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: ".55rem" }}>
          {PRESETS.map((hours) => (
            <button key={hours} type="button" className={duration === hours && !customDuration ? "era-btn-primary" : "era-btn-secondary"} onClick={() => { setDuration(hours); setCustomDuration(""); }}>
              {durationLabel(hours)}
            </button>
          ))}
        </div>
        <label style={{ display: "flex", flexDirection: "column", gap: ".3rem" }}>
          <span style={{ fontWeight: 800 }}>Custom, часов</span>
          <input type="number" min={1} max={720} value={customDuration} onChange={(event) => setCustomDuration(event.target.value)} placeholder="Например, 96" />
        </label>
        <label style={{ display: "flex", alignItems: "center", gap: ".55rem" }}>
          <input type="checkbox" checked={pin} onChange={(event) => setPin(event.target.checked)} />
          Закрепить сообщение в общем чате
        </label>
        <button type="button" className="era-btn-primary" disabled={busy} onClick={() => void start()}>
          {busy ? "Запускаем…" : "Запустить проверку"}
        </button>
      </div>
    );
  }

  const notVerified = campaign.rows.filter((row) => ["not_started", "pending", "needs_info"].includes(row.registration_status)).length;
  const unreachable = campaign.rows.filter((row) => ["blocked", "unreachable", "failed"].includes(row.delivery_status)).length;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      <Card gradient>
        <MonoLabel tone="violet">КАМПАНИЯ АКТИВНА</MonoLabel>
        <strong style={{ display: "block", marginTop: ".35rem", fontSize: "1.15rem" }}>{durationLabel(campaign.duration_hours)}</strong>
        <span style={{ display: "block", marginTop: ".25rem", color: "var(--era-text-secondary)" }}>
          До {new Date(campaign.ends_at).toLocaleString("ru-RU")} · {campaign.group_pinned ? "сообщение закреплено" : "без закрепа"}
        </span>
      </Card>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,minmax(0,1fr))", gap: ".5rem" }}>
        <Card style={{ padding: ".75rem" }}><strong>{campaign.rows.length}</strong><span style={{ display: "block", fontSize: ".72rem", color: "var(--era-text-muted)" }}>известно</span></Card>
        <Card style={{ padding: ".75rem" }}><strong>{notVerified}</strong><span style={{ display: "block", fontSize: ".72rem", color: "var(--era-text-muted)" }}>не завершили</span></Card>
        <Card style={{ padding: ".75rem" }}><strong>{unreachable}</strong><span style={{ display: "block", fontSize: ".72rem", color: "var(--era-text-muted)" }}>недоступны</span></Card>
      </div>

      <div style={{ display: "flex", gap: ".45rem", flexWrap: "wrap" }}>
        {(["all", "not_verified", "unreachable"] as const).map((key) => (
          <button key={key} type="button" className={filter === key ? "era-btn-primary" : "era-btn-secondary"} onClick={() => setFilter(key)}>
            {key === "all" ? "Все" : key === "not_verified" ? "Не верифицированы" : "Недоступны"}
          </button>
        ))}
      </div>

      {rows.length === 0 ? <EmptyState text="В этом сегменте никого нет." /> : (
        <div style={{ display: "flex", flexDirection: "column", gap: ".45rem" }}>
          {rows.map((row) => {
            const checked = selected.has(row.telegram_id);
            return (
              <button
                key={row.telegram_id}
                type="button"
                onClick={() => setSelected((previous) => {
                  const next = new Set(previous);
                  if (checked) next.delete(row.telegram_id); else next.add(row.telegram_id);
                  return next;
                })}
                style={{ width: "100%", border: 0, padding: 0, background: "transparent", textAlign: "left" }}
              >
                <Card style={{ padding: ".8rem", outline: checked ? "2px solid var(--era-violet)" : "none" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: ".6rem" }}>
                    <div style={{ minWidth: 0 }}>
                      <strong style={{ overflowWrap: "anywhere" }}>{row.name}</strong>
                      <span style={{ display: "block", marginTop: ".2rem", color: "var(--era-text-muted)", fontSize: ".75rem" }}>
                        {statusLabel(row.registration_status)} · DM: {statusLabel(row.delivery_status)}
                      </span>
                    </div>
                    <span aria-hidden="true">{checked ? "✓" : "○"}</span>
                  </div>
                </Card>
              </button>
            );
          })}
        </div>
      )}

      {selectedIds.length > 0 && (
        <Card style={{ position: "sticky", bottom: "calc(5.5rem + env(safe-area-inset-bottom,0px))", zIndex: 10 }}>
          <strong>{selectedIds.length} выбрано</strong>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: ".5rem", marginTop: ".7rem" }}>
            <button type="button" className="era-btn-secondary" disabled={busy} onClick={() => void runSelection("remind")}>Напомнить</button>
            <button type="button" className="era-btn-secondary" disabled={busy} onClick={() => void runSelection("retain")}>Оставить</button>
          </div>
          {!confirmRemove ? (
            <button type="button" className="era-btn-ghost" disabled={busy} onClick={() => setConfirmRemove(true)} style={{ width: "100%", marginTop: ".5rem" }}>Удалить выбранных из общего чата</button>
          ) : (
            <div style={{ marginTop: ".65rem", paddingTop: ".65rem", borderTop: "1px solid var(--era-border)" }}>
              <strong>Подтвердить массовое удаление?</strong>
              <p style={{ margin: ".3rem 0 .6rem", color: "var(--era-text-muted)", fontSize: ".78rem" }}>Это ручное решение. Профиль и история в ERA Platform не удаляются.</p>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: ".5rem" }}>
                <button type="button" className="era-btn-secondary" onClick={() => setConfirmRemove(false)}>Отмена</button>
                <button type="button" className="era-btn-primary" disabled={busy} onClick={() => void runSelection("remove")}>Подтвердить</button>
              </div>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
