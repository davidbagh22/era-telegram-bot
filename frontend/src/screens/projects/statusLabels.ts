// Mirrors app/utils/constants.py labels — never show raw backend enums in UI.
export const PROJECT_STATUS_LABELS: Record<string, string> = {
  draft: "Черновик",
  pending_review: "На рассмотрении",
  initial_review: "Первичная проверка",
  venue_review: "Согласование площадки",
  needs_revision: "Нужна доработка",
  approved: "Одобрен",
  in_progress: "В работе",
  completed: "Завершён",
  rejected: "Не одобрен",
  postponed: "Перенесён",
  cancelled: "Отменён",
};

export const PROJECT_ROLE_STATUS_LABELS: Record<string, string> = {
  open: "Набор открыт",
  closed: "Набор закрыт",
};

export const PROJECT_TASK_STATUS_LABELS: Record<string, string> = {
  draft: "Черновик",
  new: "Новая",
  published: "Открыта",
  in_progress: "В работе",
  review: "На проверке",
  completed: "Выполнена",
  overdue: "Просрочена",
  cancelled: "Отменена",
};

export const PROJECT_MILESTONE_STATUS_LABELS: Record<string, string> = {
  planned: "Запланирован",
  in_progress: "В работе",
  completed: "Завершён",
  cancelled: "Отменён",
};

export const PROJECT_EVENT_STATUS_LABELS: Record<string, string> = {
  draft: "Черновик",
  pending_approval: "На согласовании",
  approved: "Одобрено",
  published: "Опубликовано",
  registration_open: "Регистрация открыта",
  registration_closed: "Регистрация закрыта",
  active: "Идёт сейчас",
  completed: "Завершено",
  report_submitted: "Отчёт отправлен",
  cancelled: "Отменено",
};

export const PROJECT_CONTRIBUTION_STATUS_LABELS: Record<string, string> = {
  pending: "Ожидает подтверждения",
  confirmed: "Вклад подтверждён",
  rejected: "Не подтверждён",
  none: "Без вклада",
};

const UNKNOWN = "Статус обновлён";

export function projectStatusLabel(status: string): string {
  return PROJECT_STATUS_LABELS[status] ?? UNKNOWN;
}

export function projectRoleStatusLabel(status: string): string {
  return PROJECT_ROLE_STATUS_LABELS[status] ?? UNKNOWN;
}

export function projectTaskStatusLabel(status: string): string {
  return PROJECT_TASK_STATUS_LABELS[status] ?? UNKNOWN;
}

export function projectMilestoneStatusLabel(status: string): string {
  return PROJECT_MILESTONE_STATUS_LABELS[status] ?? UNKNOWN;
}

export function projectEventStatusLabel(status: string): string {
  return PROJECT_EVENT_STATUS_LABELS[status] ?? UNKNOWN;
}

export function projectContributionStatusLabel(status: string): string {
  return PROJECT_CONTRIBUTION_STATUS_LABELS[status] ?? UNKNOWN;
}
