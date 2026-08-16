import { authenticate } from "./client";
import { getInitData } from "../telegram/webApp";
import type {
  AdminCareerItem,
  AdminRecommendation,
  CareerDashboard,
  CareerItemPayload,
  CareerPortfolioItem,
  CareerProfileData,
  CareerPurpose,
  OfficialRecommendation,
} from "../types/career";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
let careerToken: string | null = null;

async function token(): Promise<string> {
  if (careerToken) return careerToken;
  const parameter = new URLSearchParams(window.location.search).get("devTelegramId");
  const id = parameter ? Number(parameter) : undefined;
  const auth = await authenticate(getInitData(), id);
  careerToken = auth.token;
  return careerToken;
}

async function request<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const bearer = await token();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${bearer}`,
      ...(init.body && !(init.body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
      ...(init.headers ?? {}),
    },
  });
  if (response.status === 401 && retry) {
    careerToken = null;
    return request<T>(path, init, false);
  }
  if (!response.ok) {
    let detail = response.statusText || "request_failed";
    try {
      const body = (await response.json()) as { detail?: string };
      detail = body.detail ?? detail;
    } catch {
      // Keep status text.
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

async function requestBlob(path: string, retry = true): Promise<Blob> {
  const bearer = await token();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { Authorization: `Bearer ${bearer}` },
  });
  if (response.status === 401 && retry) {
    careerToken = null;
    return requestBlob(path, false);
  }
  if (!response.ok) throw new Error(response.statusText || "download_failed");
  return response.blob();
}

export const fetchCareerDashboard = () => request<CareerDashboard>("/api/v1/career/dashboard");

export const updateCareerProfile = (payload: CareerProfileData) =>
  request<CareerProfileData>("/api/v1/career/profile", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });

export const createCareerItem = (payload: CareerItemPayload) =>
  request<CareerPortfolioItem>("/api/v1/career/items", {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const updateCareerItem = (itemId: number, payload: Partial<CareerItemPayload>) =>
  request<CareerPortfolioItem>(`/api/v1/career/items/${itemId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });

export const deleteCareerItem = (itemId: number) =>
  request<{ deleted: boolean }>(`/api/v1/career/items/${itemId}`, { method: "DELETE" });

export const uploadCareerEvidence = (itemId: number, file: File) => {
  const form = new FormData();
  form.append("upload", file);
  return request<CareerPortfolioItem>(`/api/v1/career/items/${itemId}/file`, {
    method: "POST",
    body: form,
  });
};

export const submitCareerVerification = (itemId: number) =>
  request<CareerPortfolioItem>(`/api/v1/career/items/${itemId}/verification`, { method: "POST" });

export const downloadCareerResume = (purpose: CareerPurpose) =>
  requestBlob(`/api/v1/career/resume.pdf?purpose=${encodeURIComponent(purpose)}`);

export const requestOfficialRecommendation = (purpose: CareerPurpose) =>
  request<OfficialRecommendation>("/api/v1/career/recommendation/request", {
    method: "POST",
    body: JSON.stringify({ purpose }),
  });

export const downloadOfficialRecommendation = (requestId: number) =>
  requestBlob(`/api/v1/career/recommendation/${requestId}.pdf`);

export const fetchAdminCareerItems = () => request<AdminCareerItem[]>("/api/v1/admin/career/pending");
export const fetchAdminRecommendations = () => request<AdminRecommendation[]>("/api/v1/admin/career/recommendations/pending");

export const reviewAdminCareerItem = (itemId: number, decision: "approve" | "reject", comment?: string) =>
  request<CareerPortfolioItem>(`/api/v1/admin/career/items/${itemId}/review`, {
    method: "POST",
    body: JSON.stringify({ decision, comment }),
  });

export const reviewAdminRecommendation = (
  requestId: number,
  decision: "approve" | "reject",
  finalText?: string,
  comment?: string,
) =>
  request<OfficialRecommendation>(`/api/v1/admin/career/recommendations/${requestId}/review`, {
    method: "POST",
    body: JSON.stringify({ decision, final_text: finalText, comment }),
  });

export const downloadAdminCareerEvidence = (itemId: number) =>
  requestBlob(`/api/v1/admin/career/items/${itemId}/file`);
