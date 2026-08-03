import { useState } from "react";
import type { TabKey } from "../components/BottomNavigation";
import { useAuth } from "../hooks/useAuth";
import { AdminLayout } from "../layouts/AdminLayout";
import { LeaderLayout } from "../layouts/LeaderLayout";
import { UserLayout } from "../layouts/UserLayout";
import { ActivityScreen } from "../screens/ActivityScreen";
import { AuthErrorScreen } from "../screens/AuthErrorScreen";
import { BlockedScreen } from "../screens/BlockedScreen";
import { HomeScreen } from "../screens/HomeScreen";
import { PendingScreen } from "../screens/PendingScreen";
import { ProjectsScreen } from "../screens/ProjectsScreen";
import { StatusBanner } from "../components/StatusBanner";
import type { MiniAppUserSummary } from "../types/auth";

const COMING_SOON_TITLES: Record<Exclude<TabKey, "home" | "activity" | "projects">, string> = {
  opportunities: "Возможности",
  profile: "Профиль",
};

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
  return (
    <StatusBanner
      title={COMING_SOON_TITLES[tab]}
      description="Этот раздел появится в одном из следующих обновлений ЭРА."
    />
  );
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
        {initialProjectId ? <ProjectsScreen initialProjectId={initialProjectId} /> : <HomeScreen user={user} />}
      </AdminLayout>
    );
  }
  if (user.is_leader) {
    return (
      <LeaderLayout>
        {initialProjectId ? <ProjectsScreen initialProjectId={initialProjectId} /> : <HomeScreen user={user} />}
      </LeaderLayout>
    );
  }

  return (
    <UserLayout activeTab={activeTab} onTabChange={setActiveTab}>
      {renderTab(activeTab, user, initialProjectId)}
    </UserLayout>
  );
}
