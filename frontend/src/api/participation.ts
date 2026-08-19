import { authenticate, ApiError } from "./client";
import { getInitData } from "../telegram/webApp";

export interface ParticipationState {
  participation_mode: "ACTIVE" | "LIGHT" | "PAUSED" | "OBSERVER" | "EXITED";
  activity_state: "ADAPTATION" | "ACTIVE" | "COOLING" | "INACTIVE" | "DORMANT" | "ARCHIVE_CANDIDATE";
  last_meaningful_at: string | null;
  pause_until: string | null;
  onboarding_version: number;
  current_onboarding_version: number;
  onboarding_completed_at: string | null;
  needs_onboarding: boolean;
}

async function freshToken(): Promise<string> {
  const raw = new URLSearchParams(window.location.search).get("devTelegramId");
  const devTelegramId = raw ? Number(raw) : undefined;
  const auth = await authenticate(getInitData(), devTelegramId);
  return auth.token;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = await freshToken();
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      detail = body.detail ?? detail;
    } catch {
      // Keep status text.
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

export function fetchParticipation(): Promise<ParticipationState> {
  return request<ParticipationState>("/participation/me");
}

export function completeParticipationOnboarding(): Promise<ParticipationState> {
  return request<ParticipationState>("/participation/onboarding/complete", { method: "POST" });
}

export function updateParticipationMode(
  mode: ParticipationState["participation_mode"],
  options: { pauseMonths?: 1 | 3; pauseUntil?: string } = {},
): Promise<ParticipationState> {
  return request<ParticipationState>("/participation/mode", {
    method: "POST",
    body: JSON.stringify({
      mode,
      pause_months: options.pauseMonths,
      pause_until: options.pauseUntil,
    }),
  });
}

export function saveInactivityReason(reason: string): Promise<ParticipationState> {
  return request<ParticipationState>("/participation/reactivation/reason", {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}
