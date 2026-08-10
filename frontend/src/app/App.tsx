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
import { HomeScreen } from "../screens/HomeScreen";
import { LeaderScreen } from "../screens/LeaderScreen";
import { OpportunitiesScreen } from "../screens/OpportunitiesScreen";
import { PendingScreen } from "../screens/PendingScreen";
import { ProfileScreen } from "../screens/ProfileScreen";
import { ProjectsScreen } from "../screens/ProjectsScreen";
import type { MiniAppUserSummary } from "../types/auth";

type ActivitySection = "events" | "tasks" | "calendar" | "history";

interface DeepLink {
  tab: TabKey;
  projectId: number | null;
  activitySection: ActivitySection | null;
}

// PR 36 (Bot/Mini App role split): the bot's quick-access buttons
// (📅 Ближайшее / ✅ Мои задачи / ⭐ Возможности, and notification
// "Открыть …" buttons going forward) link straight into
// `${miniapp_url}/#/<path>` — built server-side by
// app/utils/deep_links.py's miniapp_*_url() helpers — instead of just
// opening the Mini App at its home screen and making the user navigate
// themselves. This is the one place that contract is parsed back out.
function parseDeepLink(): DeepLink | null {
  const hash = window.location.hash;
  const projectMatch = hash.match(/^#\/(?:admin\/)?projects\/(\d+)/);
  if (projectMatch) {
    const projectId = Number(projectMatch[1]);
    if (Number.isFinite(projectId)) {
      return { tab: "projects", projectId, activitySection: null };
    }
  }
  if (/^#\/tasks(\/|$)/.test(hash)) {
    return { tab: "activity", projectId: null, activitySection: "tasks" };
  }
  if (/^#\/events(\/|$)/.test(hash)) {
    return { tab: "activity", projectId: null, activitySection: "events" };
  }
  if (/^#\/opportunities(\/|$)/.test(hash)) {
    return { tab: "opportunities", projectId: null, activitySection: null };
  }
  return null;
}

function renderTab(
  tab: TabKey,
  user: MiniAppUserSummary,
  initialProjectId: number | null,
  initialActivitySection: ActivitySection | null,
  onTabChange: (tab: TabKey) => void,
) {
  if (tab === "home") {
    return <HomeScreen user={user} onOpenActivity={() => onTabChange("activity")} />;
  }
  if (tab === "activity") {
    return <ActivityScreen initialSection={initialActivitySection ?? undefined} />;
  }
  if (tab === "projects") {
    return <ProjectsScreen initialProjectId={initialProjectId} />;
  }
  if (tab === "opportunities") {
    return <OpportunitiesScreen />;
  }
  return <ProfileScreen />;
}

export function App() {
  const auth = useAuth();
  const [deepLink] = useState<DeepLink | null>(() => parseDeepLink());
  const initialProjectId = deepLink?.projectId ?? null;
  const [activeTab, setActiveTab] = useState<TabKey>(deepLink?.tab ?? "home");

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

  if (user.is_admin) {
    return (
      <AdminLayout>
        {initialProjectId ? <ProjectsScreen initialProjectId={initialProjectId} /> : <AdminScreen />}
      </AdminLayout>
    );
  }
  if (user.is_leader) {
    return (
      <LeaderLayout>
        {initialProjectId ? <ProjectsScreen initialProjectId={initialProjectId} /> : <LeaderScreen />}
      </LeaderLayout>
    );
  }

  return (
    <UserLayout activeTab={activeTab} onTabChange={setActiveTab}>
      {renderTab(activeTab, user, initialProjectId, deepLink?.activitySection ?? null, setActiveTab)}
    </UserLayout>
  );
}
