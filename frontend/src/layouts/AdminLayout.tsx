import type { ReactNode } from "react";

interface AdminLayoutProps {
  children: ReactNode;
  /** Present only for a user who actually has a personal Mini App
   * experience to return to (i.e. every admin/leader — see App.tsx's
   * workspace-mode switch). Omitted, not just hidden, in the one caller
   * (App.tsx's initialProjectId deep-link branch) that isn't inside the
   * switcher flow at all. */
  onExitWorkspace?: () => void;
}

// Compact by design — this used to be a full-width gradient strip reading
// "ЭРА / ADMIN" (see git history), which read as a permanent, inescapable
// "you are now in the serious admin system" banner rather than one mode
// among several. It's still a workspace, so it still gets a name — the
// name just isn't shouting at you the whole time you're using it.
export function AdminLayout({ children, onExitWorkspace }: AdminLayoutProps) {
  return (
    <div style={{ minHeight: "100vh", paddingTop: "env(safe-area-inset-top, 0px)" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "0.75rem",
          padding: "0.625rem 1.25rem",
          borderBottom: "1px solid var(--era-border)",
        }}
      >
        <div style={{ display: "flex", alignItems: "baseline", gap: "0.5rem" }}>
          <strong style={{ fontFamily: "var(--era-font-display)", fontSize: "0.9375rem" }}>ЭРА</strong>
          <span style={{ fontSize: "0.75rem", color: "var(--era-text-muted)" }}>Управление</span>
        </div>
        {onExitWorkspace && (
          <button
            type="button"
            onClick={onExitWorkspace}
            style={{
              minHeight: "auto",
              padding: "0.3rem 0.7rem",
              fontSize: "0.75rem",
              border: "1px solid var(--era-border)",
              background: "var(--era-surface)",
              borderRadius: "var(--era-radius-pill)",
            }}
          >
            ← Личное
          </button>
        )}
      </div>
      {children}
    </div>
  );
}
