import { ApiError, authenticate } from "./client";
import { getInitData } from "../telegram/webApp";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
let tokenPromise: Promise<string> | null = null;

export type ChannelApprovalPreview = {
  day: string;
  target: string | null;
  digest: string;
  text: string;
  approved: boolean;
  preview: string;
};

export type ChannelApprovalResult = {
  day: string;
  target: string;
  digest: string;
  already: boolean;
};

function devTelegramId(): number | undefined {
  const raw = new URLSearchParams(window.location.search).get("devTelegramId");
  if (!raw) return undefined;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : undefined;
}

async function ensureToken(): Promise<string> {
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

async function request<T>(path: string, init: RequestInit = {}, retryAuth = true): Promise<T> {
  const token = await ensureToken();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(init.body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(init.headers ?? {}),
    },
  });
  if (response.status === 401 && retryAuth) {
    tokenPromise = null;
    return request<T>(path, init, false);
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* keep statusText */
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

export function fetchChannelApprovalToday(): Promise<ChannelApprovalPreview> {
  return request<ChannelApprovalPreview>("/api/v1/admin/channel-approval/today");
}

export function approveChannelPublicationToday(
  day: string,
  target: string,
  digest: string,
): Promise<ChannelApprovalResult> {
  return request<ChannelApprovalResult>("/api/v1/admin/channel-approval/approve", {
    method: "POST",
    body: JSON.stringify({ day, target, digest }),
  });
}
