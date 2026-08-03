import type { MiniAppUserSummary } from "../types/auth";

interface HomePlaceholderProps {
  user: MiniAppUserSummary;
}

// PR 1 only proves the auth handshake end-to-end. The real Home screen
// (next step, progress, activity) lands in PR 2 — see
// docs/ERA_PLATFORM_PROGRESS.md.
export function HomePlaceholder({ user }: HomePlaceholderProps) {
  return (
    <div style={{ padding: "1.5rem" }}>
      <h1 style={{ fontFamily: "var(--era-font-display)", fontSize: "1.5rem" }}>
        Привет, {user.first_name}
      </h1>
      <p style={{ color: "var(--era-text-muted)" }}>
        Вы вошли как {user.role}
        {user.is_leader ? " · режим руководителя доступен" : ""}
        {user.is_admin ? " · режим администратора доступен" : ""}
      </p>
    </div>
  );
}
