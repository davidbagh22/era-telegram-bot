import { ApiError, authenticate } from "./client";
import { getInitData } from "../telegram/webApp";
import type { AdminMetricDrilldown, AdminMetricKey } from "../types/adminMetrics";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

async function token(): Promise<string> {
  const raw = new URLSearchParams(window.location.search).get("devTelegramId");
  const devTelegramId = raw ? Number(raw) : undefined;
  const auth = await authenticate(getInitData(), devTelegramId);
  return auth.token;
}

async function detail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: string };
    return body.detail ?? response.statusText;
  } catch {
    return response.statusText;
  }
}

export async function fetchAdminMetric(metric: AdminMetricKey): Promise<AdminMetricDrilldown> {
  const bearer = await token();
  const response = await fetch(`${API_BASE_URL}/api/v1/admin/analytics/drilldown/${metric}`, {
    headers: { Authorization: `Bearer ${bearer}` },
  });
  if (!response.ok) throw new ApiError(response.status, await detail(response));
  return (await response.json()) as AdminMetricDrilldown;
}

export async function downloadAdminMetric(metric: AdminMetricKey): Promise<void> {
  const bearer = await token();
  const response = await fetch(`${API_BASE_URL}/api/v1/admin/analytics/drilldown/export/${metric}.xlsx`, {
    headers: { Authorization: `Bearer ${bearer}` },
  });
  if (!response.ok) throw new ApiError(response.status, await detail(response));
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `era-${metric}.xlsx`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
