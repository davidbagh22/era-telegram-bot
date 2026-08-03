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

function renderTab(tab: TabKey, user: MiniAppUserSummary) {
  if (tab === "home") {
    return <HomeScreen user={user} />;
  }
  if (tab === "activity") {
    return <ActivityScreen />;
  }
  if (tab === "projects") {
    return <ProjectsScreen />;
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
  const [activeTab, setActiveTab] = useState<TabKey>("home");

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
        <HomeScreen user={user} />
      </AdminLayout>
    );
  }
  if (user.is_leader) {
    return (
      <LeaderLayout>
        <HomeScreen user={user} />
      </LeaderLayout>
    );
  }

  return (
    <UserLayout activeTab={activeTab} onTabChange={setActiveTab}>
      {renderTab(activeTab, user)}
    </UserLayout>
  );
}
