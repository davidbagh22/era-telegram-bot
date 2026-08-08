import type {
  CalendarItem,
  EventItem,
  EventScope,
  HistoryEntry,
  TaskItem,
  TaskScope,
} from "../types/activity";
import type { ApiErrorBody, MiniAppAuthResponse, MiniAppUserSummary } from "../types/auth";
import type {
  BadgeItem,
  DashboardData,
  EventDecisionAction,
  EventForModeration,
  EventParticipant,
  OfferAdmin,
  OfferApplicationAction,
  OfferApplicationForReview,
  OperationalEvent,
  Partner,
  PendingApplication,
  ProjectDecisionAction,
  ProjectForModeration,
  TaskReviewAction,
  TaskSubmissionForReview,
  TeamPost,
  UserDetail,
  UserListResult,
} from "../types/admin";
import type { HomeSnapshot } from "../types/home";
import type { LeaderOpenTask, LeaderOverview, OpenTaskCreatePayload } from "../types/leader";
import type { Opportunity, OpportunityScope } from "../types/opportunity";
import type { Profile } from "../types/profile";
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

// Backend error `detail` values are machine codes (see app/api/v1/*.py),
// not sentences — this is the one place that turns them into Russian text
// for the handful of mutating actions (approve/reject/register/claim/apply)
// that can fail for a reason the user should actually see (someone else
// already decided it, no slots left, etc.), instead of failing silently.
// Not exhaustive by design: an unmapped code still shows a readable
// message with the raw code attached, rather than nothing at all.
const ACTION_ERROR_MESSAGES: Record<string, string> = {
  user_not_found: "Пользователь не найден — возможно, запись уже изменилась.",
  already_approved: "Заявка уже была одобрена ранее.",
  already_rejected: "Заявка уже была отклонена ранее.",
  comment_required: "Добавьте комментарий перед отправкой решения.",
  admin_access_required: "Недостаточно прав администратора для этого действия.",
  reviewer_access_required: "Недостаточно прав для проверки проектов.",
  event_reviewer_access_required: "Недостаточно прав для проверки мероприятий.",
  task_reviewer_access_required: "Недостаточно прав для проверки заданий.",
  offer_reviewer_access_required: "Недостаточно прав для проверки заявок на возможности.",
  leader_access_required: "Недостаточно прав лидера для этого действия.",
  invalid_action: "Такое решение недоступно для текущего статуса — обновите список.",
  project_not_found: "Проект не найден — возможно, его уже удалили.",
  event_not_found: "Мероприятие не найдено — возможно, его уже удалили.",
  submission_not_found: "Результат задания не найден — возможно, его уже проверили.",
  application_not_found: "Заявка не найдена — возможно, её уже обработали.",
  opportunity_not_found: "Возможность не найдена — возможно, её уже сняли с публикации.",
  offer_unavailable: "Эта возможность больше недоступна.",
  already_applied: "Вы уже подавали заявку на эту возможность.",
  insufficient_points: "Недостаточно баллов для этой заявки.",
  no_slots: "Свободных мест больше нет.",
  registration_not_found: "Регистрация не найдена — возможно, вы уже отменили её.",
  cannot_change_plans: "Отменить регистрацию уже нельзя — до мероприятия слишком мало времени.",
  closed: "Регистрация на это мероприятие закрыта.",
  already: "Вы уже зарегистрированы на это мероприятие.",
  full: "Свободных мест на это мероприятие больше нет.",
  assignee_not_found: "Участник не найден.",
  not_found: "Не найдено — возможно, запись уже изменилась.",
  task_closed: "Задача уже закрыта.",
  task_full: "Набор помощников на эту задачу уже завершён.",
  already_joined: "Вы уже откликнулись на эту задачу.",
  task_not_found: "Задача не найдена — возможно, её уже удалили.",
  rate_limited: "Слишком много попыток подряд — подождите немного и попробуйте снова.",
};

export function describeActionError(error: unknown): string {
  if (error instanceof ApiError) {
    return (
      ACTION_ERROR_MESSAGES[error.message] ??
      `Не удалось выполнить действие (код: ${error.message}).`
    );
  }
  return "Не удалось выполнить действие. Проверьте соединение и попробуйте ещё раз.";
}

async function parseErrorDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as ApiErrorBody;
    return body.detail ?? response.statusText;
  } catch {
    return response.statusText;
  }
}

export async function authenticate(
  initData: string,
  devTelegramId?: number,
): Promise<MiniAppAuthResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/miniapp/auth`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    // devTelegramId is a no-op unless the backend has DEV_AUTH_ENABLED set,
    // which app/config.py's assert_safe_for_deployment() refuses to allow
    // on a Render deployment (see PR13) — safe to always include when
    // present in the URL, real Telegram clients never set it.
    body: JSON.stringify({ initData, devTelegramId }),
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

export function fetchAdminDashboard(): Promise<DashboardData> {
  return authorizedGet<DashboardData>("/api/v1/admin/dashboard");
}

export function fetchAdminApplications(): Promise<PendingApplication[]> {
  return authorizedGet<PendingApplication[]>("/api/v1/admin/applications");
}

export function approveApplication(userId: number): Promise<PendingApplication> {
  return authorizedPost<PendingApplication>(`/api/v1/admin/applications/${userId}/approve`);
}

export function rejectApplication(userId: number, comment: string): Promise<PendingApplication> {
  return authorizedPost<PendingApplication>(`/api/v1/admin/applications/${userId}/reject`, {
    comment,
  });
}

export function requestApplicationInfo(
  userId: number,
  comment: string,
): Promise<PendingApplication> {
  return authorizedPost<PendingApplication>(
    `/api/v1/admin/applications/${userId}/request-info`,
    { comment },
  );
}

export function fetchAdminProjects(): Promise<ProjectForModeration[]> {
  return authorizedGet<ProjectForModeration[]>("/api/v1/admin/projects");
}

export function decideProject(
  projectId: number,
  action: ProjectDecisionAction,
  comment: string,
): Promise<ProjectForModeration> {
  return authorizedPost<ProjectForModeration>(`/api/v1/admin/projects/${projectId}/decide`, {
    action,
    comment,
  });
}

export function fetchAdminEvents(): Promise<EventForModeration[]> {
  return authorizedGet<EventForModeration[]>("/api/v1/admin/events");
}

export function decideEvent(
  eventId: number,
  action: EventDecisionAction,
  comment: string,
): Promise<EventForModeration> {
  return authorizedPost<EventForModeration>(`/api/v1/admin/events/${eventId}/decide`, {
    action,
    comment,
  });
}

export function fetchAdminTaskSubmissions(): Promise<TaskSubmissionForReview[]> {
  return authorizedGet<TaskSubmissionForReview[]>("/api/v1/admin/task-submissions");
}

export function decideTaskSubmission(
  submissionId: number,
  action: TaskReviewAction,
  comment: string,
): Promise<TaskSubmissionForReview> {
  return authorizedPost<TaskSubmissionForReview>(
    `/api/v1/admin/task-submissions/${submissionId}/decide`,
    { action, comment },
  );
}

export function fetchAdminOfferApplications(): Promise<OfferApplicationForReview[]> {
  return authorizedGet<OfferApplicationForReview[]>("/api/v1/admin/offer-applications");
}

export function decideOfferApplication(
  applicationId: number,
  action: OfferApplicationAction,
): Promise<OfferApplicationForReview> {
  return authorizedPost<OfferApplicationForReview>(
    `/api/v1/admin/offer-applications/${applicationId}/decide`,
    { action },
  );
}

// "Looking for a team" post moderation (app/handlers/admin/projects_block5_team.py) —
// distinct from the in-app ProjectWorkspace roles/applications: this broadcasts
// to the general Telegram chat.
export function fetchTeamPosts(): Promise<TeamPost[]> {
  return authorizedGet<TeamPost[]>("/api/v1/admin/projects/team-posts");
}

export function prepareTeamPost(projectId: number): Promise<TeamPost> {
  return authorizedPost<TeamPost>(`/api/v1/admin/projects/${projectId}/team-post/prepare`);
}

export function editTeamPost(projectId: number, text: string): Promise<TeamPost> {
  return authorizedPost<TeamPost>(`/api/v1/admin/projects/${projectId}/team-post/edit`, { text });
}

export function rejectTeamPost(projectId: number): Promise<TeamPost> {
  return authorizedPost<TeamPost>(`/api/v1/admin/projects/${projectId}/team-post/reject`);
}

export function publishTeamPost(projectId: number): Promise<TeamPost> {
  return authorizedPost<TeamPost>(`/api/v1/admin/projects/${projectId}/team-post/publish`);
}

// Post-moderation event operations (app/handlers/admin/event_registration_block14.py) —
// participants, attendance, points, for events already approved/published.
export function fetchOperationalEvents(): Promise<OperationalEvent[]> {
  return authorizedGet<OperationalEvent[]>("/api/v1/admin/events/operational");
}

export function fetchEventParticipants(eventId: number): Promise<EventParticipant[]> {
  return authorizedGet<EventParticipant[]>(`/api/v1/admin/events/${eventId}/participants`);
}

export function setEventAttendance(
  eventId: number,
  registrationId: number,
  attended: boolean,
): Promise<EventParticipant> {
  return authorizedPost<EventParticipant>(
    `/api/v1/admin/events/${eventId}/registrations/${registrationId}/attendance`,
    { attended },
  );
}

export function awardEventAttendancePoints(eventId: number): Promise<{ awarded_count: number }> {
  return authorizedPost(`/api/v1/admin/events/${eventId}/award-attendance-points`);
}

// Partner + offer catalog management (app/handlers/admin/partners_admin.py,
// the create/list/toggle/archive half of partner_offers_block16.py) —
// distinct from offer-application review above, which only ever reviewed
// applications to offers that already existed.
export function fetchAdminPartners(): Promise<Partner[]> {
  return authorizedGet<Partner[]>("/api/v1/admin/partners");
}

export function createPartner(payload: {
  name: string;
  description: string;
  source_url?: string;
}): Promise<Partner> {
  return authorizedPost<Partner>("/api/v1/admin/partners", payload);
}

export function setPartnerActive(partnerId: number, active: boolean): Promise<Partner> {
  return authorizedPost<Partner>(`/api/v1/admin/partners/${partnerId}/active`, { active });
}

export function archivePartner(partnerId: number): Promise<Partner> {
  return authorizedPost<Partner>(`/api/v1/admin/partners/${partnerId}/archive`);
}

export function fetchAdminOffers(): Promise<OfferAdmin[]> {
  return authorizedGet<OfferAdmin[]>("/api/v1/admin/offers");
}

export function createOffer(payload: {
  partner_id: number;
  title: string;
  description: string;
  point_cost: number;
  quantity?: number | null;
  expires_at?: string | null;
  instruction?: string;
  source_url?: string;
}): Promise<OfferAdmin> {
  return authorizedPost<OfferAdmin>("/api/v1/admin/offers", payload);
}

export function setOfferActive(offerId: number, active: boolean): Promise<OfferAdmin> {
  return authorizedPost<OfferAdmin>(`/api/v1/admin/offers/${offerId}/active`, { active });
}

export function archiveOffer(offerId: number): Promise<OfferAdmin> {
  return authorizedPost<OfferAdmin>(`/api/v1/admin/offers/${offerId}/archive`);
}

export interface AdminUsersQuery {
  query?: string;
  role?: string;
  includeArchived?: boolean;
  limit?: number;
  offset?: number;
}

export function fetchAdminUsers(params: AdminUsersQuery = {}): Promise<UserListResult> {
  const search = new URLSearchParams();
  if (params.query) search.set("query", params.query);
  if (params.role) search.set("role", params.role);
  if (params.includeArchived) search.set("include_archived", "true");
  if (params.limit) search.set("limit", String(params.limit));
  if (params.offset) search.set("offset", String(params.offset));
  const qs = search.toString();
  return authorizedGet<UserListResult>(`/api/v1/admin/users${qs ? `?${qs}` : ""}`);
}

export function fetchAdminUserDetail(userId: number): Promise<UserDetail> {
  return authorizedGet<UserDetail>(`/api/v1/admin/users/${userId}`);
}

export function changeUserRole(userId: number, role: string): Promise<UserDetail> {
  return authorizedPost<UserDetail>(`/api/v1/admin/users/${userId}/role`, { role });
}

export function setUserBlocked(userId: number, blocked: boolean): Promise<UserDetail> {
  return authorizedPost<UserDetail>(`/api/v1/admin/users/${userId}/block`, { blocked });
}

export function setUserArchived(userId: number, archived: boolean): Promise<UserDetail> {
  return authorizedPost<UserDetail>(`/api/v1/admin/users/${userId}/archive`, { archived });
}

export function toggleUserPermission(
  userId: number,
  permission: string,
): Promise<{ permission: string; enabled: boolean }> {
  return authorizedPost(`/api/v1/admin/users/${userId}/permissions/${permission}`);
}

export function awardUserPoints(
  userId: number,
  amount: number,
  reason: string,
): Promise<{ balance: number }> {
  return authorizedPost(`/api/v1/admin/users/${userId}/points`, { amount, reason });
}

export function awardUserBadge(userId: number, badgeId: number, reason: string): Promise<BadgeItem> {
  return authorizedPost(`/api/v1/admin/users/${userId}/badges/${badgeId}`, { reason });
}

export function fetchLeaderOverview(): Promise<LeaderOverview> {
  return authorizedGet<LeaderOverview>("/api/v1/leader/overview");
}

export function fetchLeaderOpenTasks(): Promise<LeaderOpenTask[]> {
  return authorizedGet<LeaderOpenTask[]>("/api/v1/leader/open-tasks");
}

export function createLeaderOpenTask(payload: OpenTaskCreatePayload): Promise<LeaderOpenTask> {
  return authorizedPost<LeaderOpenTask>("/api/v1/leader/open-tasks", payload);
}

export function decideLeaderApplication(
  taskId: number,
  userId: number,
  action: "accept" | "reject",
): Promise<LeaderOpenTask> {
  return authorizedPost<LeaderOpenTask>(
    `/api/v1/leader/open-tasks/${taskId}/applications/${userId}/decide`,
    { action },
  );
}

export function fetchProfile(): Promise<Profile> {
  return authorizedGet<Profile>("/api/v1/profile");
}

export async function downloadResumePdf(): Promise<Blob> {
  if (!sessionToken) {
    throw new ApiError(401, "missing_token");
  }
  const response = await fetch(`${API_BASE_URL}/api/v1/profile/resume.pdf`, {
    headers: { Authorization: `Bearer ${sessionToken}` },
  });
  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorDetail(response));
  }
  return response.blob();
}

export function hasSession(): boolean {
  return sessionToken !== null;
}

export function clearSession(): void {
  sessionToken = null;
}
