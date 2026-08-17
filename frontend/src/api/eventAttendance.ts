import { ApiError, authenticate } from "./client";
import { getInitData } from "../telegram/webApp";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
let tokenPromise: Promise<string> | null = null;

export interface EventAttendanceState {
  event_id: number;
  event_status: string;
  eligible: boolean;
  confirmation_open: boolean;
  confirmed: boolean;
  points_for_visit: number;
  points_awarded: boolean;
}

export interface EventAttendanceConfirmation extends EventAttendanceState {
  awarded_now: number;
  already_confirmed: boolean;
}

export interface AdminEventAttendanceState {
  event_id: number;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  attendance_code: string | null;
  can_start: boolean;
  can_complete: boolean;
  confirmation_open: boolean;
  notified_count: number;
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

async function parseError(response: Response): Promise<never> {
  let detail = response.statusText;
  try {
    detail = ((await response.json()) as { detail?: string }).detail ?? detail;
  } catch {
    // Do not expose response bodies, credentials, or participant data in logs.
  }
  throw new ApiError(response.status, detail);
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const sessionToken = await token();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${sessionToken}`,
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) return parseError(response);
  return (await response.json()) as T;
}

export function fetchEventAttendanceState(eventId: number): Promise<EventAttendanceState> {
  return requestJson<EventAttendanceState>(`/api/v1/events/${eventId}/attendance`);
}

export function confirmEventAttendance(
  eventId: number,
  code: string,
): Promise<EventAttendanceConfirmation> {
  return requestJson<EventAttendanceConfirmation>(`/api/v1/events/${eventId}/attendance/confirm`, {
    method: "POST",
    body: JSON.stringify({ code }),
  });
}

export function fetchAdminEventAttendanceState(eventId: number): Promise<AdminEventAttendanceState> {
  return requestJson<AdminEventAttendanceState>(`/api/v1/admin/events/${eventId}/attendance-state`);
}

export function startAdminEvent(eventId: number): Promise<AdminEventAttendanceState> {
  return requestJson<AdminEventAttendanceState>(`/api/v1/admin/events/${eventId}/start`, {
    method: "POST",
  });
}

export function completeAdminEvent(eventId: number): Promise<AdminEventAttendanceState> {
  return requestJson<AdminEventAttendanceState>(`/api/v1/admin/events/${eventId}/complete`, {
    method: "POST",
  });
}
