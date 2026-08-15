import type { ReactNode } from "react";
import { BottomNavigation, type TabKey } from "../components/BottomNavigation";
import { useRouteScrollMemory } from "../hooks/useRouteScrollMemory";

interface UserLayoutProps {
  children: ReactNode;
  activeTab: TabKey;
  onTabChange: (tab: TabKey) => void;
}

export function UserLayout({ children, activeTab, onTabChange }: UserLayoutProps) {
  useRouteScrollMemory();
  return (
    <div
      style={{
        minHeight: "100dvh",
        display: "flex",
        flexDirection: "column",
        paddingTop: "env(safe-area-inset-top, 0px)",
        paddingLeft: "env(safe-area-inset-left, 0px)",
        paddingRight: "env(safe-area-inset-right, 0px)",
      }}
    >
      <main style={{ flex: 1, minWidth: 0, paddingBottom: "var(--era-dock-space)" }}>{children}</main>
      <BottomNavigation active={activeTab} onChange={onTabChange} />
    </div>
  );
}
