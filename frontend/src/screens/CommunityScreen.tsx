import { useEffect } from "react";
import { fetchMe } from "../api/client";
import { SkeletonList } from "../components/Skeleton";
import { useAsync } from "../hooks/useAsync";
import { LeaderboardScreen } from "./LeaderboardScreen";
import { MediaScreen } from "./MediaScreen";
import { OpportunitiesScreen, type OpportunitiesSection } from "./OpportunitiesScreen";
import { DiscoverScreen } from "./DiscoverScreen";
import { LiteratureScreen } from "./LiteratureScreen";
import { GamesScreen } from "./GamesScreen";
import { EmptyState } from "../components/EmptyState";

// `community` remains only as a compatibility shell for old deep links.
// Participant navigation now treats Opportunities as the real fifth domain.
export type CommunitySection = "opportunities" | "leaderboard" | "surveys" | "media" | "rewards" | "auctions" | "leisure" | "points" | "literature" | "games";

interface CommunityScreenProps {
  initialSection?: CommunitySection | null;
  initialItemId?: number | null;
  initialMediaRoute?: "guide" | "files" | "era" | "ksoors" | null;
}

function toOpportunitySection(section: CommunitySection | null): OpportunitiesSection {
  if (section === "surveys" || section === "rewards" || section === "auctions") return section;
  return "offers";
}

export function CommunityScreen({ initialSection = null, initialItemId = null, initialMediaRoute = null }: CommunityScreenProps) {
  const me = useAsync(fetchMe, []);

  useEffect(() => {
    // Old #/community bookmarks should not reopen a redundant menu. Canonicalize
    // them to the actual participant destination while keeping historic links alive.
    if (!initialSection && window.location.hash === "#/community") {
      window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}#/opportunities`);
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    }
  }, [initialSection]);

  const backToOpportunities = () => {
    if (window.location.hash !== "#/opportunities") window.location.hash = "#/opportunities";
  };

  if (me.status === "loading") {
    return (
      <div className="era-page" style={{ padding: "1.25rem" }}>
        <SkeletonList count={2} />
      </div>
    );
  }
  if (me.status === "error") return <EmptyState text="Не удалось загрузить открытия." actionLabel="Повторить" onAction={me.reload} />;
  if (initialSection === "literature") return <LiteratureScreen userId={me.data.id} number={initialItemId} />;
  if (initialSection === "games") return <GamesScreen />;
  if (!initialSection || initialSection === "leisure" || initialSection === "points") {
    return <DiscoverScreen user={me.data} category={initialSection === "leisure" ? "leisure" : initialSection === "points" ? "points" : "offers"} />;
  }

  if (me.status === "ready") {
    const featureBySection: Partial<Record<CommunitySection, keyof typeof me.data.features>> = {
      surveys: "surveys",
      media: "media",
      rewards: "rewards",
      auctions: "auctions",
    };
    const feature = initialSection ? featureBySection[initialSection] : undefined;
    if (feature && !me.data.features[feature]) {
      return <OpportunitiesScreen />;
    }
  }

  if (initialSection === "leaderboard") return <LeaderboardScreen onBack={backToOpportunities} />;
  if (initialSection === "media") return <MediaScreen onBack={backToOpportunities} initialView={initialMediaRoute} />;

  return (
    <OpportunitiesScreen
      initialSection={toOpportunitySection(initialSection)}
      initialItemId={initialItemId}
      onBack={() => { window.location.hash = "#/discover"; }}
    />
  );
}
