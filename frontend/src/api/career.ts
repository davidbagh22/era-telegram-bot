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

export interface ResumeAttachmentFailure {
  key: string;
  kind: string;
  title: string;
  number: string | null;
  reason: string;
}

export class ResumeAttachmentError extends Error {
  failed: ResumeAttachmentFailure[];
  userMessage: string;
  constructor(message: string, failed: ResumeAttachmentFailure[]) {
    super("resume_attachment_failed");
    this.name = "ResumeAttachmentError";
    this.failed = failed;
    this.userMessage = message;
  }
}

async function responseError(response: Response, fallback: string): Promise<Error> {
  let detail: unknown = response.statusText || fallback;
  try {
    detail = ((await response.json()) as { detail?: unknown }).detail ?? detail;
  } catch {
    // Keep status text.
  }
  if (detail && typeof detail === "object") {
    const body = detail as { code?: string; message?: string; failed?: ResumeAttachmentFailure[] };
    if (body.code === "resume_attachment_failed" && Array.isArray(body.failed)) {
      return new ResumeAttachmentError(body.message ?? "Не удалось приложить документ", body.failed);
    }
    return new Error(body.code ?? fallback);
  }
  return new Error(String(detail));
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
  if (!response.ok) throw await responseError(response, "request_failed");
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
  if (!response.ok) throw await responseError(response, "download_failed");
  return response.blob();
}

async function requestBlobWithHeaders(path: string, retry = true): Promise<{ blob: Blob; headers: Headers }> {
  const bearer = await token();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { Authorization: `Bearer ${bearer}` },
  });
  if (response.status === 401 && retry) {
    careerToken = null;
    return requestBlobWithHeaders(path, false);
  }
  if (!response.ok) throw await responseError(response, "download_failed");
  return { blob: await response.blob(), headers: response.headers };
}

export const fetchCareerDashboard = () => request<CareerDashboard>("/api/v1/career/dashboard");

export interface IssuedCertificate { id: number; number: string; title: string; status: string; issued_at: string }
export const fetchCertificates = () => request<IssuedCertificate[]>("/api/v1/career/certificates");
export const downloadCertificate = (id: number) => requestBlob(`/api/v1/career/certificates/${id}.pdf`);

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

export interface ResumeAttachmentCandidate {
  key: string;
  kind: "certificate" | "document";
  title: string;
  number: string | null;
  item_id: number | null;
  verified: boolean;
  visible: boolean;
  selected: boolean;
  reason: string | null;
}

export interface ResumeAttachmentsPreview {
  items: ResumeAttachmentCandidate[];
  selected_count: number;
  default_attach: boolean;
}

export interface ResumeManifestEntry {
  key: string;
  kind: string;
  title: string;
  number: string | null;
  pages?: number;
}

export interface ResumeManifest {
  base_pages: number;
  total_pages: number;
  attached: ResumeManifestEntry[];
  skipped: ResumeManifestEntry[];
}

export interface ResumeExportOptions {
  attach?: boolean;
  skip?: string[];
}

export const fetchResumeAttachments = () =>
  request<ResumeAttachmentsPreview>("/api/v1/career/resume/attachments");

function decodeManifest(value: string | null): ResumeManifest | null {
  if (!value) return null;
  try {
    const base64 = value.replace(/-/g, "+").replace(/_/g, "/");
    const bytes = Uint8Array.from(atob(base64), (char) => char.charCodeAt(0));
    return JSON.parse(new TextDecoder().decode(bytes)) as ResumeManifest;
  } catch {
    return null;
  }
}

export const downloadCareerResume = async (
  purpose: CareerPurpose,
  mode: import("../types/career").CareerResumeMode = "portfolio",
  options: ResumeExportOptions = {},
): Promise<{ blob: Blob; manifest: ResumeManifest | null }> => {
  const query = new URLSearchParams({ purpose, mode });
  if (options.attach) query.set("attach_certificates", "true");
  if (options.skip?.length) query.set("skip", options.skip.join(","));
  const { blob, headers } = await requestBlobWithHeaders(`/api/v1/career/resume.pdf?${query.toString()}`);
  return { blob, manifest: decodeManifest(headers.get("X-ERA-Resume-Manifest")) };
};

export const sendCareerResume = (
  purpose: CareerPurpose,
  mode: import("../types/career").CareerResumeMode = "portfolio",
  options: ResumeExportOptions = {},
) =>
  request<{ sent: boolean; manifest?: ResumeManifest }>("/api/v1/career/resume/send", {
    method: "POST",
    body: JSON.stringify({ purpose, mode, attach_certificates: Boolean(options.attach), skip: options.skip ?? [] }),
  });

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
