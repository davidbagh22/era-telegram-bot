import { ApiError, authenticate } from "./client";
import { getInitData } from "../telegram/webApp";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
let tokenPromise: Promise<string> | null = null;

export interface MediaTask {
  id: number;
  title: string;
  description: string;
  deadline: string;
  points: number;
  status: string;
}

export interface MediaHub {
  chat_url: string;
  channel_url: string;
  open_tasks: MediaTask[];
  my_tasks: MediaTask[];
  can_manage: boolean;
}

export interface MediaLibraryItem {
  id: number;
  kind: string;
  title: string;
  description: string | null;
  url: string;
}

export interface MediaContent {
  id: number;
  source_kind: string;
  source_type: string | null;
  source_id: number | null;
  week: number | null;
  theme: string | null;
  rubric: string | null;
  kind: "text" | "poll";
  body: string | null;
  poll_question: string | null;
  poll_options: string[];
  scheduled_at: string | null;
  status: string;
  published_at: string | null;
  telegram_message_id: number | null;
}

export interface MediaConfig {
  auto_enabled: boolean;
  paused_indefinitely: boolean;
  paused_until: string | null;
}

export interface MediaAnalytics {
  planned: number;
  published: number;
  failed: number;
  on_time_rate: number | null;
  tasks_created: number;
  tasks_completed: number;
}

export interface MediaPublishResult {
  ok: boolean;
  code: string;
  message_id: number | null;
}

export interface MediaRequestResult {
  id: number;
  source_type: string;
  source_id: number;
  package_type: string;
  content_id: number | null;
  status: string;
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

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const sessionToken = await token();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${sessionToken}`,
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...(init.headers ?? {}),
    },
  });
  if (!response.ok) {
    let detail = response.statusText || "request_failed";
    try {
      const body = (await response.json()) as { detail?: string };
      detail = body.detail ?? detail;
    } catch {
      // Never print response bodies: media drafts may contain unpublished copy.
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

export const fetchMediaHub = () => request<MediaHub>("/api/v1/media/hub");
export const fetchMediaLibrary = () => request<MediaLibraryItem[]>("/api/v1/media/library");
export const submitMediaIdea = (text: string) =>
  request<MediaContent>("/api/v1/media/ideas", { method: "POST", body: JSON.stringify({ text }) });

export const fetchMediaToday = () => request<MediaContent[]>("/api/v1/media/desk/today");
export const fetchMediaContentPlan = (status?: string) =>
  request<MediaContent[]>(`/api/v1/media/desk/content${status ? `?status=${encodeURIComponent(status)}` : ""}`);
export const fetchMediaConfig = () => request<MediaConfig>("/api/v1/media/desk/config");
export const fetchMediaAnalytics = () => request<MediaAnalytics>("/api/v1/media/desk/analytics");
export const fetchMediaChannelHealth = () =>
  request<{ ok: boolean; detail: string }>("/api/v1/media/desk/channel-health");

export const setMediaAuto = (enabled: boolean) =>
  request<MediaConfig>("/api/v1/media/desk/auto", {
    method: "POST",
    body: JSON.stringify({ enabled }),
  });
export const pauseMedia = (indefinitely = true, until?: string) =>
  request<MediaConfig>("/api/v1/media/desk/pause", {
    method: "POST",
    body: JSON.stringify({ indefinitely, until: until ?? null }),
  });
export const resumeMedia = () =>
  request<MediaConfig>("/api/v1/media/desk/resume", { method: "POST" });
export const skipMediaContent = (contentId: number) =>
  request<MediaContent>(`/api/v1/media/desk/content/${contentId}/skip`, { method: "POST" });
export const rescheduleMediaContent = (contentId: number, scheduledAt: string) =>
  request<MediaContent>(`/api/v1/media/desk/content/${contentId}/reschedule`, {
    method: "POST",
    body: JSON.stringify({ scheduled_at: scheduledAt }),
  });
export const publishMediaContentNow = (contentId: number) =>
  request<MediaPublishResult>(`/api/v1/media/desk/content/${contentId}/publish-now`, { method: "POST" });
export const createMediaTasks = (contentId: number, taskKinds: string[]) =>
  request<MediaTask[]>(`/api/v1/media/desk/content/${contentId}/tasks`, {
    method: "POST",
    body: JSON.stringify({ task_kinds: taskKinds }),
  });

export const requestEventMedia = (eventId: number, packageType = "full") =>
  request<MediaRequestResult>(`/api/v1/media/requests/event/${eventId}`, {
    method: "POST",
    body: JSON.stringify({ package_type: packageType }),
  });
export const requestProjectMedia = (projectId: number, packageType = "full") =>
  request<MediaRequestResult>(`/api/v1/media/requests/project/${projectId}`, {
    method: "POST",
    body: JSON.stringify({ package_type: packageType }),
  });
