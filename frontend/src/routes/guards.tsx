import type { ReactNode } from "react";
import type { MiniAppUserSummary } from "../types/auth";

interface RequireRoleProps {
  user: MiniAppUserSummary;
  allow: (user: MiniAppUserSummary) => boolean;
  children: ReactNode;
  fallback?: ReactNode;
}

// Frontend gating is UX only — every protected API route re-checks
// permissions server-side (app/api/deps.py, authorization_service.py).
export function RequireRole({ user, allow, children, fallback = null }: RequireRoleProps) {
  return allow(user) ? <>{children}</> : <>{fallback}</>;
}

export const isLeader = (user: MiniAppUserSummary): boolean => user.is_leader;
export const isAdmin = (user: MiniAppUserSummary): boolean => user.is_admin;
