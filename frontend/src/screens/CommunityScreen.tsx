import { useState } from "react";
import { ActionCell } from "../components/ActionCell";
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
  if (section === "opportunities") return "offers";
  if (section === "surveys" || section === "rewards" || section === "auctions") return section;
  return undefined;
}

function sectionHash(section: CommunitySection): string {
  return section === "leaderboard" ? "#/leaderboard" : `#/${section}`;
}

export function CommunityScreen({ initialSection = null, initialItemId = null }: CommunityScreenProps) {
  // Local state remains as a no-hash browser-preview fallback. In Telegram,
  // key navigation writes the hash so App.tsx and browser/Telegram Back stay
  // synchronized across reloads and history navigation.
  const [fallbackSection, setFallbackSection] = useState<CommunitySection | null>(initialSection);
  const section = initialSection ?? fallbackSection;

  const openSection = (next: CommunitySection) => {
    setFallbackSection(next);
    const hash = sectionHash(next);
    if (window.location.hash !== hash) window.location.hash = hash;
  };

  const backToCommunity = () => {
    setFallbackSection(null);
    if (window.location.hash !== "#/community") window.location.hash = "#/community";
  };

  if (section === "leaderboard") {
    return <LeaderboardScreen onBack={backToCommunity} />;
  }

  if (section) {
    return (
      <OpportunitiesScreen
        initialSection={toOpportunitySection(section)}
        initialItemId={initialItemId}
        onBack={backToCommunity}
      />
    );
  }

  return (
    <div className="era-page" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem", minWidth: 0 }}>
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
            <p style={{ margin: "0 0 0.35rem", color: "rgba(255,255,255,0.68)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>
              Среда роста
            </p>
            <h1 style={{ margin: 0, fontSize: "var(--era-text-3xl)", lineHeight: 1.08 }}>Сообщество</h1>
            <p style={{ margin: "0.5rem 0 0", color: "rgba(255,255,255,0.78)", maxWidth: 280 }}>
              Возможности, рейтинг и решения, которые двигают участников дальше.
            </p>
          </div>
        </div>
      </Card>

      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", minWidth: 0 }}>
        {SECTION_CARDS.map(({ value, label, description, Icon }) => (
          <ActionCell
            key={value}
            title={label}
            description={description}
            leading={<Icon width={21} height={21} />}
            onClick={() => openSection(value)}
          />
        ))}
      </div>
    </div>
  );
}
