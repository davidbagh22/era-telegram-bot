import { useState } from "react";
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

function parseDeepLink(): DeepLink | null {
  const hash = window.location.hash;

  const projectMatch = hash.match(/^#\/(?:admin\/)?projects\/(\d+)/);
  if (projectMatch) {
    const projectId = Number(projectMatch[1]);
    if (Number.isFinite(projectId)) {
      return { tab: "projects", projectId, activitySection: null, communitySection: null, itemId: null };
    }
  }
  if (hash.match(/^#\/projects\/?$/)) {
    return { tab: "projects", projectId: null, activitySection: null, communitySection: null, itemId: null };
  }

  const taskMatch = hash.match(/^#\/tasks(?:\/(\d+))?/);
  if (taskMatch) {
    const itemId = taskMatch[1] ? Number(taskMatch[1]) : null;
    return { tab: "home", projectId: null, activitySection: "tasks", communitySection: null, itemId };
  }

  const eventMatch = hash.match(/^#\/events(?:\/(\d+))?/);
  if (eventMatch) {
    const itemId = eventMatch[1] ? Number(eventMatch[1]) : null;
    return { tab: "events", projectId: null, activitySection: null, communitySection: null, itemId };
  }

  const opportunityMatch = hash.match(/^#\/opportunities(?:\/(\d+))?/);
  if (opportunityMatch) {
    const itemId = opportunityMatch[1] ? Number(opportunityMatch[1]) : null;
    return { tab: "community", projectId: null, activitySection: null, communitySection: "opportunities", itemId };
  }

  if (hash.match(/^#\/leaderboard/)) {
    return { tab: "community", projectId: null, activitySection: null, communitySection: "leaderboard", itemId: null };
  }

  if (hash.match(/^#\/community/)) {
    return { tab: "community", projectId: null, activitySection: null, communitySection: null, itemId: null };
  }

  if (hash.match(/^#\/profile/)) {
    return { tab: "profile", projectId: null, activitySection: null, communitySection: null, itemId: null };
  }

  return null;
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
      return (
        <ActivityScreen
          initialSection={initialActivitySection}
          initialItemId={initialItemId}
        />
      );
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
  const [deepLink] = useState<DeepLink | null>(() => parseDeepLink());
  const initialProjectId = deepLink?.projectId ?? null;
  const [activeTab, setActiveTab] = useState<TabKey>(deepLink?.tab ?? "home");
  const [inWorkspace, setInWorkspace] = useState(true);

  if (auth.status === "loading") {
    return null;
  }

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
    <UserLayout activeTab={activeTab} onTabChange={setActiveTab}>
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
          setActiveTab,
        )
      )}
    </UserLayout>
  );
}
