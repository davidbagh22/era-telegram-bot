// Mirrors app/utils/constants.py's PROJECT_STATUS_LABELS exactly -- the
// backend never sent a human label alongside the raw enum, so the API
// response's `status` field was rendered as-is everywhere a project
// appeared (list, detail, workspace, admin moderation). 2026-08 UX/UI
// redesign brief section 25: "Никогда не показывать raw backend enum."
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

export function projectStatusLabel(status: string): string {
  return PROJECT_STATUS_LABELS[status] ?? status;
}
