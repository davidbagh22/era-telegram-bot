import type { Opportunity } from "../types/opportunity";
import { Card } from "./Card";
import { ChevronRightIcon, OpportunitiesIcon } from "./icons";

export function OpportunityCard({ opportunity, onClick }: { opportunity: Opportunity; onClick: () => void }) {
  return (
    <Card interactive onClick={onClick} ariaLabel={`${opportunity.title}. Подробнее`}>
      <div style={{ display: "flex", gap: "0.75rem", alignItems: "flex-start" }}>
        <span style={{ width: 42, height: 42, borderRadius: 14, display: "flex", alignItems: "center", justifyContent: "center", background: "var(--era-tint-gold)", color: "var(--era-gold-ink)", flexShrink: 0 }}><OpportunitiesIcon width={20} height={20} /></span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <p className="era-kicker" style={{ color: "var(--era-gold-ink)" }}>{opportunity.partner_name}</p>
          <strong style={{ display: "block", marginTop: "0.25rem", fontSize: "var(--era-text-lg)", overflowWrap: "anywhere" }}>{opportunity.title}</strong>
          {opportunity.reasons.length > 0 && <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>{opportunity.reasons[0]}</p>}
          <p style={{ margin: "0.5rem 0 0", fontSize: "var(--era-text-xs)", color: "var(--era-text-muted)" }}>{opportunity.point_cost > 0 ? `${opportunity.point_cost} баллов` : "Без списания баллов"}{opportunity.expires_at ? ` · до ${opportunity.expires_at.slice(0, 10)}` : ""}</p>
        </div>
        <ChevronRightIcon width={20} height={20} style={{ color: "var(--era-text-muted)", flexShrink: 0 }} />
      </div>
    </Card>
  );
}
