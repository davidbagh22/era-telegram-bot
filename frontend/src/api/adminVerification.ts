import { authenticate, ApiError } from "./client";
import { getInitData } from "../telegram/webApp";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export interface VerificationRow {
  telegram_id: number;
  user_id: number | null;
  name: string;
  registration_status: string;
  is_current_member: boolean;
  retained_by_admin: boolean;
  delivery_status: string;
  attempt_count: number;
  sent_at: string | null;
  last_attempt_at: string | null;
}

export interface VerificationCampaign {
  id: number;
  status: "active" | "completed";
  duration_hours: number;
  started_at: string;
  ends_at: string;
  completed_at: string | null;
  group_message_id: number | null;
  group_pinned: boolean;
  counts: Record<string, number>;
  delivery_counts: Record<string, number>;
  rows: VerificationRow[];
}

export interface VerificationSelectionResult {
  requested: number;
  changed: number;
  failed: number;
}

async function token(): Promise<string> {
  const raw = new URLSearchParams(window.location.search).get("devTelegramId");
  const devTelegramId = raw ? Number(raw) : undefined;
  const result = await authenticate(getInitData(), devTelegramId);
  return result.token;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const authToken = await token();
  const response = await fetch(`${API_BASE_URL}/api/v1${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${authToken}`,
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
      // Keep the HTTP status text.
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function fetchVerificationCampaign(): Promise<VerificationCampaign | null> {
  return request<VerificationCampaign | null>("/admin/community-verification");
}

export function startVerificationCampaign(
  durationHours: number,
  pinGroupMessage: boolean,
): Promise<VerificationCampaign> {
  return request<VerificationCampaign>("/admin/community-verification/start", {
    method: "POST",
    body: JSON.stringify({
      duration_hours: durationHours,
      pin_group_message: pinGroupMessage,
      idempotency_key: `ui:${new Date().toISOString().slice(0, 10)}:${durationHours}`,
    }),
  });
}

export function remindVerificationSelection(
  telegramIds: number[],
): Promise<VerificationSelectionResult> {
  return request<VerificationSelectionResult>("/admin/community-verification/remind", {
    method: "POST",
    body: JSON.stringify({ telegram_ids: telegramIds }),
  });
}

export function retainVerificationSelection(
  telegramIds: number[],
): Promise<VerificationSelectionResult> {
  return request<VerificationSelectionResult>("/admin/community-verification/retain", {
    method: "POST",
    body: JSON.stringify({ telegram_ids: telegramIds }),
  });
}

export function removeVerificationSelection(
  telegramIds: number[],
): Promise<VerificationSelectionResult> {
  return request<VerificationSelectionResult>("/admin/community-verification/remove", {
    method: "POST",
    body: JSON.stringify({
      telegram_ids: telegramIds,
      confirmation: "REMOVE_SELECTED",
    }),
  });
}
