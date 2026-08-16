import type { ReactNode } from "react";
import { BottomNavigation, type TabKey } from "../components/BottomNavigation";
import { ContextHelp } from "../components/ContextHelp";

interface UserLayoutProps {
  children: ReactNode;
  activeTab: TabKey;
  onTabChange: (tab: TabKey) => void;
}

export function UserLayout({ children, activeTab, onTabChange }: UserLayoutProps) {
  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        paddingTop: "env(safe-area-inset-top, 0px)",
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>{children}</div>
      <ContextHelp mode="user" />
      <BottomNavigation active={activeTab} onChange={onTabChange} />
    </div>
  );
}
