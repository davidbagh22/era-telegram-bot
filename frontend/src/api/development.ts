import { authenticate } from "./client";
import { getInitData } from "../telegram/webApp";
import type {
  AdminDevelopmentProfile,
  AssessmentCard,
  AssessmentResult,
  AssessmentSession,
  DevelopmentAnalytics,
  DevelopmentGoal,
  DevelopmentHome,
  DevelopmentPrivacy,
  PersonalInsightItem,
  RememberedNote,
  VectorCheckin,
} from "../types/development";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
let developmentToken: string | null = null;

async function token(): Promise<string> {
  if (developmentToken) return developmentToken;
  const parameter = new URLSearchParams(window.location.search).get("devTelegramId");
  const id = parameter ? Number(parameter) : undefined;
  const auth = await authenticate(getInitData(), id);
  developmentToken = auth.token;
  return developmentToken;
}

async function request<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const bearer = await token();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${bearer}`,
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...(init.headers ?? {}),
    },
  });
  if (response.status === 401 && retry) {
    developmentToken = null;
    return request<T>(path, init, false);
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      detail = body.detail ?? detail;
    } catch {
      // Keep the HTTP status text when the server did not return JSON.
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export const fetchDevelopmentHome = () => request<DevelopmentHome>("/api/v1/development/home");
export const acceptDevelopmentConsent = (accepted: boolean) =>
  request<{ accepted: boolean; version: string }>("/api/v1/development/consent", {
    method: "POST",
    body: JSON.stringify({ accepted }),
  });

export const fetchAssessments = () => request<AssessmentCard[]>("/api/v1/development/assessments");
export const fetchAssessment = (code: string) =>
  request<AssessmentCard>(`/api/v1/development/assessments/${encodeURIComponent(code)}`);
export const startAssessment = (code: string) =>
  request<AssessmentSession>(`/api/v1/development/assessments/${encodeURIComponent(code)}/start`, {
    method: "POST",
  });
export const fetchAssessmentSession = (sessionId: number) =>
  request<AssessmentSession>(`/api/v1/development/assessment-sessions/${sessionId}`);
export const saveAssessmentAnswer = (sessionId: number, questionCode: string, value: number) =>
  request<AssessmentSession>(`/api/v1/development/assessment-sessions/${sessionId}/answers`, {
    method: "PATCH",
    body: JSON.stringify({ question_code: questionCode, value }),
  });
export const completeAssessment = (sessionId: number) =>
  request<AssessmentResult>(`/api/v1/development/assessment-sessions/${sessionId}/complete`, {
    method: "POST",
  });
export const fetchLatestAssessmentResult = (code: string) =>
  request<AssessmentResult>(
    `/api/v1/development/assessments/${encodeURIComponent(code)}/result/latest`,
  );

export const fetchCurrentCheckin = () =>
  request<
    VectorCheckin & {
      questions: DevelopmentHome["questions"];
      answer_options: DevelopmentHome["answer_options"];
      context_options: string[];
      development_wants: string[];
    }
  >("/api/v1/development/checkin/current");
export const saveCheckinAnswer = (
  answers: Record<string, number>,
  factors?: string[],
  developmentWants?: string[],
) =>
  request<VectorCheckin>("/api/v1/development/checkin/current/answers", {
    method: "PATCH",
    body: JSON.stringify({
      answers,
      ...(factors !== undefined ? { factors } : {}),
      ...(developmentWants !== undefined ? { development_wants: developmentWants } : {}),
    }),
  });
export const completeCheckin = () =>
  request<VectorCheckin>("/api/v1/development/checkin/current/complete", { method: "POST" });
export const fetchDevelopmentHistory = () =>
  request<VectorCheckin[]>("/api/v1/development/history");
export const createDevelopmentGoal = (payload: {
  title: string;
  experiment?: string | null;
  semantic_tag?: string | null;
  is_custom?: boolean;
}) =>
  request<DevelopmentGoal>("/api/v1/development/goals", {
    method: "POST",
    body: JSON.stringify(payload),
  });
export const reviewDevelopmentGoal = (
  goalId: number,
  result: string,
  obstacle?: string | null,
) =>
  request<{ goal_id: number; result: string; obstacle: string | null }>(
    `/api/v1/development/goals/${goalId}/review`,
    { method: "POST", body: JSON.stringify({ result, obstacle: obstacle ?? null }) },
  );
export const savePersonalNote = (text: string, checkinId?: number | null) =>
  request<{ id: number; created_at: string }>("/api/v1/development/notes", {
    method: "POST",
    body: JSON.stringify({ text, checkin_id: checkinId ?? null }),
  });
export const fetchRememberedNotes = () =>
  request<RememberedNote[]>("/api/v1/development/notes/remember");
export const fetchPersonalInsights = () =>
  request<PersonalInsightItem[]>("/api/v1/development/insights");
export const submitInsightFeedback = (insightId: number, accepted: boolean) =>
  request<{ id: number; accepted: boolean; hidden: boolean }>(
    `/api/v1/development/insights/${insightId}/feedback`,
    { method: "POST", body: JSON.stringify({ accepted }) },
  );
export const fetchDevelopmentPrivacy = () =>
  request<DevelopmentPrivacy>("/api/v1/development/privacy");
export const updateDevelopmentPrivacy = (payload: {
  summary: boolean;
  interests: boolean;
  goals: boolean;
}) =>
  request<typeof payload>("/api/v1/development/privacy", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });

export const fetchAdminDevelopmentAnalytics = (periodDays = 30) =>
  request<DevelopmentAnalytics>(`/api/v1/admin/development/analytics?period_days=${periodDays}`);

export const fetchAdminDevelopmentProfile = (userId: number) =>
  request<AdminDevelopmentProfile>(`/api/v1/admin/development/participants/${userId}`);
