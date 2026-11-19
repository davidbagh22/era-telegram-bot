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
export function AppShell({ children, context = "home" }: AppShellProps) {
  useEffect(() => {
    document.documentElement.dataset.orbitContext = context;
    return () => {
      delete document.documentElement.dataset.orbitContext;
    };
  }, [context]);

  return (
    <div className="era-app-shell" data-orbit-context={context}>
      <OrbitAmbient />
      <div className="era-app-shell__content">{children}</div>
    </div>
  );
}
