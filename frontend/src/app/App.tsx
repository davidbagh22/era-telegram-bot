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
import { LeaderboardScreen } from "../screens/LeaderboardScreen";
import { NotificationsScreen } from "../screens/NotificationsScreen";
import { ObjectUnavailableScreen } from "../screens/ObjectUnavailableScreen";
import { OpportunitiesScreen, type OpportunitiesSection } from "../screens/OpportunitiesScreen";
import { PendingScreen } from "../screens/PendingScreen";
import { ProfileScreen } from "../screens/ProfileScreen";
import { ProgressScreen } from "../screens/ProgressScreen";
import { ProjectsScreen } from "../screens/ProjectsScreen";
import { UserPublicProfileScreen } from "../screens/UserPublicProfileScreen";
import { AdminEventsScreen } from "../screens/admin/AdminEventsScreen";
import type { MiniAppUserSummary } from "../types/auth";

type LegacyActivitySection = "tasks" | "calendar" | "history";
type LegacyCommunitySection = "opportunities" | "auctions" | "rewards" | "surveys" | "leaderboard";
type WorkspaceKind = "admin" | "leader";
type UtilityScreen = "progress" | "notifications";

interface DeepLink {
  tab: TabKey;
  projectId: number | null;
  activitySection: LegacyActivitySection | null;
  communitySection: CommunitySection | null;
  legacyCommunitySection: LegacyCommunitySection | null;
  itemId: number | null;
  workspace: WorkspaceKind | null;
  adminEventId: number | null;
  userId: number | null;
  utilityScreen: UtilityScreen | null;
  invalid: boolean;
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
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

function normalizeRoute(value: string): string { return value.replace(/^\/?/, "").replace(/\/$/, "").split("?")[0]; }

function routeFromStartParam(value: string): string {
  const normalized = normalizeRoute(value);
  const mappings: [RegExp, (id: string) => string][] = [
    [/^event_(\d+)$/, (id) => `events/${id}`],
    [/^project_(\d+)$/, (id) => `projects/${id}`],
    [/^task_(\d+)$/, (id) => `tasks/${id}`],
    [/^user_(\d+)$/, (id) => `users/${id}`],
    [/^admin_event_(\d+)$/, (id) => `admin/events/${id}`],
  ];
  for (const [pattern, build] of mappings) { const match = normalized.match(pattern); if (match) return build(match[1]); }
  return normalized;
}

function telegramQueryRoute(): string {
  const query = new URLSearchParams(window.location.search);
  const explicitPath = query.get("eraPath");
  if (explicitPath) return normalizeRoute(explicitPath);
  return routeFromStartParam(query.get("tgWebAppStartParam") ?? "");
}

function routeValue(): string {
  const queryRoute = telegramQueryRoute();
  if (queryRoute) return queryRoute;
  return normalizeRoute(window.location.hash.replace(/^#\/?/, ""));
}

function canonicalizeTelegramQueryRoute(): void {
  const route = telegramQueryRoute();
  if (!route) return;
  const url = new URL(window.location.href);
  url.searchParams.delete("eraPath");
  url.searchParams.delete("tgWebAppStartParam");
  url.hash = `/${route}`;
  window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
}

function link(overrides: Partial<DeepLink> = {}): DeepLink {
  return {
    tab: "home",
    projectId: null,
    activitySection: null,
    communitySection: null,
    legacyCommunitySection: null,
    itemId: null,
    workspace: null,
    adminEventId: null,
    userId: null,
    utilityScreen: null,
    invalid: false,
    ...overrides,
  };
}

function parseDeepLink(): DeepLink | null {
  const route = routeValue();
  if (!route) return null;

  const adminEvent = route.match(/^admin\/events\/(\d+)$/);
  if (adminEvent) { const id = parseOptionalId(adminEvent[1]); return id ? link({ tab: "events", workspace: "admin", adminEventId: id }) : link({ invalid: true }); }
  const adminProject = route.match(/^admin\/projects\/(\d+)$/);
  if (adminProject) { const id = parseOptionalId(adminProject[1]); return id ? link({ tab: "projects", projectId: id, workspace: "admin" }) : link({ invalid: true }); }

  const project = route.match(/^projects\/(\d+)$/);
  if (project) { const id = parseOptionalId(project[1]); return id ? link({ tab: "projects", projectId: id }) : link({ invalid: true }); }
  if (route === "projects") return link({ tab: "projects" });

  const activity = route.match(/^(tasks|calendar|history)(?:\/(\d+))?$/);
  if (activity) {
    const itemId = activity[2] ? parseOptionalId(activity[2]) : null;
    if (activity[2] && itemId === null) return link({ invalid: true });
    return link({ tab: "home", activitySection: activity[1] as LegacyActivitySection, itemId });
  }

  const event = route.match(/^events(?:\/(\d+))?$/);
  if (event) {
    const itemId = event[1] ? parseOptionalId(event[1]) : null;
    if (event[1] && itemId === null) return link({ invalid: true });
    return link({ tab: "events", itemId });
  }

  const user = route.match(/^users\/(\d+)$/);
  if (user) { const id = parseOptionalId(user[1]); return id ? link({ tab: "community", userId: id }) : link({ invalid: true }); }

  const community = route.match(/^community\/(people|team|projects|interests)$/);
  if (community) return link({ tab: "community", communitySection: community[1] as CommunitySection });
  if (route === "community") return link({ tab: "community" });

  const oldCommunity = route.match(/^(opportunities|auctions|rewards|surveys)(?:\/(\d+))?$/);
  if (oldCommunity) {
    const itemId = oldCommunity[2] ? parseOptionalId(oldCommunity[2]) : null;
    if (oldCommunity[2] && itemId === null) return link({ invalid: true });
    return link({ tab: "community", legacyCommunitySection: oldCommunity[1] as LegacyCommunitySection, itemId });
  }
  if (route === "leaderboard") return link({ tab: "community", legacyCommunitySection: "leaderboard" });

  if (route === "progress") return link({ tab: "home", utilityScreen: "progress" });
  if (route === "notifications") return link({ tab: "home", utilityScreen: "notifications" });
  if (route === "profile") return link({ tab: "profile" });
  if (route === "admin") return link({ tab: "profile", workspace: "admin" });
  if (route === "leader") return link({ tab: "profile", workspace: "leader" });
  if (route === "home") return link({ tab: "home" });
  return link({ invalid: true });
}

function navigateToTab(tab: TabKey): void {
  const target = TAB_HASH[tab];
  if (window.location.hash === target) window.scrollTo({ top: 0, behavior: "smooth" });
  else window.location.hash = target;
}

function toOpportunitySection(section: LegacyCommunitySection): OpportunitiesSection | undefined {
  if (section === "opportunities") return "offers";
  if (section === "auctions" || section === "rewards" || section === "surveys") return section;
  return undefined;
}

function renderUserRoute(linkState: DeepLink | null, user: MiniAppUserSummary) {
  if (linkState?.utilityScreen === "progress") return <ProgressScreen />;
  if (linkState?.utilityScreen === "notifications") return <NotificationsScreen />;
  if (linkState?.activitySection) return <ActivityScreen initialSection={linkState.activitySection} initialItemId={linkState.itemId} />;
  if (linkState?.tab === "projects") return <ProjectsScreen initialProjectId={linkState.projectId} />;
  if (linkState?.tab === "events") return <EventsScreen initialItemId={linkState.itemId} />;
  if (linkState?.tab === "community") {
    if (linkState.legacyCommunitySection === "leaderboard") return <LeaderboardScreen onBack={() => { window.location.hash = "#/community"; }} />;
    if (linkState.legacyCommunitySection) return <OpportunitiesScreen initialSection={toOpportunitySection(linkState.legacyCommunitySection)} initialItemId={linkState.itemId} onBack={() => { window.location.hash = "#/community"; }} />;
    return <CommunityScreen initialSection={linkState.communitySection} />;
  }
  if (linkState?.tab === "profile") return <ProfileScreen />;
  return <HomeScreen user={user} />;
}

export function App() {
  const auth = useAuth();
  const [deepLink, setDeepLink] = useState<DeepLink | null>(() => parseDeepLink());
  const [activeTab, setActiveTab] = useState<TabKey>(deepLink?.tab ?? "home");
  const [inWorkspace, setInWorkspace] = useState(false);

  useEffect(() => {
    canonicalizeTelegramQueryRoute();
    const sync = () => { const next = parseDeepLink(); setDeepLink(next); setActiveTab(next?.tab ?? "home"); };
    window.addEventListener("hashchange", sync);
    window.addEventListener("popstate", sync);
    return () => { window.removeEventListener("hashchange", sync); window.removeEventListener("popstate", sync); };
  }, []);

  const handleTabChange = (tab: TabKey) => { setActiveTab(tab); navigateToTab(tab); };
  const exitWorkspace = () => { setInWorkspace(false); navigateToTab("profile"); };

  if (auth.status === "loading") return null;
  if (auth.status === "error") return <AuthErrorScreen code={auth.code} detail={auth.detail} onRetry={auth.refresh} />;

  const { user } = auth;
  if (user.application_status === "pending" || user.application_status === "needs_info") return <PendingScreen onRefresh={auth.refresh} />;
  if (user.application_status === "rejected" || user.is_blocked) return <BlockedScreen />;

  const goHome = () => navigateToTab("home");
  if (deepLink?.invalid) return <ObjectUnavailableScreen onHome={goHome} />;
  if (deepLink?.workspace === "admin" && !user.is_admin) return <ObjectUnavailableScreen onHome={goHome} />;
  if (deepLink?.workspace === "leader" && !user.is_leader) return <ObjectUnavailableScreen onHome={goHome} />;

  if (deepLink?.userId) {
    return <UserLayout activeTab="community" onTabChange={handleTabChange}><UserPublicProfileScreen userId={deepLink.userId} /></UserLayout>;
  }

  const adminWorkspaceRequested = user.is_admin && (inWorkspace || deepLink?.workspace === "admin");
  const leaderWorkspaceRequested = user.is_leader && (inWorkspace || deepLink?.workspace === "leader");
  if (adminWorkspaceRequested) {
    return <AdminLayout onExitWorkspace={exitWorkspace}>{deepLink?.adminEventId ? <AdminEventsScreen initialEventId={deepLink.adminEventId} /> : deepLink?.projectId ? <ProjectsScreen initialProjectId={deepLink.projectId} /> : <AdminScreen />}</AdminLayout>;
  }
  if (leaderWorkspaceRequested) {
    return <LeaderLayout onExitWorkspace={exitWorkspace}>{deepLink?.projectId ? <ProjectsScreen initialProjectId={deepLink.projectId} /> : <LeaderScreen />}</LeaderLayout>;
  }

  return (
    <UserLayout activeTab={activeTab} onTabChange={handleTabChange}>
      {activeTab === "profile" && !deepLink?.utilityScreen ? (
        <ProfileScreen isAdmin={user.is_admin} isLeader={user.is_leader} onEnterWorkspace={user.is_admin || user.is_leader ? () => setInWorkspace(true) : undefined} />
      ) : renderUserRoute(deepLink, user)}
    </UserLayout>
  );
}
