import type { ReactNode } from "react";
import { FloatingNav, type TabKey } from "../components/FloatingNav";
import { OnboardingGate } from "../components/OnboardingGate";
import { ParticipationModeControl } from "../components/ParticipationModeControl";
import { OrbitContextBoundary, type OrbitContext } from "./AppShell";

interface UserLayoutProps {
  children: ReactNode;
  activeTab: TabKey;
  onTabChange: (tab: TabKey) => void;
}

function tabToContext(tab: TabKey): OrbitContext {
  if (tab === "home") return "home";
  if (tab === "events") return "events";
  if (tab === "projects") return "projects";
  if (tab === "community") return "community";
  return "profile";
}

export function UserLayout({ children, activeTab, onTabChange }: UserLayoutProps) {
  return (
    <OrbitContextBoundary context={tabToContext(activeTab)}>
      <OnboardingGate>
        <div className="era-user-layout"
          style={{
            minHeight: "100dvh",
            display: "flex",
            flexDirection: "column",
            paddingTop: "var(--era-safe-top)",
            paddingBottom: "var(--era-bottom-nav-clearance, calc(6rem + env(safe-area-inset-bottom, 0px)))",
          }}
        >
          <div style={{ flex: 1, minWidth: 0 }}>{children}</div>
          <ParticipationModeControl />
          <FloatingNav active={activeTab} onChange={onTabChange} />
        </div>
      </OnboardingGate>
    </OrbitContextBoundary>
  );
}
