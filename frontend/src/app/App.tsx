import { useEffect, useState } from "react";
import type { TabKey } from "../components/BottomNavigation";
import { useAuth } from "../hooks/useAuth";
import { AdminLayout } from "../layouts/AdminLayout";
import { LeaderLayout } from "../layouts/LeaderLayout";
import { UserLayout } from "../layouts/UserLayout";
import { AdminScreen } from "../screens/AdminScreen";
import { ActivityScreen } from "../screens/ActivityScreen";
import { AuthErrorScreen } from "../screens/AuthErrorScreen";
import { BlockedScreen } from "../screens/BlockedScreen";
import { CommunityScreen, type CommunitySection } from "../screens/CommunityScreen";
import { EventsScreen } from "../screens/EventsScreen";
import { HomeScreen } from "../screens/HomeScreen";
import { LeaderScreen } from "../screens/LeaderScreen";
import { PendingScreen } from "../screens/PendingScreen";
import { ProfileScreen } from "../screens/ProfileScreen";
import { ProjectsScreen } from "../screens/ProjectsScreen";
import type { MiniAppUserSummary } from "../types/auth";

type LegacyActivitySection = "tasks" | "calendar" | "history";

interface DeepLink {
  tab: TabKey;
  projectId: number | null;
  activitySection: LegacyActivitySection | null;
  communitySection: CommunitySection | null;
  itemId: number | null;
}

const TAB_HASH: Record<TabKey, string> = {
  home: "#/home",
  projects: "#/projects",
  events: "#/events",
  community: "#/community",
  profile: "#/profile",
};

function parseOptionalId(value: string | undefined): number | null {
  if (!value) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function parseDeepLink(): DeepLink | null {
  const hash = window.location.hash;

  const projectMatch = hash.match(/^#\/(?:admin\/)?projects\/(\d+)\/?$/);
  if (projectMatch) {
    const projectId = parseOptionalId(projectMatch[1]);
    if (projectId !== null) {
      return { tab: "projects", projectId, activitySection: null, communitySection: null, itemId: null };
    }
  }
  if (/^#\/projects\/?$/.test(hash)) {
    return { tab: "projects", projectId: null, activitySection: null, communitySection: null, itemId: null };
  }

  const activityMatch = hash.match(/^#\/(tasks|calendar|history)(?:\/(\d+))?\/?$/);
  if (activityMatch) {
    return {
      tab: "home",
      projectId: null,
      activitySection: activityMatch[1] as LegacyActivitySection,
      communitySection: null,
      itemId: parseOptionalId(activityMatch[2]),
    };
  }

  const eventMatch = hash.match(/^#\/events(?:\/(\d+))?\/?$/);
  if (eventMatch) {
    return {
      tab: "events",
      projectId: null,
      activitySection: null,
      communitySection: null,
      itemId: parseOptionalId(eventMatch[1]),
    };
  }

  const communityMatch = hash.match(/^#\/(opportunities|auctions|rewards|surveys)(?:\/(\d+))?\/?$/);
  if (communityMatch) {
    return {
      tab: "community",
      projectId: null,
      activitySection: null,
      communitySection: communityMatch[1] as CommunitySection,
      itemId: parseOptionalId(communityMatch[2]),
    };
  }

  if (/^#\/leaderboard\/?$/.test(hash)) {
    return { tab: "community", projectId: null, activitySection: null, communitySection: "leaderboard", itemId: null };
  }

  if (/^#\/community\/?$/.test(hash)) {
    return { tab: "community", projectId: null, activitySection: null, communitySection: null, itemId: null };
  }

  if (/^#\/profile\/?$/.test(hash)) {
    return { tab: "profile", projectId: null, activitySection: null, communitySection: null, itemId: null };
  }

  if (/^#\/home\/?$/.test(hash)) {
    return { tab: "home", projectId: null, activitySection: null, communitySection: null, itemId: null };
  }

  return null;
}

function navigateToTab(tab: TabKey): void {
  if (window.location.hash !== TAB_HASH[tab]) {
    window.location.hash = TAB_HASH[tab];
  }
}

function renderTab(
  tab: TabKey,
  user: MiniAppUserSummary,
  initialProjectId: number | null,
  initialActivitySection: LegacyActivitySection | null,
  initialCommunitySection: CommunitySection | null,
  initialItemId: number | null,
  isDeepLinkedTab: boolean,
  onTabChange: (tab: TabKey) => void,
) {
  if (tab === "home") {
    if (isDeepLinkedTab && initialActivitySection) {
      return <ActivityScreen initialSection={initialActivitySection} initialItemId={initialItemId} />;
    }
    return (
      <HomeScreen
        user={user}
        onOpenEvents={() => onTabChange("events")}
        onOpenCommunity={() => onTabChange("community")}
      />
    );
  }

  if (tab === "projects") {
    return <ProjectsScreen initialProjectId={initialProjectId} />;
  }

  if (tab === "events") {
    return <EventsScreen initialItemId={isDeepLinkedTab ? initialItemId : null} />;
  }

  if (tab === "community") {
    return (
      <CommunityScreen
        initialSection={isDeepLinkedTab ? initialCommunitySection : null}
        initialItemId={isDeepLinkedTab ? initialItemId : null}
      />
    );
  }

  return <ProfileScreen />;
}

export function App() {
  const auth = useAuth();
  const [deepLink, setDeepLink] = useState<DeepLink | null>(() => parseDeepLink());
  const [activeTab, setActiveTab] = useState<TabKey>(deepLink?.tab ?? "home");
  const [inWorkspace, setInWorkspace] = useState(false);

  useEffect(() => {
    const syncFromHash = () => {
      const next = parseDeepLink();
      setDeepLink(next);
      setActiveTab(next?.tab ?? "home");
    };
    window.addEventListener("hashchange", syncFromHash);
    window.addEventListener("popstate", syncFromHash);
    return () => {
      window.removeEventListener("hashchange", syncFromHash);
      window.removeEventListener("popstate", syncFromHash);
    };
  }, []);

  const handleTabChange = (tab: TabKey) => {
    setActiveTab(tab);
    navigateToTab(tab);
  };

  const initialProjectId = deepLink?.projectId ?? null;

  if (auth.status === "loading") return null;
  if (auth.status === "error") {
    return <AuthErrorScreen code={auth.code} detail={auth.detail} onRetry={auth.refresh} />;
  }

  const { user } = auth;
  if (user.application_status === "pending" || user.application_status === "needs_info") {
    return <PendingScreen onRefresh={auth.refresh} />;
  }
  if (user.application_status === "rejected" || user.is_blocked) {
    return <BlockedScreen />;
  }

  if (user.is_admin && inWorkspace) {
    return (
      <AdminLayout onExitWorkspace={() => setInWorkspace(false)}>
        {initialProjectId ? <ProjectsScreen initialProjectId={initialProjectId} /> : <AdminScreen />}
      </AdminLayout>
    );
  }
  if (user.is_leader && inWorkspace) {
    return (
      <LeaderLayout onExitWorkspace={() => setInWorkspace(false)}>
        {initialProjectId ? <ProjectsScreen initialProjectId={initialProjectId} /> : <LeaderScreen />}
      </LeaderLayout>
    );
  }

  return (
    <UserLayout activeTab={activeTab} onTabChange={handleTabChange}>
      {activeTab === "profile" ? (
        <ProfileScreen
          isAdmin={user.is_admin}
          isLeader={user.is_leader}
          onEnterWorkspace={user.is_admin || user.is_leader ? () => setInWorkspace(true) : undefined}
        />
      ) : (
        renderTab(
          activeTab,
          user,
          initialProjectId,
          deepLink?.activitySection ?? null,
          deepLink?.communitySection ?? null,
          deepLink?.itemId ?? null,
          deepLink?.tab === activeTab,
          handleTabChange,
        )
      )}
    </UserLayout>
  );
}