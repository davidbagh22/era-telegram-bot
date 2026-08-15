import { ApiError, authenticate } from "./client";

export interface AdminProjectDetail {
  id: number;
  title: string;
  short_description: string;
  status: string;
  author_id: number;
  author_name: string;
  submitted_at: string | null;
  admin_comment: string | null;
  form_data: Record<string, unknown>;
  generated_document: string | null;
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
let tokenPromise: Promise<string> | null = null;

function devTelegramId(): number | undefined {
  const raw = new URLSearchParams(window.location.search).get("devTelegramId");
  if (!raw) return undefined;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : undefined;
}

async function token(): Promise<string> {
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

export async function fetchAdminProjectDetail(projectId: number): Promise<AdminProjectDetail> {
  const authToken = await token();
  const response = await fetch(`${API_BASE_URL}/api/v1/admin/projects/${projectId}/detail`, {
    headers: { Authorization: `Bearer ${authToken}` },
  });
  if (!response.ok) {
    if (response.status === 401) tokenPromise = null;
    throw new ApiError(response.status, response.statusText);
  }
  return (await response.json()) as AdminProjectDetail;
}
