import { Card } from "../../components/Card";

/** Clear thresholds for branded certificates / thank-you letters (owner policy 17.11.2026). */
const LADDER = [
  { issuer: "ЭРА", points: 2000, label: "Сертификат ЭРА" },
  { issuer: "Дом Москвы", points: 5000, label: "Сертификат Дома Москвы" },
  { issuer: "Русский дом", points: 5000, label: "Сертификат Русского дома" },
  { issuer: "КСООРС", points: 5000, label: "Сертификат КСООРС" },
  { issuer: "АСРВВА", points: 5000, label: "Сертификат АСРВВА" },
] as const;

export function CertificatesPanel({ pointsBalance = 0 }: { pointsBalance?: number }) {
  return (
    <section aria-label="Сертификаты и благодарственные письма" style={{ display: "grid", gap: "0.65rem" }}>
      <div>
        <p style={{ margin: 0, fontSize: "0.72rem", fontWeight: 850, letterSpacing: "0.06em", color: "var(--era-text-muted)", textTransform: "uppercase" }}>
          Документы
        </p>
        <h2 style={{ margin: "0.25rem 0 0", fontSize: "var(--era-text-xl)" }}>Сертификаты и благодарности</h2>
        <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)", fontSize: "0.84rem", lineHeight: 1.45 }}>
          Баллы копятся в профиле и открывают заявление. Когда порог набран — подайте заявку; решение принимает админ.
        </p>
      </div>
      <div style={{ display: "grid", gap: "0.45rem" }}>
        {LADDER.map((item) => {
          const ready = pointsBalance >= item.points;
          return (
            <Card key={item.label} style={{ padding: "0.85rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "flex-start" }}>
                <div style={{ minWidth: 0 }}>
                  <strong style={{ display: "block" }}>{item.label}</strong>
                  <span style={{ display: "block", marginTop: 3, color: "var(--era-text-muted)", fontSize: "0.78rem" }}>
                    {item.issuer} · порог {item.points.toLocaleString("ru-RU")} баллов
                  </span>
                </div>
                <button
                  type="button"
                  className={ready ? "era-btn-primary" : undefined}
                  disabled={!ready}
                  onClick={() => {
                    window.location.hash = "#/opportunities";
                  }}
                  style={{ flexShrink: 0, minHeight: "2.5rem", opacity: ready ? 1 : 0.55 }}
                >
                  {ready ? "Подать заявление" : "Ещё рано"}
                </button>
              </div>
            </Card>
          );
        })}
      </div>
    </section>
  );
}
