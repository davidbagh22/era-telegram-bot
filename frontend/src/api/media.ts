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

export type MediaAccessLevel = "no_access" | "pending" | "member" | "leader" | "admin";

export interface MediaPermissions {
  tools_read: boolean;
  content_plan_read: boolean;
  content_plan_write: boolean;
  members_manage: boolean;
  analytics_read: boolean;
  publications_manage: boolean;
}

export interface MediaHub {
  access_level: MediaAccessLevel;
  permissions: MediaPermissions;
  chat_url: string;
  channel_url: string;
  open_tasks: MediaTask[];
  my_tasks: MediaTask[];
  can_manage: boolean;
}

export interface MediaApplicant {
  id: number;
  name: string;
  applied_at: string;
}

export interface MediaMember {
  id: number;
  name: string;
}

export interface MediaLibraryItem {
  id: number;
  kind: string;
  title: string;
  description: string | null;
  url: string;
  // "internal_route" -> an in-app hash route (e.g. "media/guide"), must be
  // opened with SPA navigation, never window.open/openLink (DELTA ToR §32-34).
  destination_type: "internal_route" | "external_url" | "file";
}

export interface MediaGuide {
  principles: string[];
  post: string[];
  reels: string[];
  visual: string[];
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
  channel_posts_period: number;
  chat_messages_period: number;
  chat_active_authors_period: number;
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
export const applyToMedia = () => request<MediaHub>("/api/v1/media/apply", { method: "POST" });
export const fetchMediaLibrary = () => request<MediaLibraryItem[]>("/api/v1/media/library");
export const fetchMediaGuide = () => request<MediaGuide>("/api/v1/media/guide");
export const fetchMediaApplications = () => request<MediaApplicant[]>("/api/v1/media/team/applications");
export const fetchMediaMembers = () => request<MediaMember[]>("/api/v1/media/team/members");
export const decideMediaApplicant = (userId: number, action: "approve" | "reject" | "revoke") =>
  request<{ status: string }>(`/api/v1/media/team/${userId}/decide`, {
    method: "POST",
    body: JSON.stringify({ action }),
  });
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
