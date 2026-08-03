import type { ApiErrorBody, MiniAppAuthResponse, MiniAppUserSummary } from "../types/auth";
import type { HomeSnapshot } from "../types/home";

// Empty string means "same origin as the frontend" — set VITE_API_BASE_URL
// when the Mini App is hosted separately from the FastAPI backend.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

// Kept in memory only. Telegram re-supplies fresh initData on every Mini
// App open, so there is no need for a long-lived token in localStorage.
let sessionToken: string | null = null;

export class ApiError extends Error {
  status: number;

  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
  }
}

async function parseErrorDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as ApiErrorBody;
    return body.detail ?? response.statusText;
  } catch {
    return response.statusText;
  }
}

export async function authenticate(initData: string): Promise<MiniAppAuthResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/miniapp/auth`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ initData }),
  });
  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorDetail(response));
  }
  const data = (await response.json()) as MiniAppAuthResponse;
  sessionToken = data.token;
  return data;
}

async function authorizedGet<T>(path: string): Promise<T> {
  if (!sessionToken) {
    throw new ApiError(401, "missing_token");
  }
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { Authorization: `Bearer ${sessionToken}` },
  });
  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorDetail(response));
  }
  return (await response.json()) as T;
}

export function fetchMe(): Promise<MiniAppUserSummary> {
  return authorizedGet<MiniAppUserSummary>("/api/v1/me");
}

export function fetchHome(): Promise<HomeSnapshot> {
  return authorizedGet<HomeSnapshot>("/api/v1/home");
}

export function hasSession(): boolean {
  return sessionToken !== null;
}

export function clearSession(): void {
  sessionToken = null;
}
