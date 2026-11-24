import { useState } from "react";
import { fetchHome, fetchOpportunities } from "../../api/client";
import { Card } from "../../components/Card";
import { useAsync } from "../../hooks/useAsync";

/** Clear thresholds for branded certificates / thank-you letters (owner policy 17.11.2026). */
const LADDER = [
  { issuer: "ЭРА", points: 2000, label: "Сертификат ЭРА", catalogTitle: "Сертификат участника ЭРА" },
  { issuer: "Дом Москвы", points: 5000, label: "Сертификат Дома Москвы", catalogTitle: "Сертификат Дома Москвы" },
  { issuer: "Русский дом", points: 5000, label: "Сертификат Русского дома", catalogTitle: "Сертификат Русского дома" },
  { issuer: "КСООРС", points: 5000, label: "Сертификат КСООРС", catalogTitle: "Сертификат КСООРС" },
  { issuer: "АСРВВА", points: 5000, label: "Сертификат АСРВВА", catalogTitle: "Сертификат АСРВВА" },
] as const;

/** Ladder short names → recognition catalog partner.name values. */
const ISSUER_ALIASES: Record<(typeof LADDER)[number]["issuer"], string> = {
  "ЭРА": "ЭРА",
  "Дом Москвы": "Дом Москвы в Ереване",
  "Русский дом": "Русский дом",
  "КСООРС": "КСООРС Армении",
  "АСРВВА": "Ассоциация студентов российских вузов в Армении",
};

type LadderItem = (typeof LADDER)[number];

async function openCertificateApplication(item: LadderItem): Promise<void> {
  const offers = await fetchOpportunities({
    scope: "all",
    state: "available",
    issuer: ISSUER_ALIASES[item.issuer],
    type: "certificate",
    sort: "by_organization",
  });
  const match =
    offers.find((offer) => offer.title === item.catalogTitle)
    ?? offers.find((offer) => offer.required_points === item.points && offer.eligible)
    ?? offers.find((offer) => offer.eligible)
    ?? offers[0];
  if (match) {
    window.location.hash = `#/opportunities/${match.id}`;
    return;
  }
  document.getElementById("opportunities-offers")?.scrollIntoView({ block: "start", behavior: "smooth" });
}

export function CertificatesPanel() {
  const home = useAsync(() => fetchHome(), []);
  const pointsBalance = home.status === "ready" ? home.data.points_balance : 0;
  const [pendingLabel, setPendingLabel] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const handleApply = async (item: LadderItem) => {
    setPendingLabel(item.label);
    setActionError(null);
    try {
      await openCertificateApplication(item);
    } catch {
      setActionError("Не удалось открыть заявление. Попробуйте ещё раз.");
    } finally {
      setPendingLabel(null);
    }
  };

  return (
    <section aria-label="Сертификаты и благодарственные письма" style={{ display: "grid", gap: "0.65rem" }}>
      <div>
        <p style={{ margin: 0, fontSize: "0.72rem", fontWeight: 850, letterSpacing: "0.06em", color: "var(--era-text-muted)", textTransform: "uppercase" }}>
          Документы
        </p>
        <h2 style={{ margin: "0.25rem 0 0", fontSize: "var(--era-text-xl)" }}>Сертификаты и благодарности</h2>
        <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)", fontSize: "0.84rem", lineHeight: 1.45 }}>
          Баллы копятся в профиле и открывают заявление. Сейчас у вас{" "}
          {home.status === "ready" ? pointsBalance.toLocaleString("ru-RU") : "…"} баллов.
        </p>
      </div>
      {actionError && <p style={{ margin: 0, color: "var(--era-error)", fontSize: "0.82rem" }}>{actionError}</p>}
      <div style={{ display: "grid", gap: "0.45rem" }}>
        {LADDER.map((item) => {
          const ready = pointsBalance >= item.points;
          const pending = pendingLabel === item.label;
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
                  disabled={!ready || home.status !== "ready" || pendingLabel !== null}
                  onClick={() => { void handleApply(item); }}
                  style={{ flexShrink: 0, minHeight: "2.5rem", opacity: ready ? 1 : 0.55 }}
                >
                  {!ready ? "Ещё рано" : pending ? "Открываем…" : "Подать заявление"}
                </button>
              </div>
            </Card>
          );
        })}
      </div>
    </section>
  );
}
