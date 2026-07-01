from enum import StrEnum


class Role(StrEnum):
    PARTICIPANT = "participant"
    ACTIVIST = "activist"
    LEADER = "leader"
    HEAD = "head"
    COUNCIL = "council"
    ADMIN = "admin"


PRIVILEGED_ROLES = {Role.LEADER, Role.HEAD, Role.COUNCIL, Role.ADMIN}


class ParticipationStatus(StrEnum):
    NEW_MEMBER = "new_member"
    INVOLVED_MEMBER = "involved_member"
    ACTIVE_MEMBER = "active_member"
    TEAM_MEMBER = "team_member"
    PROJECT_CURATOR = "project_curator"
    COMMUNITY_LEADER = "community_leader"


class ApplicationStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_INFO = "needs_info"


class EventStatus(StrEnum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    PUBLISHED = "published"
    REGISTRATION_OPEN = "registration_open"
    REGISTRATION_CLOSED = "registration_closed"
    ACTIVE = "active"
    COMPLETED = "completed"
    REPORT_SUBMITTED = "report_submitted"
    CANCELLED = "cancelled"


class RegistrationStatus(StrEnum):
    REGISTERED = "registered"
    WILL_COME = "will_come"
    NOT_COMING = "not_coming"
    ATTENDED = "attended"
    NO_SHOW = "no_show"
    CANCELLED = "cancelled"


class ProjectStatus(StrEnum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    INITIAL_REVIEW = "initial_review"
    VENUE_REVIEW = "venue_review"
    NEEDS_REVISION = "needs_revision"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REJECTED = "rejected"
    POSTPONED = "postponed"
    CANCELLED = "cancelled"


class TaskStatus(StrEnum):
    DRAFT = "draft"
    NEW = "new"
    PUBLISHED = "published"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    COMPLETED = "completed"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


ROLE_LABELS = {
    Role.PARTICIPANT: "Участник",
    Role.ACTIVIST: "Активист",
    Role.LEADER: "Лидер",
    Role.HEAD: "Руководитель",
    Role.COUNCIL: "Совет",
    Role.ADMIN: "Председатель / администратор",
}

STATUS_LABELS = {
    ParticipationStatus.NEW_MEMBER: "Новый участник",
    ParticipationStatus.INVOLVED_MEMBER: "Вовлечённый участник",
    ParticipationStatus.ACTIVE_MEMBER: "Активный участник",
    ParticipationStatus.TEAM_MEMBER: "Член команды",
    ParticipationStatus.PROJECT_CURATOR: "Куратор проекта",
    ParticipationStatus.COMMUNITY_LEADER: "Лидер сообщества",
}

APPLICATION_STATUS_LABELS = {
    ApplicationStatus.PENDING: "На рассмотрении",
    ApplicationStatus.APPROVED: "Одобрена",
    ApplicationStatus.REJECTED: "Не одобрена",
    ApplicationStatus.NEEDS_INFO: "Нужна дополнительная информация",
}

EVENT_STATUS_LABELS = {
    EventStatus.DRAFT: "Черновик",
    EventStatus.PENDING_APPROVAL: "На согласовании",
    EventStatus.APPROVED: "Одобрено",
    EventStatus.PUBLISHED: "Опубликовано",
    EventStatus.REGISTRATION_OPEN: "Регистрация открыта",
    EventStatus.REGISTRATION_CLOSED: "Регистрация закрыта",
    EventStatus.ACTIVE: "Идёт сейчас",
    EventStatus.COMPLETED: "Завершено",
    EventStatus.REPORT_SUBMITTED: "Отчёт отправлен",
    EventStatus.CANCELLED: "Отменено",
}

REGISTRATION_STATUS_LABELS = {
    RegistrationStatus.REGISTERED: "Зарегистрирован",
    RegistrationStatus.WILL_COME: "Подтвердил участие",
    RegistrationStatus.NOT_COMING: "Не сможет прийти",
    RegistrationStatus.ATTENDED: "Посетил",
    RegistrationStatus.NO_SHOW: "Не пришёл",
    RegistrationStatus.CANCELLED: "Регистрация отменена",
}

PROJECT_STATUS_LABELS = {
    ProjectStatus.DRAFT: "Черновик",
    ProjectStatus.PENDING_REVIEW: "На рассмотрении",
    ProjectStatus.INITIAL_REVIEW: "Первичная проверка",
    ProjectStatus.VENUE_REVIEW: "Согласование площадки",
    ProjectStatus.NEEDS_REVISION: "Нужна доработка",
    ProjectStatus.APPROVED: "Одобрен",
    ProjectStatus.IN_PROGRESS: "В работе",
    ProjectStatus.COMPLETED: "Завершён",
    ProjectStatus.REJECTED: "Не одобрен",
    ProjectStatus.POSTPONED: "Перенесён",
    ProjectStatus.CANCELLED: "Отменён",
}

TASK_STATUS_LABELS = {
    TaskStatus.DRAFT: "Черновик",
    TaskStatus.NEW: "Новая",
    TaskStatus.PUBLISHED: "Открыт набор",
    TaskStatus.IN_PROGRESS: "В работе",
    TaskStatus.REVIEW: "На проверке",
    TaskStatus.COMPLETED: "Выполнена",
    TaskStatus.OVERDUE: "Просрочена",
    TaskStatus.CANCELLED: "Отменена",
}

REPORT_TYPE_LABELS = {
    "event": "Отчёт по мероприятию",
    "monthly": "Месячный отчёт лидера",
}

REPORT_STATUS_LABELS = {
    "draft": "Черновик",
    "pending": "На рассмотрении",
    "submitted": "На рассмотрении",
    "approved": "Принят",
    "needs_revision": "Нужна доработка",
    "rejected": "Не принят",
}
