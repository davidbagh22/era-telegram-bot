import { authenticate, ApiError } from "./client";
import { getInitData } from "../telegram/webApp";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export interface ParticipationSummary {
  historical_approved: number;
  current_roster: number;
  active_base: number;
  returned_30d: number;
  new_30d: number;
  modes: Record<string, number>;
  states: Record<string, number>;
}

export interface ParticipationPerson {
  id: number;
  telegram_id: number;
  name: string;
  username: string | null;
  participation_mode: string;
  activity_state: string;
  last_meaningful_at: string | null;
  state_since: string | null;
  pause_until: string | null;
  returned_at: string | null;
}

async function authToken(): Promise<string> {
  const raw = new URLSearchParams(window.location.search).get("devTelegramId");
  const devTelegramId = raw ? Number(raw) : undefined;
  return (await authenticate(getInitData(), devTelegramId)).token;
}

async function get<T>(path: string): Promise<T> {
  const token = await authToken();
  const response = await fetch(`${API_BASE_URL}/api/v1${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = ((await response.json()) as { detail?: string }).detail ?? detail;
    } catch {
      // keep HTTP detail
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

export function fetchParticipationSummary(): Promise<ParticipationSummary> {
  return get<ParticipationSummary>("/admin/participation/summary");
}

export function fetchParticipationPeople(options: {
  state?: string;
  mode?: string;
  returned30d?: boolean;
} = {}): Promise<ParticipationPerson[]> {
  const query = new URLSearchParams();
  if (options.state) query.set("state", options.state);
  if (options.mode) query.set("mode", options.mode);
  if (options.returned30d) query.set("returned_30d", "true");
  return get<ParticipationPerson[]>(`/admin/participation/people${query.size ? `?${query.toString()}` : ""}`);
}
