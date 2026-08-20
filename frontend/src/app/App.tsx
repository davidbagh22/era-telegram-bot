import { useEffect, useState } from "react";
import type { TabKey } from "../components/FloatingNav";
import { useAuth } from "../hooks/useAuth";
import { AdminLayout } from "../layouts/AdminLayout";
import { LeaderLayout } from "../layouts/LeaderLayout";
import { UserLayout } from "../layouts/UserLayout";
import { AdminScreen } from "../screens/AdminScreen";
import { ActivityScreen } from "../screens/ActivityScreen";
import { AuthErrorScreen } from "../screens/AuthErrorScreen";
import { BlockedScreen } from "../screens/BlockedScreen";
import { CommunityScreen, type CommunitySection } from "../screens/CommunityScreen";
import { DevelopmentScreen, type DevelopmentRoute } from "../screens/DevelopmentScreen";
import { EraProScreen } from "../screens/EraProScreen";
import { EventsScreen } from "../screens/EventsScreen";
import { HomeScreen } from "../screens/HomeScreen";
import { LeaderScreen } from "../screens/LeaderScreen";
import { ObjectUnavailableScreen } from "../screens/ObjectUnavailableScreen";
import { PendingScreen } from "../screens/PendingScreen";
import { ProfileScreen } from "../screens/ProfileScreen";
import { ProgressScreen } from "../screens/ProgressScreen";
import { ProjectsScreen } from "../screens/ProjectsScreen";
import { TasksScreen } from "../screens/TasksScreen";
import { UserPublicProfileScreen } from "../screens/UserPublicProfileScreen";
import { AdminEventsScreen } from "../screens/admin/AdminEventsScreen";
import type { MiniAppUserSummary } from "../types/auth";

type LegacyActivitySection = "tasks" | "calendar" | "history";
type WorkspaceKind = "admin" | "leader";
type SpecialScreen = "progress" | "development" | "era-pro";

interface DeepLink {
  tab: TabKey;
  projectId: number | null;
  activitySection: LegacyActivitySection | null;
  communitySection: CommunitySection | null;
  itemId: number | null;
  workspace: WorkspaceKind | null;
  adminEventId: number | null;
  userId: number | null;
  specialScreen: SpecialScreen | null;
  developmentRoute: DevelopmentRoute | null;
  mediaRoute: "guide" | null;
  invalid: boolean;
}

const TAB_HASH: Record<TabKey, string> = {
  home: "#/home",
  projects: "#/projects",
  events: "#/events",
  community: "#/opportunities",
  profile: "#/profile",
};

function parseOptionalId(value: string | undefined): number | null {
  if (!value) return null;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

function normalizeRoute(value: string): string {
  return value.replace(/^\/?/, "").replace(/\/$/, "");
}

function routeFromStartParam(value: string): string {
  const normalized = normalizeRoute(value);
  const mappings: [RegExp, (id: string) => string][] = [
    [/^event_(\d+)$/, (id) => `events/${id}`],
    [/^project_(\d+)$/, (id) => `projects/${id}`],
    [/^task_(\d+)$/, (id) => `tasks/${id}`],
    [/^user_(\d+)$/, (id) => `users/${id}`],
    [/^admin_event_(\d+)$/, (id) => `admin/events/${id}`],
  ];
  for (const [pattern, build] of mappings) {
    const match = normalized.match(pattern);
    if (match) return build(match[1]);
  }
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
    itemId: null,
    workspace: null,
    adminEventId: null,
    userId: null,
    specialScreen: null,
    developmentRoute: null,
    mediaRoute: null,
    invalid: false,
    ...overrides,
  };
}

function parseDevelopmentRoute(route: string): DevelopmentRoute | null {
  if (route === "development") return "home";
  if (route === "development/checkin" || route === "development/checkin/current") return "checkin";
  if (route === "development/assessments") return "assessments";
  if (route === "development/history") return "history";
  if (route === "development/goals") return "goals";
  if (route === "development/privacy") return "privacy";
  return null;
}

function parseDeepLink(): DeepLink | null {
  const route = routeValue();
  if (!route) return null;

  const developmentRoute = parseDevelopmentRoute(route);
  if (developmentRoute) return link({ tab: "home", specialScreen: "development", developmentRoute });
  if (route === "era-pro") return link({ tab: "community", specialScreen: "era-pro" });

  const adminEventMatch = route.match(/^admin\/events\/(\d+)$/);
  if (adminEventMatch) {
    const adminEventId = parseOptionalId(adminEventMatch[1]);
    return adminEventId ? link({ tab: "events", workspace: "admin", adminEventId }) : link({ invalid: true });
  }
  const adminProjectMatch = route.match(/^admin\/projects\/(\d+)$/);
  if (adminProjectMatch) {
    const projectId = parseOptionalId(adminProjectMatch[1]);
    return projectId ? link({ tab: "projects", projectId, workspace: "admin" }) : link({ invalid: true });
  }
  const projectMatch = route.match(/^projects\/(\d+)$/);
  if (projectMatch) {
    const projectId = parseOptionalId(projectMatch[1]);
    return projectId ? link({ tab: "projects", projectId }) : link({ invalid: true });
  }
  if (route === "projects") return link({ tab: "projects" });

  const activityMatch = route.match(/^(tasks|calendar|history)(?:\/(\d+))?$/);
  if (activityMatch) {
    const itemId = activityMatch[2] ? parseOptionalId(activityMatch[2]) : null;
    if (activityMatch[2] && itemId === null) return link({ invalid: true });
    return link({ tab: "home", activitySection: activityMatch[1] as LegacyActivitySection, itemId });
  }

  const eventMatch = route.match(/^events(?:\/(\d+))?$/);
  if (eventMatch) {
    const itemId = eventMatch[1] ? parseOptionalId(eventMatch[1]) : null;
    if (eventMatch[1] && itemId === null) return link({ invalid: true });
    return link({ tab: "events", itemId });
  }

  const userMatch = route.match(/^users\/(\d+)$/);
  if (userMatch) {
    const userId = parseOptionalId(userMatch[1]);
    return userId ? link({ tab: "community", userId }) : link({ invalid: true });
  }

  const communityMatch = route.match(/^(opportunities|auctions|rewards|surveys|media)(?:\/(\d+))?$/);
  if (communityMatch) {
    const itemId = communityMatch[2] ? parseOptionalId(communityMatch[2]) : null;
    if (communityMatch[2] && itemId === null) return link({ invalid: true });
    return link({ tab: "community", communitySection: communityMatch[1] as CommunitySection, itemId });
  }

  if (route === "media/guide") return link({ tab: "community", communitySection: "media", mediaRoute: "guide" });

  if (route === "progress") return link({ tab: "home", specialScreen: "progress" });
  if (route === "leaderboard") return link({ tab: "community", communitySection: "leaderboard" });
  if (route === "community") return link({ tab: "community" });
  if (route === "profile") return link({ tab: "profile" });
  if (route === "admin") return link({ tab: "profile", workspace: "admin" });
  if (route === "leader") return link({ tab: "profile", workspace: "leader" });
  if (route === "home") return link({ tab: "home" });
  return link({ invalid: true });
}

function navigateToTab(tab: TabKey): void {
  if (window.location.hash !== TAB_HASH[tab]) window.location.hash = TAB_HASH[tab];
}

function navigateToRoute(route: string): void {
  const target = `#/${normalizeRoute(route)}`;
  if (window.location.hash !== target) window.location.hash = target;
}

function renderTab(
  tab: TabKey,
  user: MiniAppUserSummary,
  initialProjectId: number | null,
  initialActivitySection: LegacyActivitySection | null,
  initialCommunitySection: CommunitySection | null,
  initialItemId: number | null,
  initialMediaRoute: "guide" | null,
  isDeepLinkedTab: boolean,
  onTabChange: (tab: TabKey) => void,
) {
  if (tab === "home") {
    if (isDeepLinkedTab && initialActivitySection === "tasks") {
      return <TasksScreen initialItemId={initialItemId} onBack={() => navigateToTab("home")} />;
    }
    if (isDeepLinkedTab && initialActivitySection) return <ActivityScreen initialSection={initialActivitySection} initialItemId={initialItemId} />;
    return (
      <HomeScreen
        user={user}
        onOpenProfile={() => navigateToRoute("profile")}
        onOpenProgress={() => navigateToRoute("progress")}
        onOpenDevelopment={() => navigateToRoute("development")}
        onOpenEvents={() => onTabChange("events")}
        onOpenEvent={(id) => navigateToRoute(`events/${id}`)}
        onOpenProject={(id) => navigateToRoute(`projects/${id}`)}
        onOpenTask={(id) => navigateToRoute(`tasks/${id}`)}
        onOpenTasks={() => navigateToRoute("tasks")}
        onOpenCommunity={() => navigateToRoute("opportunities")}
        onOpenOpportunity={(id) => navigateToRoute(`opportunities/${id}`)}
      />
    );
  }
  if (tab === "projects") return <ProjectsScreen initialProjectId={initialProjectId} />;
  if (tab === "events") return <EventsScreen initialItemId={isDeepLinkedTab ? initialItemId : null} />;
  if (tab === "community") return <CommunityScreen initialSection={isDeepLinkedTab ? initialCommunitySection : null} initialItemId={isDeepLinkedTab ? initialItemId : null} initialMediaRoute={isDeepLinkedTab ? initialMediaRoute : null} />;
  return <ProfileScreen onOpenDevelopment={() => navigateToRoute("development")} />;
}

export function App() {
  const auth = useAuth();
  const [deepLink, setDeepLink] = useState<DeepLink | null>(() => parseDeepLink());
  const [activeTab, setActiveTab] = useState<TabKey>(deepLink?.tab ?? "home");
  const [inWorkspace, setInWorkspace] = useState(false);

  useEffect(() => {
    canonicalizeTelegramQueryRoute();
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
  if (user.application_status === "pending" || user.application_status === "needs_info") return <PendingScreen onRefresh={auth.refresh} />;
  if (user.application_status === "rejected" || user.is_blocked) return <BlockedScreen />;

  const goHome = () => navigateToTab("home");
  if (deepLink?.invalid) return <ObjectUnavailableScreen onHome={goHome} />;
  if (deepLink?.workspace === "admin" && !user.is_admin) return <ObjectUnavailableScreen onHome={goHome} />;
  if (deepLink?.workspace === "leader" && !user.is_leader) return <ObjectUnavailableScreen onHome={goHome} />;

  if (deepLink?.userId) {
    return <UserLayout activeTab="community" onTabChange={handleTabChange}><UserPublicProfileScreen userId={deepLink.userId} onBack={() => window.history.length > 1 ? window.history.back() : navigateToRoute("opportunities")} /></UserLayout>;
  }

  if (deepLink?.specialScreen === "progress") {
    return (
      <UserLayout activeTab="home" onTabChange={handleTabChange}>
        <ProgressScreen
          onBack={() => window.history.length > 1 ? window.history.back() : navigateToTab("home")}
          onOpenProjects={() => navigateToTab("projects")}
          onOpenTasks={() => navigateToRoute("tasks")}
          onOpenEvents={() => navigateToTab("events")}
        />
      </UserLayout>
    );
  }

  if (deepLink?.specialScreen === "development") {
    return (
      <UserLayout activeTab="home" onTabChange={handleTabChange}>
        <DevelopmentScreen
          route={deepLink.developmentRoute ?? "home"}
          onNavigate={(route) => navigateToRoute(route === "home" ? "development" : `development/${route}`)}
          onBack={() => window.history.length > 1 ? window.history.back() : navigateToTab("home")}
        />
      </UserLayout>
    );
  }

  if (deepLink?.specialScreen === "era-pro") {
    return (
      <UserLayout activeTab="community" onTabChange={handleTabChange}>
        <EraProScreen onBack={() => window.history.length > 1 ? window.history.back() : navigateToRoute("opportunities")} />
      </UserLayout>
    );
  }

  const adminWorkspaceRequested = user.is_admin && (inWorkspace || deepLink?.workspace === "admin");
  const leaderWorkspaceRequested = user.is_leader && (inWorkspace || deepLink?.workspace === "leader");

  if (adminWorkspaceRequested) {
    return <AdminLayout onExitWorkspace={exitWorkspace}>{deepLink?.adminEventId ? <AdminEventsScreen initialEventId={deepLink.adminEventId} /> : initialProjectId ? <ProjectsScreen initialProjectId={initialProjectId} /> : <AdminScreen />}</AdminLayout>;
  }
  if (leaderWorkspaceRequested) {
    return <LeaderLayout onExitWorkspace={exitWorkspace}>{initialProjectId ? <ProjectsScreen initialProjectId={initialProjectId} /> : <LeaderScreen />}</LeaderLayout>;
  }

  return (
    <UserLayout activeTab={activeTab} onTabChange={handleTabChange}>
      {activeTab === "profile" ? (
        <ProfileScreen
          isAdmin={user.is_admin}
          isLeader={user.is_leader}
          onEnterWorkspace={user.is_admin || user.is_leader ? () => setInWorkspace(true) : undefined}
          onOpenDevelopment={() => navigateToRoute("development")}
        />
      ) : renderTab(activeTab, user, initialProjectId, deepLink?.activitySection ?? null, deepLink?.communitySection ?? null, deepLink?.itemId ?? null, deepLink?.mediaRoute ?? null, deepLink?.tab === activeTab, handleTabChange)}
    </UserLayout>
  );
}
