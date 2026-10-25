import { ApiError, authenticate } from "./client";
import { getInitData } from "../telegram/webApp";
import type {
  AutoContentCalendarEntry,
  AutoContentCustomHoliday,
  AutoContentHistoryEntry,
  AutoContentItemPatch,
  AutoContentOverview,
  AutoContentPreview,
  AutoContentSettings,
} from "../types/autocontent";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
let tokenPromise: Promise<string> | null = null;

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

async function parseDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: string };
    return body.detail ?? response.statusText;
  } catch {
    return response.statusText;
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  retryAuth = true,
): Promise<T> {
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
    throw new ApiError(response.status, await parseDetail(response));
  }
  return (await response.json()) as T;
}

export function fetchAutoContentOverview(): Promise<AutoContentOverview> {
  return request<AutoContentOverview>("/api/v1/admin/autocontent/overview");
}

export function fetchAutoContentCalendar(
  start: string,
  days = 31,
): Promise<AutoContentCalendarEntry[]> {
  return request<AutoContentCalendarEntry[]>(
    `/api/v1/admin/autocontent/calendar?start=${encodeURIComponent(start)}&days=${days}`,
  );
}

export function fetchAutoContentHistory(limit = 100): Promise<AutoContentHistoryEntry[]> {
  return request<AutoContentHistoryEntry[]>(`/api/v1/admin/autocontent/history?limit=${limit}`);
}

export function patchAutoContentSettings(
  changes: Partial<AutoContentSettings>,
): Promise<AutoContentSettings> {
  return request<AutoContentSettings>("/api/v1/admin/autocontent/settings", {
    method: "PATCH",
    body: JSON.stringify(changes),
  });
}

export function patchAutoContentItem(
  contentId: string,
  changes: AutoContentItemPatch,
): Promise<{ content_id: string; text: string; is_enabled: boolean; is_skipped: boolean; title: string | null }> {
  return request(`/api/v1/admin/autocontent/items/${encodeURIComponent(contentId)}`, {
    method: "PATCH",
    body: JSON.stringify(changes),
  });
}

export function skipAutoContentItem(contentId: string): Promise<{ content_id: string; skipped: boolean }> {
  return request(`/api/v1/admin/autocontent/items/${encodeURIComponent(contentId)}/skip`, {
    method: "POST",
  });
}

export function sendAutoContentItemNow(
  contentId: string,
): Promise<{ status: string; delivery_id: number | null; message_id: number | null }> {
  return request(`/api/v1/admin/autocontent/items/${encodeURIComponent(contentId)}/send-now`, {
    method: "POST",
  });
}

export function previewAutoContent(text: string): Promise<AutoContentPreview> {
  return request<AutoContentPreview>("/api/v1/admin/autocontent/preview", {
    method: "POST",
    body: JSON.stringify({ text }),
  });
}

export function createAutoContentHoliday(payload: {
  date_key: string;
  title: string;
  text: string;
}): Promise<AutoContentCustomHoliday> {
  return request<AutoContentCustomHoliday>("/api/v1/admin/autocontent/holidays", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
