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

type ActivitySection = "projects" | "events" | "tasks" | "calendar" | "history";

interface DeepLink {
  tab: TabKey;
  projectId: number | null;
  activitySection: ActivitySection | null;
  /** The specific task/event/opportunity id from a per-notification deep
   * link (`#/tasks/{id}`, `#/events/{id}`, `#/opportunities/{id}`) — the
   * landing screen scrolls to and briefly highlights this item once its
   * list has loaded. `null` for tab-level-only links (e.g. the bot's
   * quick-access buttons, which intentionally don't name one item). */
  itemId: number | null;
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
      // "Проекты" is a section inside Activity now, not its own bottom-nav
      // tab (2026-08 redesign brief section 16) — see BottomNavigation.tsx.
      return { tab: "activity", projectId, activitySection: "projects", itemId: null };
    }
  }
  const taskMatch = hash.match(/^#\/tasks(?:\/(\d+))?/);
  if (taskMatch) {
    const itemId = taskMatch[1] ? Number(taskMatch[1]) : null;
    return { tab: "activity", projectId: null, activitySection: "tasks", itemId };
  }
  const eventMatch = hash.match(/^#\/events(?:\/(\d+))?/);
  if (eventMatch) {
    const itemId = eventMatch[1] ? Number(eventMatch[1]) : null;
    return { tab: "activity", projectId: null, activitySection: "events", itemId };
  }
  const opportunityMatch = hash.match(/^#\/opportunities(?:\/(\d+))?/);
  if (opportunityMatch) {
    const itemId = opportunityMatch[1] ? Number(opportunityMatch[1]) : null;
    return { tab: "opportunities", projectId: null, activitySection: null, itemId };
  }
  if (hash.match(/^#\/profile/)) {
    return { tab: "profile", projectId: null, activitySection: null, itemId: null };
  }
  return null;
}

function renderTab(
  tab: TabKey,
  user: MiniAppUserSummary,
  initialProjectId: number | null,
  initialActivitySection: ActivitySection | null,
  initialItemId: number | null,
  onTabChange: (tab: TabKey) => void,
) {
  if (tab === "home") {
    return <HomeScreen user={user} onOpenActivity={() => onTabChange("activity")} />;
  }
  if (tab === "activity") {
    return (
      <ActivityScreen
        initialSection={initialActivitySection ?? undefined}
        initialItemId={initialItemId}
        initialProjectId={initialProjectId}
      />
    );
  }
  if (tab === "opportunities") {
    return <OpportunitiesScreen initialItemId={initialItemId} />;
  }
  return <ProfileScreen />;
}

export function App() {
  const auth = useAuth();
  const [deepLink] = useState<DeepLink | null>(() => parseDeepLink());
  const initialProjectId = deepLink?.projectId ?? null;
  const [activeTab, setActiveTab] = useState<TabKey>(deepLink?.tab ?? "home");
  // Admin/leader land in their workspace by default — unchanged from
  // before this switch existed, and what e2e/admin.spec.ts and friends
  // already assume ("ЭРА / ADMIN" — now just "Управление" — visible right
  // after login, no extra click). What's new is that it's no longer the
  // *only* place they can be: "← Личное" in AdminLayout/LeaderLayout flips
  // this to false, landing them on the exact same Home/Activity/
  // Opportunities/Profile a participant sees — previously an admin or
  // leader had no route to their own personal Mini App at all.
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
          deepLink?.itemId ?? null,
          setActiveTab,
        )
      )}
    </UserLayout>
  );
}
