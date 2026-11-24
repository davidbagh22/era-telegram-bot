import { useEffect, type ReactNode } from "react";
import { OrbitAmbient } from "../components/OrbitAmbient";

export type OrbitContext = "home" | "events" | "projects" | "community" | "profile" | "workspace";

interface AppShellProps {
  children: ReactNode;
  context?: OrbitContext;
}

/**
 * Single shell above user/leader/admin layouts: one OrbitAmbient lifecycle.
 */
export function OrbitContextBoundary({ children, context = "home" }: AppShellProps) {
  useEffect(() => {
    document.documentElement.dataset.orbitContext = context;
    return () => {
      delete document.documentElement.dataset.orbitContext;
    };
  }, [context]);

  return <>{children}</>;
}

/** Keep the same ambient DOM node across auth, tabs and workspace changes. */
export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="era-app-shell">
      <OrbitAmbient />
      <div className="era-app-shell__content">{children}</div>
    </div>
  );
}
