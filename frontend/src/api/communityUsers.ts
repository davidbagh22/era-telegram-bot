import { ApiError, authenticate } from "./client";
import { getInitData } from "../telegram/webApp";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
let tokenPromise: Promise<string> | null = null;

export interface CommunityUser {
  id: number;
  name: string;
  username: string | null;
  telegram_url: string | null;
  role: string;
  role_label: string;
  participation_status: string;
  participation_label: string;
  departments: string[];
  directions: string[];
  events_attended: number;
  project_memberships: number;
  tasks_completed: number;
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

async function get<T>(path: string): Promise<T> {
  const sessionToken = await token();
  const response = await fetch(`${API_BASE_URL}${path}`, { headers: { Authorization: `Bearer ${sessionToken}` } });
  if (!response.ok) {
    let detail = response.statusText;
    try { detail = ((await response.json()) as { detail?: string }).detail ?? detail; } catch { /* no PII logging */ }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

export function fetchCommunityUsers(q = ""): Promise<CommunityUser[]> {
  const params = new URLSearchParams();
  if (q.trim()) params.set("q", q.trim());
  return get<CommunityUser[]>(`/api/v1/users${params.size ? `?${params.toString()}` : ""}`);
}

export function fetchCommunityUser(userId: number): Promise<CommunityUser> {
  return get<CommunityUser>(`/api/v1/users/${userId}`);
}
