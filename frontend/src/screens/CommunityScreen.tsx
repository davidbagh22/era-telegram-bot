import { useEffect } from "react";
import { LeaderboardScreen } from "./LeaderboardScreen";
import { MediaScreen } from "./MediaScreen";
import { OpportunitiesScreen, type OpportunitiesSection } from "./OpportunitiesScreen";

// `community` remains only as a compatibility shell for old deep links.
// Participant navigation now treats Opportunities as the real fifth domain.
export type CommunitySection = "opportunities" | "leaderboard" | "surveys" | "media" | "rewards" | "auctions";

interface CommunityScreenProps {
  initialSection?: CommunitySection | null;
  initialItemId?: number | null;
  initialMediaRoute?: "guide" | null;
}

function toOpportunitySection(section: CommunitySection | null): OpportunitiesSection {
  if (section === "surveys" || section === "rewards" || section === "auctions") return section;
  return "offers";
}

export function CommunityScreen({ initialSection = null, initialItemId = null, initialMediaRoute = null }: CommunityScreenProps) {
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

  if (initialSection === "leaderboard") return <LeaderboardScreen onBack={backToOpportunities} />;
  if (initialSection === "media") return <MediaScreen onBack={backToOpportunities} initialView={initialMediaRoute} />;

  return (
    <OpportunitiesScreen
      initialSection={toOpportunitySection(initialSection)}
      initialItemId={initialItemId}
    />
  );
}
