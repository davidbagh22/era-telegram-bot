import { ApiError, authenticate } from "./client";
import { getInitData } from "../telegram/webApp";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
let tokenPromise: Promise<string> | null = null;

export interface AdminEventCreatePayload {
  title: string;
  description: string;
  event_date: string;
  event_time: string;
  location: string;
  format: string;
  participant_limit?: number;
  points_for_visit: number;
  needs_volunteers: boolean;
  additional_info?: string;
  publish: boolean;
}

export interface AdminEventCreateResult {
  id: number;
  title: string;
  status: string;
  event_date: string;
  event_time: string;
  location: string;
}

function devTelegramId(): number | undefined {
  const raw = new URLSearchParams(window.location.search).get("devTelegramId");
  if (!raw) return undefined;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : undefined;
}

async function token(): Promise<string> {
  if (!tokenPromise) {
    tokenPromise = authenticate(getInitData(), devTelegramId())
      .then((result) => result.token)
      .catch((error) => {
        tokenPromise = null;
        throw error;
      });
  }
  return tokenPromise;
}

export async function createAdminEvent(payload: AdminEventCreatePayload): Promise<AdminEventCreateResult> {
  const sessionToken = await token();
  const response = await fetch(`${API_BASE_URL}/api/v1/admin/events/create`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${sessionToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = ((await response.json()) as { detail?: string }).detail ?? detail;
    } catch {
      // Keep the HTTP status text; no credentials or response body are logged.
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as AdminEventCreateResult;
}
