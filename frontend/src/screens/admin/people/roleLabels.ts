// Mirrors app/utils/constants.py's ROLE_LABELS / PERMISSION_LABELS — the
// frontend has no access to the Python source of truth, so these are kept
// in one place and only here, for both PeopleList and PersonDetail.
export const ROLE_LABELS: Record<string, string> = {
  participant: "Участник",
  activist: "Активист",
  leader: "Лидер",
  head: "Руководитель направления",
  council: "Совет",
  admin: "Админ",
};

export const ROLE_OPTIONS = Object.entries(ROLE_LABELS).map(([value, label]) => ({ value, label }));

export const PERMISSION_LABELS: Record<string, string> = {
  "panel.view": "Просмотр панели",
  "applications.review": "Одобрение заявок",
  "events.manage": "Управление мероприятиями",
  "projects.review": "Управление проектами",
  "partners.manage": "Управление партнёрами",
  "tasks.manage": "Управление задачами",
  "points.award": "Начисление баллов",
  "analytics.view": "Просмотр аналитики",
  "chat.moderate": "Модерация чата",
  "people.view": "Просмотр участников",
  "people.manage": "Управление участниками",
  "portfolio.review": "Портфолио и сертификаты",
  "broadcasts.create": "Рассылки и ответы",
};
