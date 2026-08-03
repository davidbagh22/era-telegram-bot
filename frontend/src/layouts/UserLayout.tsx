import type { ReactNode } from "react";

interface UserLayoutProps {
  children: ReactNode;
}

// Bottom navigation and AppHeader land in PR 2 alongside the design system.
export function UserLayout({ children }: UserLayoutProps) {
  return <div style={{ minHeight: "100vh" }}>{children}</div>;
}
