import { ApiError, authenticate } from "./client";
import { getInitData } from "../telegram/webApp";
import type { TaskItem } from "../types/activity";

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
    tokenPromise = authenticate(getInitData(), devTelegramId())
      .then((result) => result.token)
      .catch((error) => {
        tokenPromise = null;
        throw error;
      });
  }
  return tokenPromise;
}

export async function fetchTaskDetail(taskId: number): Promise<TaskItem> {
  const sessionToken = await token();
  const response = await fetch(`${API_BASE_URL}/api/v1/tasks/${taskId}`, {
    headers: { Authorization: `Bearer ${sessionToken}` },
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = ((await response.json()) as { detail?: string }).detail ?? detail;
    } catch {
      // Keep status text. No response-body logging.
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as TaskItem;
}
