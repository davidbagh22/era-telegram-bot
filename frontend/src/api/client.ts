import type {
  CalendarItem,
  EventItem,
  EventScope,
  HistoryEntry,
  TaskItem,
  TaskScope,
} from "../types/activity";
import type { ApiErrorBody, MiniAppAuthResponse, MiniAppUserSummary } from "../types/auth";
import type { HomeSnapshot } from "../types/home";
import type { Opportunity, OpportunityScope } from "../types/opportunity";
import type {
  ProjectDetail,
  ProjectEvent,
  ProjectMember,
  ProjectMilestone,
  ProjectQuestion,
  ProjectRole,
  ProjectScope,
  ProjectSummary,
  ProjectTask,
  ProjectWorkspace,
  TeamMessageResult,
} from "../types/project";

// Empty string means "same origin as the frontend" — set VITE_API_BASE_URL
// when the Mini App is hosted separately from the FastAPI backend.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

// Kept in memory only. Telegram re-supplies fresh initData on every Mini
// App open, so there is no need for a long-lived token in localStorage.
let sessionToken: string | null = null;

export class ApiError extends Error {
  status: number;

  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
  }
}

async function parseErrorDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as ApiErrorBody;
    return body.detail ?? response.statusText;
  } catch {
    return response.statusText;
  }
}

export async function authenticate(initData: string): Promise<MiniAppAuthResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/miniapp/auth`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ initData }),
  });
  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorDetail(response));
  }
  const data = (await response.json()) as MiniAppAuthResponse;
  sessionToken = data.token;
  return data;
}

async function authorizedGet<T>(path: string): Promise<T> {
  if (!sessionToken) {
    throw new ApiError(401, "missing_token");
  }
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { Authorization: `Bearer ${sessionToken}` },
  });
  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorDetail(response));
  }
  return (await response.json()) as T;
}

async function authorizedSend<T>(
  method: "POST" | "PATCH",
  path: string,
  body?: unknown,
): Promise<T> {
  if (!sessionToken) {
    throw new ApiError(401, "missing_token");
  }
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${sessionToken}`,
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorDetail(response));
  }
  return (await response.json()) as T;
}

function authorizedPost<T>(path: string, body?: unknown): Promise<T> {
  return authorizedSend<T>("POST", path, body);
}

function authorizedPatch<T>(path: string, body: unknown): Promise<T> {
  return authorizedSend<T>("PATCH", path, body);
}

export function fetchMe(): Promise<MiniAppUserSummary> {
  return authorizedGet<MiniAppUserSummary>("/api/v1/me");
}

export function fetchHome(): Promise<HomeSnapshot> {
  return authorizedGet<HomeSnapshot>("/api/v1/home");
}

export function fetchEvents(scope: EventScope): Promise<EventItem[]> {
  return authorizedGet<EventItem[]>(`/api/v1/events?scope=${scope}`);
}

export function registerForEvent(eventId: number): Promise<EventItem> {
  return authorizedPost<EventItem>(`/api/v1/events/${eventId}/register`);
}

export function cancelEventRegistration(eventId: number): Promise<EventItem> {
  return authorizedPost<EventItem>(`/api/v1/events/${eventId}/cancel`);
}

export function fetchTasks(scope: TaskScope): Promise<TaskItem[]> {
  return authorizedGet<TaskItem[]>(`/api/v1/tasks?scope=${scope}`);
}

export function claimTask(taskId: number): Promise<TaskItem> {
  return authorizedPost<TaskItem>(`/api/v1/tasks/${taskId}/claim`);
}

export function fetchCalendar(): Promise<CalendarItem[]> {
  return authorizedGet<CalendarItem[]>("/api/v1/activity/calendar");
}

export function fetchHistory(): Promise<HistoryEntry[]> {
  return authorizedGet<HistoryEntry[]>("/api/v1/activity/history");
}

export function fetchProjects(scope: ProjectScope): Promise<ProjectSummary[]> {
  return authorizedGet<ProjectSummary[]>(`/api/v1/projects?scope=${scope}`);
}

export function fetchProjectQuestions(): Promise<ProjectQuestion[]> {
  return authorizedGet<ProjectQuestion[]>("/api/v1/projects/questions");
}

export function fetchProject(projectId: number): Promise<ProjectDetail> {
  return authorizedGet<ProjectDetail>(`/api/v1/projects/${projectId}`);
}

export function createProject(idea: string): Promise<ProjectDetail> {
  return authorizedPost<ProjectDetail>("/api/v1/projects", { idea });
}

export function updateProject(
  projectId: number,
  answers: Record<string, string>,
): Promise<ProjectDetail> {
  return authorizedPatch<ProjectDetail>(`/api/v1/projects/${projectId}`, { answers });
}

export function submitProject(projectId: number): Promise<ProjectDetail> {
  return authorizedPost<ProjectDetail>(`/api/v1/projects/${projectId}/submit`);
}

export function cancelProject(projectId: number): Promise<ProjectDetail> {
  return authorizedPost<ProjectDetail>(`/api/v1/projects/${projectId}/cancel`);
}

export function fetchProjectWorkspace(projectId: number): Promise<ProjectWorkspace> {
  return authorizedGet<ProjectWorkspace>(`/api/v1/projects/${projectId}/workspace`);
}

export function createProjectRole(
  projectId: number,
  payload: { title: string; description?: string; requirements?: string; capacity?: number },
): Promise<ProjectRole> {
  return authorizedPost<ProjectRole>(`/api/v1/projects/${projectId}/workspace/roles`, payload);
}

export function setProjectRoleStatus(
  projectId: number,
  roleId: number,
  status: "open" | "closed",
): Promise<ProjectRole> {
  return authorizedPatch<ProjectRole>(`/api/v1/projects/${projectId}/workspace/roles/${roleId}`, {
    status,
  });
}

export function applyToProjectRole(
  projectId: number,
  payload: { role_id?: number; text?: string },
): Promise<ProjectMember> {
  return authorizedPost<ProjectMember>(
    `/api/v1/projects/${projectId}/workspace/applications`,
    payload,
  );
}

export function approveProjectApplication(
  projectId: number,
  memberId: number,
): Promise<ProjectMember> {
  return authorizedPost<ProjectMember>(
    `/api/v1/projects/${projectId}/workspace/applications/${memberId}/approve`,
  );
}

export function rejectProjectApplication(
  projectId: number,
  memberId: number,
): Promise<ProjectMember> {
  return authorizedPost<ProjectMember>(
    `/api/v1/projects/${projectId}/workspace/applications/${memberId}/reject`,
  );
}

export function addProjectMember(
  projectId: number,
  payload: { user_id: number; role_id?: number },
): Promise<ProjectMember> {
  return authorizedPost<ProjectMember>(`/api/v1/projects/${projectId}/workspace/members`, payload);
}

export function changeProjectMemberRole(
  projectId: number,
  memberId: number,
  roleId?: number,
): Promise<ProjectMember> {
  return authorizedPatch<ProjectMember>(
    `/api/v1/projects/${projectId}/workspace/members/${memberId}`,
    { role_id: roleId },
  );
}

export function confirmProjectContribution(
  projectId: number,
  memberId: number,
  payload: { summary: string; result?: string },
): Promise<ProjectMember> {
  return authorizedPost<ProjectMember>(
    `/api/v1/projects/${projectId}/workspace/members/${memberId}/contribution/confirm`,
    payload,
  );
}

export function createProjectMilestone(
  projectId: number,
  payload: {
    title: string;
    description?: string;
    deadline?: string;
    responsible_id?: number;
  },
): Promise<ProjectMilestone> {
  return authorizedPost<ProjectMilestone>(
    `/api/v1/projects/${projectId}/workspace/milestones`,
    payload,
  );
}

export function setProjectMilestoneStatus(
  projectId: number,
  milestoneId: number,
  status: "pending" | "in_progress" | "blocked" | "completed",
): Promise<ProjectMilestone> {
  return authorizedPatch<ProjectMilestone>(
    `/api/v1/projects/${projectId}/workspace/milestones/${milestoneId}`,
    { status },
  );
}

export function createProjectTask(
  projectId: number,
  payload: {
    title: string;
    description: string;
    deadline: string;
    assignee_id?: number;
    points?: number;
  },
): Promise<ProjectTask> {
  return authorizedPost<ProjectTask>(`/api/v1/projects/${projectId}/workspace/tasks`, payload);
}

export function assignProjectTask(
  projectId: number,
  taskId: number,
  assigneeId?: number,
): Promise<ProjectTask> {
  return authorizedPost<ProjectTask>(
    `/api/v1/projects/${projectId}/workspace/tasks/${taskId}/assign`,
    { assignee_id: assigneeId },
  );
}

export function linkProjectEvent(projectId: number, eventId: number): Promise<ProjectEvent> {
  return authorizedPost<ProjectEvent>(
    `/api/v1/projects/${projectId}/workspace/events/${eventId}/link`,
  );
}

export function messageProjectTeam(projectId: number, text: string): Promise<TeamMessageResult> {
  return authorizedPost<TeamMessageResult>(`/api/v1/projects/${projectId}/workspace/team/message`, {
    text,
  });
}

export function fetchOpportunities(scope: OpportunityScope): Promise<Opportunity[]> {
  return authorizedGet<Opportunity[]>(`/api/v1/opportunities?scope=${scope}`);
}

export function fetchOpportunity(offerId: number): Promise<Opportunity> {
  return authorizedGet<Opportunity>(`/api/v1/opportunities/${offerId}`);
}

export function applyToOpportunity(offerId: number): Promise<Opportunity> {
  return authorizedPost<Opportunity>(`/api/v1/opportunities/${offerId}/apply`);
}

export function saveOpportunity(offerId: number): Promise<Opportunity> {
  return authorizedPost<Opportunity>(`/api/v1/opportunities/${offerId}/save`);
}

export function unsaveOpportunity(offerId: number): Promise<Opportunity> {
  return authorizedPost<Opportunity>(`/api/v1/opportunities/${offerId}/unsave`);
}

export function hasSession(): boolean {
  return sessionToken !== null;
}

export function clearSession(): void {
  sessionToken = null;
}
