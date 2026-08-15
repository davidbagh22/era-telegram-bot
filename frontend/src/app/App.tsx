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
type WorkspaceKind = "admin" | "leader";

interface DeepLink {
  tab: TabKey;
  projectId: number | null;
  activitySection: LegacyActivitySection | null;
  communitySection: CommunitySection | null;
  itemId: number | null;
  workspace: WorkspaceKind | null;
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

function routeValue(): string {
  const hashRoute = window.location.hash.replace(/^#\/?/, "").replace(/\/$/, "");
  if (hashRoute) return hashRoute;

  const query = new URLSearchParams(window.location.search);
  // eraPath is the first-class Bot -> Mini App route. tgWebAppStartParam is
  // accepted too so a future Main Mini App `startapp` link can use the same
  // parser without another navigation layer.
  return (query.get("eraPath") ?? query.get("tgWebAppStartParam") ?? "")
    .replace(/^\/?/, "")
    .replace(/\/$/, "");
}

function parseDeepLink(): DeepLink | null {
  const route = routeValue();
  if (!route) return null;

  const adminProjectMatch = route.match(/^admin\/projects\/(\d+)$/);
  if (adminProjectMatch) {
    const projectId = parseOptionalId(adminProjectMatch[1]);
    if (projectId !== null) {
      return {
        tab: "projects",
        projectId,
        activitySection: null,
        communitySection: null,
        itemId: null,
        workspace: "admin",
      };
    }
  }

  const projectMatch = route.match(/^projects\/(\d+)$/);
  if (projectMatch) {
    const projectId = parseOptionalId(projectMatch[1]);
    if (projectId !== null) {
      return {
        tab: "projects",
        projectId,
        activitySection: null,
        communitySection: null,
        itemId: null,
        workspace: null,
      };
    }
  }
  if (route === "projects") {
    return { tab: "projects", projectId: null, activitySection: null, communitySection: null, itemId: null, workspace: null };
  }

  const activityMatch = route.match(/^(tasks|calendar|history)(?:\/(\d+))?$/);
  if (activityMatch) {
    return {
      tab: "home",
      projectId: null,
      activitySection: activityMatch[1] as LegacyActivitySection,
      communitySection: null,
      itemId: parseOptionalId(activityMatch[2]),
      workspace: null,
    };
  }

  const eventMatch = route.match(/^events(?:\/(\d+))?$/);
  if (eventMatch) {
    return {
      tab: "events",
      projectId: null,
      activitySection: null,
      communitySection: null,
      itemId: parseOptionalId(eventMatch[1]),
      workspace: null,
    };
  }

  const communityMatch = route.match(/^(opportunities|auctions|rewards|surveys)(?:\/(\d+))?$/);
  if (communityMatch) {
    return {
      tab: "community",
      projectId: null,
      activitySection: null,
      communitySection: communityMatch[1] as CommunitySection,
      itemId: parseOptionalId(communityMatch[2]),
      workspace: null,
    };
  }

  if (route === "leaderboard") {
    return { tab: "community", projectId: null, activitySection: null, communitySection: "leaderboard", itemId: null, workspace: null };
  }
  if (route === "community") {
    return { tab: "community", projectId: null, activitySection: null, communitySection: null, itemId: null, workspace: null };
  }
  if (route === "profile") {
    return { tab: "profile", projectId: null, activitySection: null, communitySection: null, itemId: null, workspace: null };
  }
  if (route === "admin") {
    return { tab: "profile", projectId: null, activitySection: null, communitySection: null, itemId: null, workspace: "admin" };
  }
  if (route === "leader") {
    return { tab: "profile", projectId: null, activitySection: null, communitySection: null, itemId: null, workspace: "leader" };
  }
  if (route === "home") {
    return { tab: "home", projectId: null, activitySection: null, communitySection: null, itemId: null, workspace: null };
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

  if (tab === "projects") return <ProjectsScreen initialProjectId={initialProjectId} />;
  if (tab === "events") return <EventsScreen initialItemId={isDeepLinkedTab ? initialItemId : null} />;
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
    const syncFromLocation = () => {
      const next = parseDeepLink();
      setDeepLink(next);
      setActiveTab(next?.tab ?? "home");
    };
    window.addEventListener("hashchange", syncFromLocation);
    window.addEventListener("popstate", syncFromLocation);
    return () => {
      window.removeEventListener("hashchange", syncFromLocation);
      window.removeEventListener("popstate", syncFromLocation);
    };
  }, []);

  const handleTabChange = (tab: TabKey) => {
    setActiveTab(tab);
    navigateToTab(tab);
  };

  const exitWorkspace = () => {
    setInWorkspace(false);
    navigateToTab("profile");
  };

  const initialProjectId = deepLink?.projectId ?? null;

  if (auth.status === "loading") return null;
  if (auth.status === "error") return <AuthErrorScreen code={auth.code} detail={auth.detail} onRetry={auth.refresh} />;

  const { user } = auth;
  if (user.application_status === "pending" || user.application_status === "needs_info") {
    return <PendingScreen onRefresh={auth.refresh} />;
  }
  if (user.application_status === "rejected" || user.is_blocked) return <BlockedScreen />;

  const adminWorkspaceRequested = user.is_admin && (inWorkspace || deepLink?.workspace === "admin");
  const leaderWorkspaceRequested = user.is_leader && (inWorkspace || deepLink?.workspace === "leader");

  if (adminWorkspaceRequested) {
    return (
      <AdminLayout onExitWorkspace={exitWorkspace}>
        {initialProjectId ? <ProjectsScreen initialProjectId={initialProjectId} /> : <AdminScreen />}
      </AdminLayout>
    );
  }
  if (leaderWorkspaceRequested) {
    return (
      <LeaderLayout onExitWorkspace={exitWorkspace}>
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
