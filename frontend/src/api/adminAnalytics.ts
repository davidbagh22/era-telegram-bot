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

/**
 * Calculations may keep stable internal English identifiers, but implementation
 * vocabulary must never leak into the Russian product interface.
 */
function russianAnalyticsText(value: string | null): string | null {
  if (value === null) return null;
  return value
    .replace(/Weekly Pulse/gi, "пульс недели")
    .replace(/Meaningful activity/gi, "реальная активность")
    .replace(/meaningful action/gi, "подтверждённая активность")
    .replace(/meaningful/gi, "значимая")
    .replace(/digital engagement/gi, "цифровая активность")
    .replace(/operational activity/gi, "подтверждённое участие")
    .replace(/Active Base/gi, "активная база")
    .replace(/ACTIVE\/LIGHT участники/gi, "участники в активном или лёгком режиме")
    .replace(/PAUSED\/OBSERVER\/EXITED/gi, "пауза, наблюдение и выход")
    .replace(/Check-in['’]ов/gi, "ответов")
    .replace(/Check-ins?/gi, "ответы")
    .replace(/check-ins?/gi, "ответы")
    .replace(/No-show/gi, "не пришли")
    .replace(/Blocker/gi, "препятствие")
    .replace(/Retention/gi, "удержание")
    .replace(/Conversion/gi, "конверсия")
    .replace(/Coverage/gi, "охват")
    .replace(/Response rate/gi, "доля ответов");
}

function localizeEfficiency(snapshot: EfficiencySnapshot): EfficiencySnapshot {
  return {
    ...snapshot,
    label: russianAnalyticsText(snapshot.label) ?? snapshot.label,
    period_label: russianAnalyticsText(snapshot.period_label) ?? snapshot.period_label,
    data_note: russianAnalyticsText(snapshot.data_note) ?? snapshot.data_note,
    top_interest: russianAnalyticsText(snapshot.top_interest),
    metrics: snapshot.metrics.map((metric) => ({
      ...metric,
      label: russianAnalyticsText(metric.label) ?? metric.label,
      display: russianAnalyticsText(metric.display) ?? metric.display,
      note: russianAnalyticsText(metric.note) ?? metric.note,
    })),
    recommendations: snapshot.recommendations.map((item) => ({
      ...item,
      title: russianAnalyticsText(item.title) ?? item.title,
      reason: russianAnalyticsText(item.reason) ?? item.reason,
      action: russianAnalyticsText(item.action) ?? item.action,
    })),
  };
}

function localizeHealth(snapshot: OrganizationHealthSnapshot): OrganizationHealthSnapshot {
  return {
    ...snapshot,
    pulse_label: russianAnalyticsText(snapshot.pulse_label) ?? snapshot.pulse_label,
    period_label: russianAnalyticsText(snapshot.period_label) ?? snapshot.period_label,
    data_note: russianAnalyticsText(snapshot.data_note) ?? snapshot.data_note,
    risks: snapshot.risks.map((risk) => russianAnalyticsText(risk) ?? risk),
    vector_dimensions: snapshot.vector_dimensions.map((dimension) => ({
      ...dimension,
      label: russianAnalyticsText(dimension.label) ?? dimension.label,
    })),
    metrics: snapshot.metrics.map((metric) => ({
      ...metric,
      category: russianAnalyticsText(metric.category) ?? metric.category,
      label: russianAnalyticsText(metric.label) ?? metric.label,
      display: russianAnalyticsText(metric.display) ?? metric.display,
      note: russianAnalyticsText(metric.note) ?? metric.note,
    })),
  };
}

export function fetchAdminAnalyticsDetails(section: AnalyticsDetailSection): Promise<AnalyticsDetails> {
  return adminGet<AnalyticsDetails>(`/api/v1/admin/analytics/details/${section}`);
}

export async function fetchEraEfficiency(): Promise<EfficiencySnapshot> {
  return localizeEfficiency(await adminGet<EfficiencySnapshot>("/api/v1/admin/analytics/weekly"));
}

export async function fetchOrganizationHealth(): Promise<OrganizationHealthSnapshot> {
  return localizeHealth(await adminGet<OrganizationHealthSnapshot>("/api/v1/admin/analytics/health"));
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
