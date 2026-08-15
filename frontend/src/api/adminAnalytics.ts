import { ApiError, authenticate } from "./client";

export type AnalyticsDetailSection = "users" | "events" | "projects" | "contacts" | "goals";

export interface AnalyticsDetailItem {
  id: number;
  title: string;
  subtitle: string | null;
  status: string | null;
}

export interface AnalyticsDetails {
  section: AnalyticsDetailSection;
  total: number;
  items: AnalyticsDetailItem[];
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
let tokenPromise: Promise<string> | null = null;

function devTelegramId(): number | undefined {
  const raw = new URLSearchParams(window.location.search).get("devTelegramId");
  if (!raw) return undefined;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : undefined;
}

async function adminToken(): Promise<string> {
  if (!tokenPromise) {
    const initData = window.Telegram?.WebApp?.initData ?? "";
    tokenPromise = authenticate(initData, devTelegramId()).then((result) => result.token);
  }
  try {
    return await tokenPromise;
  } catch (error) {
    tokenPromise = null;
    throw error;
  }
}

export async function fetchAdminAnalyticsDetails(section: AnalyticsDetailSection): Promise<AnalyticsDetails> {
  const token = await adminToken();
  const response = await fetch(`${API_BASE_URL}/api/v1/admin/analytics/details/${section}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      detail = body.detail ?? detail;
    } catch {
      // Keep status text for non-JSON responses.
    }
    if (response.status === 401) tokenPromise = null;
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as AnalyticsDetails;
}
