import { fetchEraPro } from "../api/eraPro";
import { useAsync } from "../hooks/useAsync";
import { Card } from "./Card";
import { MonoLabel } from "./MonoLabel";
import { StatusBadge } from "./StatusBadge";

function formatPoints(value: number): string {
  return new Intl.NumberFormat("ru-RU").format(value);
}

const STATUS = {
  locked: ["Закрыто", "neutral"],
  available: ["Заявка доступна", "success"],
  submitted: ["На рассмотрении", "violet"],
  needs_info: ["Нужно дополнить", "warning"],
  approved: ["Вы в ЭРА PRO", "success"],
  declined: ["Можно подать снова", "neutral"],
} as const;

export function EraProOpportunityCard() {
  const state = useAsync(() => fetchEraPro(), []);

  const open = () => {
    if (window.location.hash !== "#/era-pro") window.location.hash = "#/era-pro";
  };

  if (state.status === "loading") {
    return (
      <Card gradient>
        <MonoLabel tone="violet">ЭРА PRO</MonoLabel>
        <strong style={{ display: "block", marginTop: "0.3rem" }}>Закрытое лидерское и наставническое сообщество</strong>
        <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)", fontSize: "0.82rem" }}>Проверяем ваш текущий уровень…</p>
      </Card>
    );
  }

  if (state.status === "error") {
    return (
      <Card onClick={open}>
        <MonoLabel tone="violet">ЭРА PRO</MonoLabel>
        <strong style={{ display: "block", marginTop: "0.3rem" }}>Закрытое лидерское и наставническое сообщество</strong>
        <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)", fontSize: "0.82rem" }}>Откройте раздел, чтобы проверить доступ.</p>
      </Card>
    );
  }

  const data = state.data;
  const percent = Math.min(100, Math.round((data.points / Math.max(1, data.threshold)) * 100));
  const [label, tone] = STATUS[data.status];

  return (
    <Card gradient onClick={open} style={{ borderColor: "rgba(99,44,255,.2)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: "0.7rem", alignItems: "flex-start" }}>
        <div style={{ minWidth: 0 }}>
          <MonoLabel tone="violet">ЭРА PRO</MonoLabel>
          <strong style={{ display: "block", marginTop: "0.32rem", fontSize: "1.05rem", lineHeight: 1.35 }}>Закрытое лидерское и наставническое сообщество</strong>
        </div>
        <StatusBadge label={label} tone={tone} />
      </div>

      <p style={{ margin: "0.5rem 0 0", color: "var(--era-text-secondary)", fontSize: "0.82rem", lineHeight: 1.5 }}>
        Наставники, эксперты, дипломаты, предприниматели, ораторы, руководители и представители разных профессиональных сфер.
      </p>

      <div style={{ marginTop: "0.75rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem", color: "var(--era-text-muted)", fontSize: "0.78rem" }}>
          <span>{formatPoints(data.points)} / {formatPoints(data.threshold)}</span>
          <span>{percent}%</span>
        </div>
        <div style={{ height: 7, marginTop: "0.3rem", borderRadius: 999, overflow: "hidden", background: "var(--era-ring-track)" }}>
          <div style={{ width: `${percent}%`, height: "100%", background: "var(--era-gradient-signal)" }} />
        </div>
      </div>

      <p style={{ margin: "0.5rem 0 0", color: "var(--era-text-muted)", fontSize: "0.78rem" }}>
        {data.status === "locked" && `Ещё ${formatPoints(data.remaining_points)} баллов до подачи заявки.`}
        {data.status === "available" && "Порог достигнут. Можно подать заявку — баллы не списываются."}
        {data.status === "submitted" && "Заявка рассматривается командой ЭРА."}
        {data.status === "needs_info" && "Откройте ЭРА PRO и дополните заявку."}
        {data.status === "approved" && "Закрытый уровень открыт."}
        {data.status === "declined" && "Баллы сохранены. Новую заявку можно подать позже."}
      </p>
      <span style={{ display: "block", marginTop: "0.7rem", color: "var(--era-violet)", fontWeight: 850, fontSize: "0.84rem" }}>
        {data.status === "locked" ? "Как приблизиться" : data.status === "available" ? "Подать заявку" : "Открыть ЭРА PRO"} →
      </span>
    </Card>
  );
}
