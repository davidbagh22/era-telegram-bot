import { ApiError, authenticate } from "./client";

export type AnalyticsDetailSection = "users" | "events" | "projects" | "contacts" | "goals";
export type ExecutiveReportPeriod = "30d" | "3m" | "6m" | "1y" | "custom";

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

export interface EfficiencyMetric {
  key: string;
  label: string;
  value: number;
  display: string;
  score: number | null;
  note: string;
}

export interface EfficiencyRecommendation {
  priority: "high" | "medium" | "opportunity" | string;
  title: string;
  reason: string;
  action: string;
}

export interface EfficiencySnapshot {
  score: number;
  label: string;
  period_label: string;
  metrics: EfficiencyMetric[];
  recommendations: EfficiencyRecommendation[];
  top_interest: string | null;
  top_interest_count: number;
  data_note: string;
}

export interface HealthMetric {
  key: string;
  category: string;
  label: string;
  value: number;
  display: string;
  note: string;
  score: number | null;
}

export interface OrganizationVectorDimension {
  key: string;
  label: string;
  value: number;
  delta: number | null;
}

export interface OrganizationHealthSnapshot {
  pulse: number | null;
  pulse_label: string;
  pulse_coverage: number;
  pulse_sample_size: number;
  pulse_suppressed: boolean;
  vector_dimensions: OrganizationVectorDimension[];
  metrics: HealthMetric[];
  risks: string[];
  period_label: string;
  data_note: string;
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

async function adminGet<T>(path: string): Promise<T> {
  const token = await adminToken();
  const response = await fetch(`${API_BASE_URL}${path}`, {
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
  return (await response.json()) as T;
}

async function adminBlob(path: string): Promise<Blob> {
  const token = await adminToken();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    if (response.status === 401) tokenPromise = null;
    throw new ApiError(response.status, response.statusText);
  }
  return response.blob();
}

export function fetchAdminAnalyticsDetails(section: AnalyticsDetailSection): Promise<AnalyticsDetails> {
  return adminGet<AnalyticsDetails>(`/api/v1/admin/analytics/details/${section}`);
}

export function fetchEraEfficiency(): Promise<EfficiencySnapshot> {
  return adminGet<EfficiencySnapshot>("/api/v1/admin/analytics/weekly");
}

export function fetchOrganizationHealth(): Promise<OrganizationHealthSnapshot> {
  return adminGet<OrganizationHealthSnapshot>("/api/v1/admin/analytics/health");
}

export function downloadAnalyticsSectionTable(section: AnalyticsDetailSection): Promise<Blob> {
  return adminBlob(`/api/v1/admin/analytics/details/${section}/export.xlsx`);
}

export function downloadOrganizationHealthReport(): Promise<Blob> {
  return adminBlob("/api/v1/admin/analytics/health-report.xlsx");
}

export function downloadFullAnalyticsReport(
  period: ExecutiveReportPeriod = "30d",
  startDate?: string,
  endDate?: string,
): Promise<Blob> {
  const params = new URLSearchParams({ period });
  if (period === "custom" && startDate && endDate) {
    params.set("start_date", startDate);
    params.set("end_date", endDate);
  }
  return adminBlob(`/api/v1/admin/analytics/executive-report.xlsx?${params.toString()}`);
}
