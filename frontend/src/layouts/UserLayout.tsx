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
      {/* minWidth: 0 — a flex item's default min-width is its content's
          width, not 0; without this, a wide-enough descendant (e.g.
          PillTabs' scrollable row) pushes this wider instead of shrinking
          to the viewport, and its own overflowX:auto never gets a chance
          to contain it. See PillTabs.tsx's own comment on the same root
          cause, found by frontend/e2e/responsive.spec.ts. */}
      <div style={{ flex: 1, minWidth: 0 }}>{children}</div>
      <BottomNavigation active={activeTab} onChange={onTabChange} />
    </div>
  );
}
