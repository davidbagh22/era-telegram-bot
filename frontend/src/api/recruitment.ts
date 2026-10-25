import { ApiError, authenticate } from "./client";
import { getInitData } from "../telegram/webApp";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
let recruitmentToken: string | null = null;

async function token(): Promise<string> {
  if (recruitmentToken) return recruitmentToken;
  const devParam = new URLSearchParams(window.location.search).get("devTelegramId");
  const result = await authenticate(getInitData(), devParam ? Number(devParam) : undefined);
  recruitmentToken = result.token;
  return recruitmentToken;
}

async function request<T>(method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
  const authToken = await token();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    cache: "no-store",
    headers: {
      Authorization: `Bearer ${authToken}`,
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (response.status === 401) {
    recruitmentToken = null;
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = ((await response.json()) as { detail?: string }).detail ?? detail;
    } catch {
      // keep HTTP status text
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

export interface RecruitmentAssignment {
  assignment_id: number;
  user_id: number;
  user_name: string;
  starts_at: string;
  ends_at: string | null;
}

export interface RecruitmentOffice {
  id: number;
  title: string;
  description: string | null;
  responsibilities: string[];
  requirements: string | null;
  expected_result: string | null;
  workload: string | null;
  capacity: number | null;
  occupied: number;
  free_slots: number | null;
  recruitment_mode: "auto" | "manual" | "closed";
  application_enabled: boolean;
  application_deadline: string | null;
  is_public: boolean;
  application_count: number;
  assignments: RecruitmentAssignment[];
}

export interface CandidateFacts {
  participation_status: string;
  participation_label: string;
  current_offices: string[];
  completed_projects: number;
  tasks_completed_on_time: number;
  tasks_completed_total: number;
  on_time_rate: number | null;
  events_attended: number;
  portfolio_items: number;
  points: number;
}

export interface PositionApplicationAdmin {
  id: number;
  office_id: number;
  office_title: string;
  user_id: number;
  user_name: string;
  status: string;
  motivation: string | null;
  relevant_experience: string | null;
  plan: string | null;
  availability: string | null;
  attachment_url: string | null;
  submitted_at: string | null;
  review_note: string | null;
  facts: CandidateFacts;
}

export interface RecruitmentSettingsPayload {
  recruitment_mode: "auto" | "manual" | "closed";
  capacity: number | null;
  application_enabled: boolean | null;
  responsibilities: string[] | null;
  requirements: string | null;
  expected_result: string | null;
  workload: string | null;
  application_deadline: string | null;
  is_public: boolean | null;
}

export function fetchRecruitmentOffices(): Promise<RecruitmentOffice[]> {
  return request("GET", "/api/v1/admin/recruitment/offices");
}

export function updateRecruitmentOffice(
  officeId: number,
  payload: RecruitmentSettingsPayload,
): Promise<RecruitmentOffice> {
  return request("POST", `/api/v1/admin/recruitment/offices/${officeId}`, payload);
}

export function fetchRoleApplications(officeId: number): Promise<PositionApplicationAdmin[]> {
  return request("GET", `/api/v1/admin/recruitment/offices/${officeId}/applications`);
}

export function fetchRoleApplication(applicationId: number): Promise<PositionApplicationAdmin> {
  return request("GET", `/api/v1/admin/recruitment/applications/${applicationId}`);
}

export function decideRoleApplication(
  applicationId: number,
  status: "reviewing" | "needs_info" | "interview" | "reserve" | "approved" | "rejected",
  note = "",
): Promise<PositionApplicationAdmin> {
  return request("POST", `/api/v1/admin/recruitment/applications/${applicationId}/decision`, { status, note });
}

export function appointRoleApplication(
  applicationId: number,
  appointmentType: "regular" | "acting" = "regular",
): Promise<PositionApplicationAdmin> {
  return request("POST", `/api/v1/admin/recruitment/applications/${applicationId}/appoint`, {
    appointment_type: appointmentType,
    ends_at: null,
  });
}
