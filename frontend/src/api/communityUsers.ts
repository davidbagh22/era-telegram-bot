import { ApiError, authenticate } from "./client";
import { getInitData } from "../telegram/webApp";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
let tokenPromise: Promise<string> | null = null;

export interface CommunityUser {
  id: number;
  name: string;
  role: string;
  role_label: string;
  participation_status: string;
  participation_label: string;
  departments: string[];
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

export async function fetchCommunityUser(userId: number): Promise<CommunityUser> {
  const sessionToken = await token();
  const response = await fetch(`${API_BASE_URL}/api/v1/users/${userId}`, {
    headers: { Authorization: `Bearer ${sessionToken}` },
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = ((await response.json()) as { detail?: string }).detail ?? detail;
    } catch {
      // Do not log response bodies or personal data.
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as CommunityUser;
}
