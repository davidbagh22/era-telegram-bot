import { ApiError, authenticate } from "./client";
import { getInitData } from "../telegram/webApp";
import type {
  LeadershipFeedback,
  LeadershipWeeklyReport,
  LeadershipWeeklySubmit,
} from "../types/leadership";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

async function token(): Promise<string> {
  const devTelegramIdParam = new URLSearchParams(window.location.search).get("devTelegramId");
  const devTelegramId = devTelegramIdParam ? Number(devTelegramIdParam) : undefined;
  const result = await authenticate(getInitData(), devTelegramId);
  return result.token;
}

async function parseDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: string };
    return body.detail ?? response.statusText;
  } catch {
    return response.statusText;
  }
}

async function request<T>(path: string, method: "GET" | "POST" = "GET", body?: unknown): Promise<T> {
  const bearer = await token();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${bearer}`,
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    throw new ApiError(response.status, await parseDetail(response));
  }
  return (await response.json()) as T;
}

export function fetchCurrentLeadershipPulse(): Promise<LeadershipWeeklyReport> {
  return request<LeadershipWeeklyReport>("/api/v1/leadership/reports/current");
}

export function submitLeadershipPulse(payload: LeadershipWeeklySubmit): Promise<LeadershipWeeklyReport> {
  return request<LeadershipWeeklyReport>("/api/v1/leadership/reports", "POST", payload);
}

export function fetchLeadershipFeedback(reportId: number): Promise<LeadershipFeedback[]> {
  return request<LeadershipFeedback[]>(`/api/v1/leadership/reports/${reportId}/feedback`);
}
