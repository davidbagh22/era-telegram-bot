import { Suspense, lazy, useEffect, useState } from "react";
import type { TabKey } from "../components/FloatingNav";
import { useAuth } from "../hooks/useAuth";
import { UserLayout } from "../layouts/UserLayout";
import { AuthErrorScreen } from "../screens/AuthErrorScreen";
import { BlockedScreen } from "../screens/BlockedScreen";
import type { CommunitySection } from "../screens/CommunityScreen";
import type { DevelopmentRoute } from "../screens/DevelopmentScreen";
import { HomeScreen } from "../screens/HomeScreen";
import { ObjectUnavailableScreen } from "../screens/ObjectUnavailableScreen";
import { PendingScreen } from "../screens/PendingScreen";
import type { MiniAppUserSummary } from "../types/auth";

const AdminLayout = lazy(() => import("../layouts/AdminLayout").then((m) => ({ default: m.AdminLayout })));
const LeaderLayout = lazy(() => import("../layouts/LeaderLayout").then((m) => ({ default: m.LeaderLayout })));
const AdminScreen = lazy(() => import("../screens/AdminScreen").then((m) => ({ default: m.AdminScreen })));
const ActivityScreen = lazy(() => import("../screens/ActivityScreen").then((m) => ({ default: m.ActivityScreen })));
const CommunityScreen = lazy(() => import("../screens/CommunityScreen").then((m) => ({ default: m.CommunityScreen })));
const DevelopmentScreen = lazy(() => import("../screens/DevelopmentScreen").then((m) => ({ default: m.DevelopmentScreen })));
const EraProScreen = lazy(() => import("../screens/EraProScreen").then((m) => ({ default: m.EraProScreen })));
const EventsScreen = lazy(() => import("../screens/EventsScreen").then((m) => ({ default: m.EventsScreen })));
const IdeasScreen = lazy(() => import("../screens/IdeasScreen").then((m) => ({ default: m.IdeasScreen })));
const LeaderScreen = lazy(() => import("../screens/LeaderScreen").then((m) => ({ default: m.LeaderScreen })));
const PeopleScreen = lazy(() => import("../screens/PeopleScreen").then((m) => ({ default: m.PeopleScreen })));
const ProfileScreen = lazy(() => import("../screens/ProfileScreen").then((m) => ({ default: m.ProfileScreen })));
const ProgressScreen = lazy(() => import("../screens/ProgressScreen").then((m) => ({ default: m.ProgressScreen })));
const ProjectsScreen = lazy(() => import("../screens/ProjectsScreen").then((m) => ({ default: m.ProjectsScreen })));
const TasksScreen = lazy(() => import("../screens/TasksScreen").then((m) => ({ default: m.TasksScreen })));
const TeamsScreen = lazy(() => import("../screens/TeamsScreen").then((m) => ({ default: m.TeamsScreen })));
const UserPublicProfileScreen = lazy(() => import("../screens/UserPublicProfileScreen").then((m) => ({ default: m.UserPublicProfileScreen })));
const VectorHomeScreen = lazy(() => import("../screens/VectorHomeScreen").then((m) => ({ default: m.VectorHomeScreen })));
const AdminEventsScreen = lazy(() => import("../screens/admin/AdminEventsScreen").then((m) => ({ default: m.AdminEventsScreen })));

const RouteFallback = <div className="era-page era-discover-page" role="status">Загрузка раздела…</div>;

type LegacyActivitySection = "events" | "tasks" | "calendar" | "history";
type WorkspaceKind = "admin" | "leader";
type SpecialScreen = "progress" | "development" | "era-pro";
type OrbitCatalog = "people" | "teams" | "ideas";

interface DeepLink {
  tab: TabKey;
  projectId: number | null;
  activitySection: LegacyActivitySection | null;
  eventScope: "mine" | null;
  communitySection: CommunitySection | null;
  itemId: number | null;
  workspace: WorkspaceKind | null;
  adminEventId: number | null;
  userId: number | null;
  specialScreen: SpecialScreen | null;
  developmentRoute: DevelopmentRoute | null;
  mediaRoute: "guide" | "files" | "era" | "ksoors" | null;
  orbitCatalog: OrbitCatalog | null;
  invalid: boolean;
}

const TAB_HASH: Record<TabKey, string> = {
  home: "#/home",
  projects: "#/projects",
  events: "#/events",
  community: "#/discover",
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
    eventScope: null,
    communitySection: null,
    itemId: null,
    workspace: null,
    adminEventId: null,
    userId: null,
    specialScreen: null,
    developmentRoute: null,
    mediaRoute: null,
    orbitCatalog: null,
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
  if (route === "events_mine" || route === "events/mine") return link({ tab: "events", activitySection: "events", eventScope: "mine" });
  if (route === "participation") return link({ tab: "events" });

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
    return link({ tab: "events", activitySection: "events", itemId });
  }

  const userMatch = route.match(/^users\/(\d+)$/);
  if (userMatch) {
    const userId = parseOptionalId(userMatch[1]);
    return userId ? link({ tab: "home", userId }) : link({ invalid: true });
  }

  const communityMatch = route.match(/^(opportunities|auctions|rewards|surveys|media)(?:\/(\d+))?$/);
  if (communityMatch) {
    const itemId = communityMatch[2] ? parseOptionalId(communityMatch[2]) : null;
    if (communityMatch[2] && itemId === null) return link({ invalid: true });
    return link({ tab: "community", communitySection: communityMatch[1] as CommunitySection, itemId });
  }

  if (route === "media/guide") return link({ tab: "community", communitySection: "media", mediaRoute: "guide" });
  if (route === "media/files") return link({ tab: "community", communitySection: "media", mediaRoute: "files" });
  if (route === "media/era" || route === "media/ksoors") return link({ tab: "community", communitySection: "media", mediaRoute: route === "media/era" ? "era" : "ksoors" });

  if (route === "progress") return link({ tab: "home", specialScreen: "progress" });
  if (route === "leaderboard") return link({ tab: "community", communitySection: "leaderboard" });
  if (route === "people") return link({ tab: "home", orbitCatalog: "people" });
  if (route === "teams") return link({ tab: "home", orbitCatalog: "teams" });
  if (route === "ideas") return link({ tab: "home", orbitCatalog: "ideas" });
  if (route === "discover") return link({ tab: "community" });
  if (route === "discover/leisure") return link({ tab: "community", communitySection: "leisure" });
  if (route === "discover/points") return link({ tab: "community", communitySection: "points" });
  const readingMatch = route.match(/^literature(?:\/(\d+))?$/);
  if (readingMatch) {
    const itemId = parseOptionalId(readingMatch[1]);
    if (readingMatch[1] && itemId === null) return link({ invalid: true });
    return link({ tab: "community", communitySection: "literature", itemId });
  }
  if (route === "games") return link({ tab: "community", communitySection: "games" });
  if (route === "community") return link({ tab: "community", communitySection: "opportunities" });
  if (route === "profile") return link({ tab: "profile" });
  if (route === "admin") return link({ tab: "profile", workspace: "admin" });
  if (route === "leader") return link({ tab: "profile", workspace: "leader" });
  if (route === "home") return link({ tab: "home" });
  // Telegram campaigns and old menu buttons may carry arbitrary start
  // parameters.  Only a malformed *known object contract* is an invalid
  // destination; every other value is a safe normal launch.
  if (/^(events?|projects?|tasks?|opportunities?|users?|admin\/events?)(?:\/|_)/.test(route)) {
    return link({ invalid: true });
  }
  return null;
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
  initialEventScope: "mine" | null,
  initialCommunitySection: CommunitySection | null,
  initialItemId: number | null,
  initialMediaRoute: "guide" | "files" | "era" | "ksoors" | null,
  isDeepLinkedTab: boolean,
) {
  if (tab === "home") {
    if (isDeepLinkedTab && initialActivitySection === "tasks") {
      return <Suspense fallback={RouteFallback}><TasksScreen initialItemId={initialItemId} onBack={() => navigateToTab("home")} /></Suspense>;
    }
    if (isDeepLinkedTab && initialActivitySection) return <Suspense fallback={RouteFallback}><ActivityScreen initialSection={initialActivitySection} initialItemId={initialItemId} /></Suspense>;
    return (
      <HomeScreen
        user={user}
        onOpenProfile={() => navigateToRoute("profile")}
        onOpenProgress={() => navigateToRoute("progress")}
        onOpenDevelopment={() => navigateToRoute("development")}
        onOpenAssessments={() => navigateToRoute("development/assessments")}
        onOpenEvents={() => navigateToRoute("events")}
        onOpenEvent={(id) => navigateToRoute(`events/${id}`)}
        onOpenProject={(id) => navigateToRoute(`projects/${id}`)}
        onOpenTask={(id) => navigateToRoute(`tasks/${id}`)}
        onOpenTasks={() => navigateToRoute("tasks")}
        onOpenCommunity={() => navigateToRoute("opportunities")}
        onOpenOpportunity={(id) => navigateToRoute(`opportunities/${id}`)}
        onOpenProjects={() => navigateToRoute("projects")}
      />
    );
  }
  if (tab === "projects") return <Suspense fallback={RouteFallback}><ProjectsScreen initialProjectId={initialProjectId} /></Suspense>;
  if (tab === "events") {
    if (isDeepLinkedTab && initialActivitySection && initialActivitySection !== "events") {
      return <Suspense fallback={RouteFallback}><ActivityScreen initialSection={initialActivitySection} initialItemId={initialItemId} /></Suspense>;
    }
    return (
      <Suspense fallback={RouteFallback}>
        <EventsScreen
          canEdit={user.is_admin || user.permissions?.includes("events.manage")}
          key={initialEventScope ?? "all"}
          initialItemId={isDeepLinkedTab ? initialItemId : null}
          initialScope={initialEventScope ?? undefined}
        />
      </Suspense>
    );
  }
  if (tab === "community") return <Suspense fallback={RouteFallback}><CommunityScreen initialSection={isDeepLinkedTab ? initialCommunitySection : null} initialItemId={isDeepLinkedTab ? initialItemId : null} initialMediaRoute={isDeepLinkedTab ? initialMediaRoute : null} /></Suspense>;
  return <Suspense fallback={RouteFallback}><ProfileScreen onOpenDevelopment={() => navigateToRoute("development")} /></Suspense>;
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

  if (auth.status === "loading") return <div className="era-page era-discover-page" role="status">Загрузка ЭРА…</div>;
  if (auth.status === "error") return <AuthErrorScreen code={auth.code} detail={auth.detail} onRetry={auth.refresh} />;

  const { user } = auth;
  if (user.application_status === "rejected" || user.is_blocked) return <BlockedScreen />;

  const goHome = () => navigateToTab("home");
  if (deepLink?.invalid) return <ObjectUnavailableScreen onHome={goHome} />;
  if (deepLink?.workspace === "admin" && !user.is_admin) return <ObjectUnavailableScreen onHome={goHome} />;
  if (deepLink?.workspace === "leader" && !user.is_leader) return <ObjectUnavailableScreen onHome={goHome} />;

  if (user.application_status === "pending" || user.application_status === "needs_info") {
    return (
      <UserLayout activeTab={activeTab} onTabChange={handleTabChange}>
        {activeTab === "home" ? (
          <PendingScreen status={user.application_status} onRefresh={auth.refresh} />
        ) : (
          renderTab(activeTab, user, initialProjectId, deepLink?.activitySection ?? null, deepLink?.eventScope ?? null, deepLink?.communitySection ?? null, deepLink?.itemId ?? null, deepLink?.mediaRoute ?? null, deepLink?.tab === activeTab)
        )}
      </UserLayout>
    );
  }

  if (deepLink?.userId) {
    return (
      <UserLayout activeTab="home" onTabChange={handleTabChange}>
        <Suspense fallback={RouteFallback}>
          <UserPublicProfileScreen
            userId={deepLink.userId}
            onBack={() => (window.history.length > 1 ? window.history.back() : navigateToRoute("people"))}
          />
        </Suspense>
      </UserLayout>
    );
  }

  if (deepLink?.orbitCatalog === "people") {
    return (
      <UserLayout activeTab="home" onTabChange={handleTabChange}>
        <Suspense fallback={RouteFallback}>
          <PeopleScreen
            onBack={() => navigateToTab("home")}
            onOpenUser={(id) => navigateToRoute(`users/${id}`)}
          />
        </Suspense>
      </UserLayout>
    );
  }
  if (deepLink?.orbitCatalog === "teams") {
    return (
      <UserLayout activeTab="home" onTabChange={handleTabChange}>
        <Suspense fallback={RouteFallback}>
          <TeamsScreen
            onBack={() => navigateToTab("home")}
            onOpenProject={(id) => navigateToRoute(`projects/${id}`)}
          />
        </Suspense>
      </UserLayout>
    );
  }
  if (deepLink?.orbitCatalog === "ideas") {
    return (
      <UserLayout activeTab="home" onTabChange={handleTabChange}>
        <Suspense fallback={RouteFallback}>
          <IdeasScreen
            onBack={() => navigateToTab("home")}
            onOpenProject={(id) => navigateToRoute(`projects/${id}`)}
          />
        </Suspense>
      </UserLayout>
    );
  }

  if (deepLink?.specialScreen === "progress") {
    return (
      <UserLayout activeTab="home" onTabChange={handleTabChange}>
        <Suspense fallback={RouteFallback}>
          <ProgressScreen
            onBack={() => window.history.length > 1 ? window.history.back() : navigateToTab("home")}
            onOpenProjects={() => navigateToTab("projects")}
            onOpenTasks={() => navigateToRoute("tasks")}
            onOpenEvents={() => navigateToTab("events")}
          />
        </Suspense>
      </UserLayout>
    );
  }

  if (deepLink?.specialScreen === "development") {
    const developmentRoute = deepLink.developmentRoute ?? "home";
    return (
      <UserLayout activeTab="home" onTabChange={handleTabChange}>
        <Suspense fallback={RouteFallback}>
          {developmentRoute === "home" ? (
            <VectorHomeScreen
              onNavigate={(route) => navigateToRoute(`development/${route}`)}
              onBack={() => window.history.length > 1 ? window.history.back() : navigateToTab("home")}
            />
          ) : (
            <DevelopmentScreen
              route={developmentRoute}
              onNavigate={(route) => navigateToRoute(route === "home" ? "development" : `development/${route}`)}
              onBack={() => window.history.length > 1 ? window.history.back() : navigateToTab("home")}
            />
          )}
        </Suspense>
      </UserLayout>
    );
  }

  if (deepLink?.specialScreen === "era-pro") {
    return (
      <UserLayout activeTab="community" onTabChange={handleTabChange}>
        <Suspense fallback={RouteFallback}>
          <EraProScreen onBack={() => window.history.length > 1 ? window.history.back() : navigateToRoute("opportunities")} />
        </Suspense>
      </UserLayout>
    );
  }

  const adminWorkspaceRequested = user.is_admin && (inWorkspace || deepLink?.workspace === "admin");
  const leaderWorkspaceRequested = user.is_leader && (inWorkspace || deepLink?.workspace === "leader");

  if (adminWorkspaceRequested) {
    return <Suspense fallback={RouteFallback}><AdminLayout onExitWorkspace={exitWorkspace}>{deepLink?.adminEventId ? <AdminEventsScreen initialEventId={deepLink.adminEventId} /> : initialProjectId ? <ProjectsScreen initialProjectId={initialProjectId} /> : <AdminScreen />}</AdminLayout></Suspense>;
  }
  if (leaderWorkspaceRequested) {
    return <Suspense fallback={RouteFallback}><LeaderLayout onExitWorkspace={exitWorkspace}>{initialProjectId ? <ProjectsScreen initialProjectId={initialProjectId} /> : <LeaderScreen />}</LeaderLayout></Suspense>;
  }

  return (
    <UserLayout activeTab={activeTab} onTabChange={handleTabChange}>
      {activeTab === "profile" ? (
        <Suspense fallback={RouteFallback}>
          <ProfileScreen
            isAdmin={user.is_admin}
            isLeader={user.is_leader}
            onEnterWorkspace={user.is_admin || user.is_leader ? () => setInWorkspace(true) : undefined}
            onOpenDevelopment={() => navigateToRoute("development")}
          />
        </Suspense>
      ) : renderTab(activeTab, user, initialProjectId, deepLink?.activitySection ?? null, deepLink?.eventScope ?? null, deepLink?.communitySection ?? null, deepLink?.itemId ?? null, deepLink?.mediaRoute ?? null, deepLink?.tab === activeTab)}
    </UserLayout>
  );
}
