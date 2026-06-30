from enum import StrEnum


class Role(StrEnum):
    PARTICIPANT = "participant"
    ACTIVIST = "activist"
    LEADER = "leader"
    COUNCIL = "council"
    ADMIN = "admin"


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
    NEEDS_REVISION = "needs_revision"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REJECTED = "rejected"


class TaskStatus(StrEnum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    COMPLETED = "completed"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


ROLE_LABELS = {
    Role.PARTICIPANT: "Участник",
    Role.ACTIVIST: "Активист",
    Role.LEADER: "Лидер",
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

DEPARTMENTS = {
    "Внутренние связи": ("Лидерство", "Культура", "Интерактив"),
    "Внешние связи": (
        "Международное направление",
        "Медиа",
        "Социальные инициативы",
    ),
}

DEFAULT_POINTS = {
    "Регистрация в боте": 5,
    "Посещение мероприятия": 5,
    "Подтверждённое селфи": 5,
    "Помощь в организации": 15,
    "Волонтёрство": 20,
    "Создание контента": 15,
    "Привлечение нового участника": 10,
    "Предложение идеи проекта": 10,
    "Одобренный проект": 30,
    "Участие в реализации проекта": 20,
    "Роль ведущего / спикера": 25,
    "Выполнение задачи": 10,
    "Получение знака отличия": 20,
    "Наставничество": 25,
    "Поддержка ЭРА": 15,
}

BADGES = (
    "Голос ЭРА",
    "Медиа-движок",
    "Организатор",
    "Волонтёр ЭРА",
    "Проектный автор",
    "Лидер месяца",
    "Амбассадор ЭРА",
    "Надёжный человек",
    "Командный игрок",
    "Прорыв месяца",
    "Наставник",
    "Поддержка ЭРА",
)

PRIVILEGED_ROLES = {Role.LEADER, Role.COUNCIL, Role.ADMIN}
ADMIN_ROLES = {Role.ADMIN}
