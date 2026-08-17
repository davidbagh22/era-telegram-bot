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
  "applications.review": "Работа с заявками",
  "events.manage": "Управление мероприятиями",
  "projects.review": "Модерация проектов",
  "partners.manage": "Партнёры и возможности",
  "tasks.manage": "Управление заданиями",
  "points.award": "Баллы и знаки отличия",
  "analytics.view": "Аналитика",
  "chat.moderate": "Модерация чатов",
  "people.view": "Просмотр участников",
  "people.manage": "Управление участниками",
  "portfolio.review": "Портфолио и сертификаты",
  "broadcasts.create": "Рассылки и ответы",
  "development.self.read": "Мой вектор · свои данные",
  "development.self.write": "Мой вектор · свои ответы",
  "development.admin.summary.read": "Мой вектор · сводки",
  "development.admin.individual.read": "Мой вектор · профили участников",
  "development.admin.analytics.read": "Мой вектор · аналитика сообщества",
  "development.admin.export": "Мой вектор · экспорт агрегатов",
  "development.methodology.manage": "Мой вектор · методики",
  "development.content.manage": "Мой вектор · рекомендации",
};

export const PERMISSION_DESCRIPTIONS: Record<string, string> = {
  "panel.view": "Открывать рабочую панель и видеть доступные ему управленческие разделы.",
  "applications.review": "Просматривать новые регистрации, запрашивать уточнения, одобрять или отклонять заявки.",
  "events.manage": "Создавать и редактировать мероприятия, работать со списками участников, посещаемостью и публикацией.",
  "projects.review": "Просматривать проекты участников, отправлять на доработку, одобрять и сопровождать их движение по статусам.",
  "partners.manage": "Вести партнёров, возможности и связанные с ними предложения для участников.",
  "tasks.manage": "Создавать задания, управлять ими и проверять результаты участников.",
  "points.award": "Начислять и списывать баллы, а также выдавать знаки отличия с обязательной причиной.",
  "analytics.view": "Смотреть показатели сообщества, динамику и доступные аналитические выгрузки.",
  "chat.moderate": "Использовать доступные инструменты модерации организационных чатов ЭРА.",
  "people.view": "Открывать список участников и их расширенные карточки: анкету, активность, интересы и результаты.",
  "people.manage": "Менять роли и статусы участников, блокировать и возвращать из архива в пределах своих полномочий.",
  "portfolio.review": "Проверять портфолио, подтверждения достижений и связанные сертификаты.",
  "broadcasts.create": "Создавать рассылки, работать с обращениями и коммуникацией с участниками.",
  "development.self.read": "Читать собственный личный профиль развития.",
  "development.self.write": "Сохранять собственные Check-in, цели, заметки и обратную связь по выводам.",
  "development.admin.summary.read": "Видеть только разрешённые участниками сводные показатели развития.",
  "development.admin.individual.read": "Открывать индивидуальный разрешённый профиль развития с обязательным аудитом доступа.",
  "development.admin.analytics.read": "Смотреть агрегированную аналитику только при безопасном размере выборки.",
  "development.admin.export": "Экспортировать только разрешённую агрегированную аналитику развития.",
  "development.methodology.manage": "Управлять версиями методик после методологического и лицензионного согласования.",
  "development.content.manage": "Управлять семействами и формулировками рекомендаций без изменения научного scoring.",
};
