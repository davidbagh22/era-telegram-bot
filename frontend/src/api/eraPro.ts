import { authenticate, ApiError } from "./client";
import { getInitData } from "../telegram/webApp";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
let eraProToken: string | null = null;

export type EraProStatus = "locked" | "available" | "submitted" | "needs_info" | "approved" | "declined";

export interface EraProApplication {
  id: number;
  status: string;
  motivation: string;
  directions: string[];
  target_result: string;
  community_value: string;
  portfolio_url: string | null;
  admin_comment: string | null;
  submitted_at: string;
  updated_at: string;
}

export interface EraProMe {
  threshold: number;
  points: number;
  remaining_points: number;
  eligible: boolean;
  status: EraProStatus;
  has_access: boolean;
  application: EraProApplication | null;
}

export interface EraProApplicationPayload {
  motivation: string;
  directions: string[];
  target_result: string;
  community_value: string;
  portfolio_url?: string | null;
}

export interface EraProAdminApplication extends EraProApplication {
  user_id: number;
  full_name: string;
  username: string | null;
  points: number;
  participation_status: string | null;
}

async function token(): Promise<string> {
  if (eraProToken) return eraProToken;
  const raw = new URLSearchParams(window.location.search).get("devTelegramId");
  const devTelegramId = raw ? Number(raw) : undefined;
  const auth = await authenticate(getInitData(), devTelegramId);
  eraProToken = auth.token;
  return eraProToken;
}

async function request<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const bearer = await token();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${bearer}`,
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...(init.headers ?? {}),
    },
  });
  if (response.status === 401 && retry) {
    eraProToken = null;
    return request<T>(path, init, false);
  }
  if (!response.ok) {
    let detail = response.statusText;
    try { detail = ((await response.json()) as { detail?: string }).detail ?? detail; } catch { /* no body */ }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

export function fetchEraPro(): Promise<EraProMe> {
  return request<EraProMe>("/api/v1/era-pro/me");
}

export function submitEraPro(payload: EraProApplicationPayload, resubmit = false): Promise<EraProMe> {
  return request<EraProMe>(`/api/v1/era-pro/${resubmit ? "resubmit" : "apply"}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchAdminEraProApplications(): Promise<EraProAdminApplication[]> {
  return request<EraProAdminApplication[]>("/api/v1/admin/era-pro/applications");
}

export function decideEraProApplication(
  applicationId: number,
  decision: "needs_info" | "approved" | "declined",
  comment?: string,
): Promise<EraProAdminApplication> {
  return request<EraProAdminApplication>(`/api/v1/admin/era-pro/applications/${applicationId}/decision`, {
    method: "POST",
    body: JSON.stringify({ decision, comment: comment?.trim() || null }),
  });
}
