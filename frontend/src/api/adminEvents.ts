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

export interface EventProgramDraftItem {
  title: string;
  description?: string;
  time?: string;
  responsible?: string;
  notes?: string;
}

export interface EventTaskDraftItem {
  title: string;
  description?: string;
  deadline?: string;
  points?: number;
  confirmation_required?: boolean;
  reviewer?: string;
}

export interface AdminEventDraft {
  id: number;
  status: string;
  wizard_step: number;
  is_complete: boolean;
  title: string;
  short_description: string;
  full_description: string;
  project_id: number | null;
  category: string | null;
  event_date: string;
  event_time: string;
  end_time: string | null;
  location: string;
  address: string | null;
  attendance_mode: "offline" | "online" | "hybrid";
  has_poster: boolean;
  registration_required: boolean;
  participant_limit: number | null;
  registration_close_at: string | null;
  waitlist_enabled: boolean;
  registration_audience: string;
  chat_url: string | null;
  organizer: string | null;
  participant_value: string | null;
  contact: string | null;
  program: EventProgramDraftItem[];
  participant_tasks: EventTaskDraftItem[];
  points_for_visit: number;
  reminders: number[];
  broadcast_enabled: boolean;
  broadcast_targets: string[];
  broadcast_estimate: number;
}

export type AdminEventDraftPatch = Partial<{
  wizard_step: number;
  title: string;
  short_description: string;
  full_description: string;
  project_id: number | null;
  category: string;
  event_date: string;
  event_time: string;
  end_time: string;
  location: string;
  address: string;
  attendance_mode: "offline" | "online" | "hybrid";
  registration_required: boolean;
  participant_limit: number | null;
  registration_close_at: string | null;
  waitlist_enabled: boolean;
  registration_audience: string;
  chat_url: string | null;
  organizer: string | null;
  participant_value: string | null;
  contact: string | null;
  program: EventProgramDraftItem[];
  participant_tasks: EventTaskDraftItem[];
  points_for_visit: number;
  reminders: number[];
  broadcast_enabled: boolean;
  broadcast_targets: string[];
}>;

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

async function parseError(response: Response): Promise<never> {
  let detail = response.statusText;
  try {
    detail = ((await response.json()) as { detail?: string }).detail ?? detail;
  } catch {
    // Keep status text. Never log response bodies or credentials here.
  }
  throw new ApiError(response.status, detail);
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const sessionToken = await token();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${sessionToken}`,
      ...(init?.body instanceof FormData ? {} : init?.body ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) return parseError(response);
  return (await response.json()) as T;
}

export async function createAdminEvent(payload: AdminEventCreatePayload): Promise<AdminEventCreateResult> {
  return requestJson<AdminEventCreateResult>("/api/v1/admin/events/create", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function createEventDraft(): Promise<AdminEventDraft> {
  return requestJson<AdminEventDraft>("/api/v1/admin/events/drafts", { method: "POST" });
}

export function listEventDrafts(): Promise<AdminEventDraft[]> {
  return requestJson<AdminEventDraft[]>("/api/v1/admin/events/drafts");
}

export function fetchEventDraft(eventId: number): Promise<AdminEventDraft> {
  return requestJson<AdminEventDraft>(`/api/v1/admin/events/${eventId}/draft`);
}

export function saveEventDraft(eventId: number, patch: AdminEventDraftPatch): Promise<AdminEventDraft> {
  return requestJson<AdminEventDraft>(`/api/v1/admin/events/${eventId}/draft`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export function publishEventDraft(eventId: number): Promise<AdminEventDraft> {
  return requestJson<AdminEventDraft>(`/api/v1/admin/events/${eventId}/publish`, { method: "POST" });
}

export function cancelAdminEvent(eventId: number): Promise<AdminEventDraft> {
  return requestJson<AdminEventDraft>(`/api/v1/admin/events/${eventId}/cancel`, { method: "POST" });
}

export async function uploadEventPoster(eventId: number, file: File): Promise<AdminEventDraft> {
  const body = new FormData();
  body.append("file", file);
  return requestJson<AdminEventDraft>(`/api/v1/admin/events/${eventId}/poster`, {
    method: "POST",
    body,
  });
}

export function removeEventPoster(eventId: number): Promise<AdminEventDraft> {
  return requestJson<AdminEventDraft>(`/api/v1/admin/events/${eventId}/poster/remove`, { method: "POST" });
}

export async function downloadEventParticipants(
  eventId: number,
  format: "xlsx" | "csv",
): Promise<void> {
  const sessionToken = await token();
  const response = await fetch(`${API_BASE_URL}/api/v1/admin/events/${eventId}/participants/export.${format}`, {
    headers: { Authorization: `Bearer ${sessionToken}` },
  });
  if (!response.ok) return parseError(response);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `ERA_event_${eventId}_participants.${format}`;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 500);
}
