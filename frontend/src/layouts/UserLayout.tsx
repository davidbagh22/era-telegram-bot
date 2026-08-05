import type { ReactNode } from "react";
import { BottomNavigation, type TabKey } from "../components/BottomNavigation";

interface UserLayoutProps {
  children: ReactNode;
  activeTab: TabKey;
  onTabChange: (tab: TabKey) => void;
}

// AppHeader (profile summary, notifications) is deferred until a screen
// actually needs one — Home covers that ground itself for now.
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
      <div style={{ flex: 1 }}>{children}</div>
      <BottomNavigation active={activeTab} onChange={onTabChange} />
    </div>
  );
}
