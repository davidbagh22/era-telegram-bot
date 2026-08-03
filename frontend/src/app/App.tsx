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

function projectIdFromHash(): number | null {
  const match = window.location.hash.match(/^#\/(?:admin\/)?projects\/(\d+)/);
  if (!match) {
    return null;
  }
  const projectId = Number(match[1]);
  return Number.isFinite(projectId) ? projectId : null;
}

function renderTab(tab: TabKey, user: MiniAppUserSummary, initialProjectId: number | null) {
  if (tab === "home") {
    return <HomeScreen user={user} />;
  }
  if (tab === "activity") {
    return <ActivityScreen />;
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
  const initialProjectId = projectIdFromHash();
  const [activeTab, setActiveTab] = useState<TabKey>(initialProjectId ? "projects" : "home");

  if (auth.status === "loading") {
    return null;
  }

  if (auth.status === "error") {
    return <AuthErrorScreen code={auth.code} detail={auth.detail} />;
  }

  const { user } = auth;

  if (user.application_status === "pending" || user.application_status === "needs_info") {
    return <PendingScreen />;
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
      {renderTab(activeTab, user, initialProjectId)}
    </UserLayout>
  );
}
