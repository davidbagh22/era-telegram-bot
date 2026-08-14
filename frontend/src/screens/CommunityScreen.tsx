import { useState } from "react";
import { Card } from "../components/Card";
import { AuctionIcon, CommunityIcon, OpportunitiesIcon, RewardIcon, SurveyIcon } from "../components/icons";
import { LeaderboardScreen } from "./LeaderboardScreen";
import { OpportunitiesScreen, type OpportunitiesSection } from "./OpportunitiesScreen";

export type CommunitySection = "opportunities" | "leaderboard" | "surveys" | "rewards" | "auctions";

interface CommunityScreenProps {
  initialSection?: CommunitySection | null;
  initialItemId?: number | null;
}

const SECTION_CARDS: {
  value: CommunitySection;
  label: string;
  description: string;
  Icon: typeof CommunityIcon;
}[] = [
  {
    value: "opportunities",
    label: "Возможности",
    description: "Предложения, заявки и новые точки роста",
    Icon: OpportunitiesIcon,
  },
  {
    value: "leaderboard",
    label: "Рейтинг",
    description: "Ваше место и активные участники ЭРА",
    Icon: CommunityIcon,
  },
  {
    value: "surveys",
    label: "Опросы",
    description: "Быстро влиять на решения команды",
    Icon: SurveyIcon,
  },
  {
    value: "rewards",
    label: "Награды",
    description: "Каталог, где баллы превращаются в статус",
    Icon: RewardIcon,
  },
  {
    value: "auctions",
    label: "Аукционы",
    description: "Редкие возможности за баллы",
    Icon: AuctionIcon,
  },
];

function toOpportunitySection(section: CommunitySection): OpportunitiesSection | undefined {
  if (section === "opportunities") {
    return "offers";
  }
  if (section === "surveys" || section === "rewards" || section === "auctions") {
    return section;
  }
  return undefined;
}

export function CommunityScreen({ initialSection = null, initialItemId = null }: CommunityScreenProps) {
  const [section, setSection] = useState<CommunitySection | null>(initialSection);

  if (section === "leaderboard") {
    return <LeaderboardScreen onBack={() => setSection(null)} />;
  }

  if (section) {
    return (
      <OpportunitiesScreen
        initialSection={toOpportunitySection(section)}
        initialItemId={section === "opportunities" ? initialItemId : null}
        onBack={() => setSection(null)}
      />
    );
  }

  return (
    <div
      className="era-page"
      style={{
        padding: "1.25rem",
        display: "flex",
        flexDirection: "column",
        gap: "1rem",
      }}
    >
      <Card gradient style={{ position: "relative", overflow: "hidden", minHeight: 164 }}>
        <div
          aria-hidden="true"
          style={{
            position: "absolute",
            right: -28,
            top: -34,
            width: 150,
            height: 150,
            borderRadius: "50%",
            background: "rgba(255,255,255,0.1)",
            border: "1px solid rgba(255,255,255,0.16)",
          }}
        />
        <div style={{ position: "relative", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          <span
            style={{
              width: 46,
              height: 46,
              borderRadius: "50%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: "rgba(255,255,255,0.14)",
            }}
            aria-hidden="true"
          >
            <CommunityIcon width={23} height={23} />
          </span>
          <div>
            <p
              style={{
                margin: "0 0 0.35rem",
                color: "rgba(255,255,255,0.68)",
                fontSize: "var(--era-text-xs)",
                fontWeight: 800,
                textTransform: "uppercase",
              }}
            >
              Среда роста
            </p>
            <h1 style={{ margin: 0, fontSize: "var(--era-text-3xl)", lineHeight: 1.08 }}>
              Сообщество
            </h1>
            <p style={{ margin: "0.5rem 0 0", color: "rgba(255,255,255,0.78)", maxWidth: 280 }}>
              Возможности, рейтинг и решения, которые двигают участников дальше.
            </p>
          </div>
        </div>
      </Card>

      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        {SECTION_CARDS.map(({ value, label, description, Icon }) => (
          <Card key={value}>
            <button
              type="button"
              onClick={() => setSection(value)}
              style={{
                all: "unset",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: "0.875rem",
                width: "100%",
              }}
            >
              <span
                style={{
                  width: 44,
                  height: 44,
                  borderRadius: "50%",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flexShrink: 0,
                  background: "var(--era-tint-violet)",
                  color: "var(--era-violet)",
                }}
                aria-hidden="true"
              >
                <Icon width={21} height={21} />
              </span>
              <span style={{ flex: 1, minWidth: 0 }}>
                <strong style={{ display: "block", fontSize: "var(--era-text-lg)" }}>{label}</strong>
                <span style={{ display: "block", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>
                  {description}
                </span>
              </span>
              <span aria-hidden="true" style={{ color: "var(--era-text-muted)" }}>
                →
              </span>
            </button>
          </Card>
        ))}
      </div>
    </div>
  );
}
