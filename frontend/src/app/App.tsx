import { useEffect, useState } from "react";
import type { TabKey } from "../components/BottomNavigation";
import { ActionCell } from "../components/ActionCell";
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
import { EventsScreen } from "../screens/EventsScreen";
import { HomeScreen } from "../screens/HomeScreen";
import { LeaderScreen } from "../screens/LeaderScreen";
import { ObjectUnavailableScreen } from "../screens/ObjectUnavailableScreen";
import { PendingScreen } from "../screens/PendingScreen";
import { ProfileScreen } from "../screens/ProfileScreen";
import { ProgressScreen } from "../screens/ProgressScreen";
import { ProjectsScreen } from "../screens/ProjectsScreen";
import { UserPublicProfileScreen } from "../screens/UserPublicProfileScreen";
import { AdminEventsScreen } from "../screens/admin/AdminEventsScreen";
import type { MiniAppUserSummary } from "../types/auth";

type LegacyActivitySection = "tasks" | "calendar" | "history";
type WorkspaceKind = "admin" | "leader";
type SpecialScreen = "progress" | "development";

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
  invalid: boolean;
}

const TAB_HASH: Record<TabKey, string> = {
  home: "#/home",
  projects: "#/projects",
  events: "#/events",
  community: "#/community",
  profile: "#/profile",
};

function parseOptionalId(value: string | undefined) {
  if (!value) return null;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

function normalizeRoute(value: string) {
  return value.replace(/^\/?/, "").replace(/\/$/, "");
}

function routeFromStartParam(value: string) {
  const normalized = normalizeRoute(value);
  if (normalized === "vector") return "development";
  if (/^vector_checkin_\d{4}_\d{2}$/.test(normalized)) return "development/checkin";
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

function telegramQueryRoute() {
  const query = new URLSearchParams(window.location.search);
  const explicitPath = query.get("eraPath");
  if (explicitPath) return normalizeRoute(explicitPath);
  return routeFromStartParam(query.get("tgWebAppStartParam") ?? "");
}

function routeValue() {
  return telegramQueryRoute() || normalizeRoute(window.location.hash.replace(/^#\/?/, ""));
}

function canonicalizeTelegramQueryRoute() {
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
    invalid: false,
    ...overrides,
  };
}

function parseDeepLink(): DeepLink | null {
  const route = routeValue();
  if (!route) return null;

  let match = route.match(/^admin\/events\/(\d+)$/);
  if (match) {
    const id = parseOptionalId(match[1]);
    return id ? link({ tab: "events", workspace: "admin", adminEventId: id }) : link({ invalid: true });
  }

  match = route.match(/^admin\/projects\/(\d+)$/);
  if (match) {
    const id = parseOptionalId(match[1]);
    return id ? link({ tab: "projects", projectId: id, workspace: "admin" }) : link({ invalid: true });
  }

  match = route.match(/^projects\/(\d+)$/);
  if (match) {
    const id = parseOptionalId(match[1]);
    return id ? link({ tab: "projects", projectId: id }) : link({ invalid: true });
  }
  if (route === "projects") return link({ tab: "projects" });

  match = route.match(/^(tasks|calendar|history)(?:\/(\d+))?$/);
  if (match) {
    const id = match[2] ? parseOptionalId(match[2]) : null;
    if (match[2] && id === null) return link({ invalid: true });
    return link({ tab: "home", activitySection: match[1] as LegacyActivitySection, itemId: id });
  }

  match = route.match(/^events(?:\/(\d+))?$/);
  if (match) {
    const id = match[1] ? parseOptionalId(match[1]) : null;
    if (match[1] && id === null) return link({ invalid: true });
    return link({ tab: "events", itemId: id });
  }

  match = route.match(/^users\/(\d+)$/);
  if (match) {
    const id = parseOptionalId(match[1]);
    return id ? link({ tab: "community", userId: id }) : link({ invalid: true });
  }

  match = route.match(/^(opportunities|auctions|rewards|surveys)(?:\/(\d+))?$/);
  if (match) {
    const id = match[2] ? parseOptionalId(match[2]) : null;
    if (match[2] && id === null) return link({ invalid: true });
    return link({
      tab: "community",
      communitySection: match[1] as CommunitySection,
      itemId: id,
    });
  }

  match = route.match(/^development(?:\/(checkin|assessments|history|goals|privacy))?$/);
  if (match) {
    return link({
      tab: "home",
      specialScreen: "development",
      developmentRoute: (match[1] as DevelopmentRoute | undefined) ?? "home",
    });
  }

  if (route === "progress") return link({ tab: "home", specialScreen: "progress" });
  if (route === "leaderboard") return link({ tab: "community", communitySection: "leaderboard" });
  if (route === "community") return link({ tab: "community" });
  if (route === "profile") return link({ tab: "profile" });
  if (route === "admin") return link({ tab: "profile", workspace: "admin" });
  if (route === "leader") return link({ tab: "profile", workspace: "leader" });
  if (route === "home") return link({ tab: "home" });
  return link({ invalid: true });
}

function navigateToTab(tab: TabKey) {
  if (window.location.hash !== TAB_HASH[tab]) window.location.hash = TAB_HASH[tab];
}

function navigateToRoute(route: string) {
  const target = `#/${normalizeRoute(route)}`;
  if (window.location.hash !== target) window.location.hash = target;
}

function developmentPath(route: DevelopmentRoute) {
  return route === "home" ? "development" : `development/${route}`;
}

function renderTab(
  tab: TabKey,
  user: MiniAppUserSummary,
  projectId: number | null,
  activity: LegacyActivitySection | null,
  community: CommunitySection | null,
  itemId: number | null,
  deep: boolean,
  onTab: (tab: TabKey) => void,
) {
  if (tab === "home") {
    if (deep && activity) return <ActivityScreen initialSection={activity} initialItemId={itemId} />;
    return (
      <HomeScreen
        user={user}
        onOpenProfile={() => navigateToRoute("profile")}
        onOpenProgress={() => navigateToRoute("progress")}
        onOpenDevelopment={() => navigateToRoute("development")}
        onOpenEvents={() => onTab("events")}
        onOpenEvent={(id) => navigateToRoute(`events/${id}`)}
        onOpenProject={(id) => navigateToRoute(`projects/${id}`)}
        onOpenTask={(id) => navigateToRoute(`tasks/${id}`)}
        onOpenCommunity={() => onTab("community")}
        onOpenOpportunity={(id) => navigateToRoute(`opportunities/${id}`)}
      />
    );
  }
  if (tab === "projects") return <ProjectsScreen initialProjectId={projectId} />;
  if (tab === "events") return <EventsScreen initialItemId={deep ? itemId : null} />;
  if (tab === "community") {
    return <CommunityScreen initialSection={deep ? community : null} initialItemId={deep ? itemId : null} />;
  }
  return <ProfileScreen />;
}

export function App() {
  const auth = useAuth();
  const [deepLink, setDeepLink] = useState<DeepLink | null>(() => parseDeepLink());
  const [activeTab, setActiveTab] = useState<TabKey>(deepLink?.tab ?? "home");
  const [inWorkspace, setInWorkspace] = useState(false);

  useEffect(() => {
    canonicalizeTelegramQueryRoute();
    const sync = () => {
      const next = parseDeepLink();
      setDeepLink(next);
      setActiveTab(next?.tab ?? "home");
    };
    window.addEventListener("hashchange", sync);
    window.addEventListener("popstate", sync);
    return () => {
      window.removeEventListener("hashchange", sync);
      window.removeEventListener("popstate", sync);
    };
  }, []);

  const handleTab = (tab: TabKey) => {
    setActiveTab(tab);
    navigateToTab(tab);
  };
  const exitWorkspace = () => {
    setInWorkspace(false);
    navigateToTab("profile");
  };
  const projectId = deepLink?.projectId ?? null;

  if (auth.status === "loading") return null;
  if (auth.status === "error") {
    return <AuthErrorScreen code={auth.code} detail={auth.detail} onRetry={auth.refresh} />;
  }

  const { user } = auth;
  if (user.application_status === "pending" || user.application_status === "needs_info") {
    return <PendingScreen onRefresh={auth.refresh} />;
  }
  if (user.application_status === "rejected" || user.is_blocked) return <BlockedScreen />;

  const goHome = () => navigateToTab("home");
  if (deepLink?.invalid) return <ObjectUnavailableScreen onHome={goHome} />;
  if (deepLink?.workspace === "admin" && !user.is_admin) return <ObjectUnavailableScreen onHome={goHome} />;
  if (deepLink?.workspace === "leader" && !user.is_leader) return <ObjectUnavailableScreen onHome={goHome} />;

  if (deepLink?.userId) {
    return (
      <UserLayout activeTab="community" onTabChange={handleTab}>
        <UserPublicProfileScreen
          userId={deepLink.userId}
          onBack={() => (window.history.length > 1 ? window.history.back() : navigateToTab("community"))}
        />
      </UserLayout>
    );
  }

  if (deepLink?.specialScreen === "progress") {
    return (
      <UserLayout activeTab="home" onTabChange={handleTab}>
        <ProgressScreen
          onBack={() => (window.history.length > 1 ? window.history.back() : navigateToTab("home"))}
          onOpenProjects={() => navigateToTab("projects")}
          onOpenTasks={() => navigateToRoute("tasks")}
          onOpenEvents={() => navigateToTab("events")}
        />
      </UserLayout>
    );
  }

  if (deepLink?.specialScreen === "development") {
    return (
      <UserLayout activeTab="home" onTabChange={handleTab}>
        <DevelopmentScreen
          route={deepLink.developmentRoute ?? "home"}
          onNavigate={(route) => navigateToRoute(developmentPath(route))}
          onBack={() => (window.history.length > 1 ? window.history.back() : navigateToTab("home"))}
        />
      </UserLayout>
    );
  }

  const admin = user.is_admin && (inWorkspace || deepLink?.workspace === "admin");
  const leader = user.is_leader && (inWorkspace || deepLink?.workspace === "leader");

  if (admin) {
    return (
      <AdminLayout onExitWorkspace={exitWorkspace}>
        {deepLink?.adminEventId ? (
          <AdminEventsScreen initialEventId={deepLink.adminEventId} />
        ) : projectId ? (
          <ProjectsScreen initialProjectId={projectId} />
        ) : (
          <AdminScreen />
        )}
      </AdminLayout>
    );
  }

  if (leader) {
    return (
      <LeaderLayout onExitWorkspace={exitWorkspace}>
        {projectId ? <ProjectsScreen initialProjectId={projectId} /> : <LeaderScreen />}
      </LeaderLayout>
    );
  }

  return (
    <UserLayout activeTab={activeTab} onTabChange={handleTab}>
      {activeTab === "profile" ? (
        <>
          <ProfileScreen
            isAdmin={user.is_admin}
            isLeader={user.is_leader}
            onEnterWorkspace={user.is_admin || user.is_leader ? () => setInWorkspace(true) : undefined}
          />
          <section style={{ padding: "0 1.25rem 1.5rem" }}>
            <h2>Развитие</h2>
            <ActionCell
              title="Мой вектор"
              description="Понять себя и текущее состояние"
              onClick={() => navigateToRoute("development")}
            />
            <ActionCell
              title="Мои результаты"
              description="Последний Check-in и личная карта"
              onClick={() => navigateToRoute("development/checkin")}
            />
            <ActionCell
              title="Моя история"
              description="Как менялось состояние"
              onClick={() => navigateToRoute("development/history")}
            />
            <ActionCell
              title="Мои цели"
              description="Один фокус и реальный эксперимент"
              onClick={() => navigateToRoute("development/goals")}
            />
          </section>
        </>
      ) : (
        renderTab(
          activeTab,
          user,
          projectId,
          deepLink?.activitySection ?? null,
          deepLink?.communitySection ?? null,
          deepLink?.itemId ?? null,
          deepLink?.tab === activeTab,
          handleTab,
        )
      )}
    </UserLayout>
  );
}
