import { useState } from "react";
import { ActionCell } from "../components/ActionCell";
import { EditorialHero } from "../components/EditorialHero";
import { CommunityIcon, OpportunitiesIcon, SurveyIcon } from "../components/icons";
import { LeaderboardScreen } from "./LeaderboardScreen";
import { MediaScreen } from "./MediaScreen";
import { OpportunitiesScreen, type OpportunitiesSection } from "./OpportunitiesScreen";

// Legacy rewards/auctions remain routable so old notifications/links do not
// break, but they are intentionally no longer advertised as primary community
// navigation: the new Opportunities model treats recognition points as
// reputation, not a spendable store currency.
export type CommunitySection = "opportunities" | "leaderboard" | "surveys" | "media" | "rewards" | "auctions";

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
    description: "Документы, заявки и следующие точки роста",
    Icon: OpportunitiesIcon,
  },
  {
    value: "media",
    label: "Медиа",
    description: "Возьми реальную задачу, войди в команду и собери портфолио",
    Icon: CommunityIcon,
  },
  {
    value: "leaderboard",
    label: "Рейтинг",
    description: "Ваш прогресс и активные участники ЭРА",
    Icon: CommunityIcon,
  },
  {
    value: "surveys",
    label: "Опросы",
    description: "Быстро влиять на решения команды",
    Icon: SurveyIcon,
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
  const [fallbackSection, setFallbackSection] = useState<CommunitySection | null>(initialSection);
  const hasRouteHash = window.location.hash.startsWith("#/");
  const section = hasRouteHash ? initialSection : initialSection ?? fallbackSection;

  const openSection = (next: CommunitySection) => {
    setFallbackSection(next);
    const hash = sectionHash(next);
    if (window.location.hash !== hash) window.location.hash = hash;
  };

  const backToCommunity = () => {
    setFallbackSection(null);
    if (window.location.hash !== "#/community") window.location.hash = "#/community";
  };

  if (section === "leaderboard") return <LeaderboardScreen onBack={backToCommunity} />;
  if (section === "media") return <MediaScreen onBack={backToCommunity} />;

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
      <EditorialHero
        eyebrow="Среда роста"
        title="Сообщество"
        description="Здесь активность превращается в опыт, статус и следующие возможности."
        glow="signal"
      >
        <span
          aria-hidden="true"
          style={{
            width: 46,
            height: 46,
            borderRadius: "50%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "var(--era-tint-violet)",
            color: "var(--era-violet)",
          }}
        >
          <CommunityIcon width={23} height={23} />
        </span>
      </EditorialHero>

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
