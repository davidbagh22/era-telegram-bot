from enum import StrEnum


class Role(StrEnum):
    PARTICIPANT = "participant"
    ACTIVIST = "activist"
    LEADER = "leader"
    HEAD = "head"
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


# Leadership OS (2026-08 master ToR "Analytics + Leadership OS") ------------
# Office/UserOffice stay the base directory objects (app/database/models.py);
# these enums back the new leadership layer built on top of them.


class PositionApplicationStatus(StrEnum):
    """Section 20 of the Leadership OS ToR."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    REVIEWING = "reviewing"
    INTERVIEW = "interview"
    RESERVE = "reserve"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    APPOINTED = "appointed"


class AppointmentType(StrEnum):
    """Section 25: regular vs acting (и.о.) appointments."""

    REGULAR = "regular"
    ACTING = "acting"


class LeadershipGoalStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class LeadershipReportStatus(StrEnum):
    """Section 40: the three quick-report traffic-light states."""

    ON_TRACK = "green"
    AT_RISK = "yellow"
    NEEDS_HELP = "red"


class AttentionItemStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class AttentionItemSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


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
    WAITLIST = "waitlist"
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
    Role.HEAD: "Руководитель направления",
    Role.COUNCIL: "Совет",
    Role.ADMIN: "Админ",
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
    RegistrationStatus.WAITLIST: "Лист ожидания",
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

DEPARTMENTS = {
    "Внутренние связи": ("Лидерство", "Культура", "Интерактив"),
    "Внешние связи": (
        "Международное направление",
        "Медиа",
        "Социальные инициативы",
    ),
}


class PointCategory(StrEnum):
    """Points/Ranks/Opportunities ToR ("ERA Platform — ранги, баллы...")
    section 47 phase 1: a single category taxonomy every PointTransaction
    is bucketed into, so caps/reporting/eligibility checks never have to
    pattern-match source_type strings directly. Existing source_type
    values keep their names -- they're mapped onto these categories via
    SOURCE_TYPE_TO_CATEGORY below rather than renamed, so nothing that
    already reads source_type breaks."""

    REGISTRATION = "registration"
    DIGITAL_ENGAGEMENT = "digital_engagement"
    EVENT = "event"
    TASK = "task"
    PROJECT = "project"
    VOLUNTEERING = "volunteering"
    MEDIA = "media"
    REPRESENTATION = "representation"
    MENTORSHIP = "mentorship"
    REFERRAL = "referral"
    REDEMPTION = "redemption"
    MANUAL = "manual"
    OTHER = "other"


# add_points() derives PointTransaction.category from source_type via this
# map when no explicit category is passed (see app/services/points_service.py).
# Unknown/unmapped source_types fall back to PointCategory.OTHER.
SOURCE_TYPE_TO_CATEGORY: dict[str, PointCategory] = {
    "registration": PointCategory.REGISTRATION,
    "registration_approval": PointCategory.REGISTRATION,
    "event_attendance": PointCategory.EVENT,
    "event_activity": PointCategory.EVENT,
    "attendance_proof": PointCategory.EVENT,
    "task_submission": PointCategory.TASK,
    "task_completion": PointCategory.TASK,
    "project_approval": PointCategory.PROJECT,
    "proposal_points": PointCategory.PROJECT,
    "manual_points": PointCategory.MANUAL,
    "manual_points_command": PointCategory.MANUAL,
    "badge_award": PointCategory.MANUAL,
    "partner_offer": PointCategory.REDEMPTION,
    "reward_redemption": PointCategory.REDEMPTION,
    "auction_win": PointCategory.REDEMPTION,
    "referral_registration": PointCategory.REFERRAL,
    "referral_first_event": PointCategory.REFERRAL,
    "point_transfer": PointCategory.OTHER,
    "digital_daily_open": PointCategory.DIGITAL_ENGAGEMENT,
    "digital_streak_7day": PointCategory.DIGITAL_ENGAGEMENT,
    "digital_event_registration": PointCategory.DIGITAL_ENGAGEMENT,
    "digital_vector_checkin": PointCategory.DIGITAL_ENGAGEMENT,
    "digital_vector_pulse": PointCategory.DIGITAL_ENGAGEMENT,
    "digital_goal_set": PointCategory.DIGITAL_ENGAGEMENT,
    "digital_goal_completed": PointCategory.DIGITAL_ENGAGEMENT,
}


# Digital engagement point values + caps (Points/Ranks ToR section 5). Small,
# capped-by-design points for using the app itself -- enforcement lives in
# app/services/digital_engagement_service.py. Caps the ToR lists but that
# have no existing UI trigger yet (full profile completion, material
# acknowledgement) are intentionally left out until that feature exists;
# wiring them in later is additive, not a rework of this table.
DIGITAL_ENGAGEMENT_POINTS = {
    "daily_open": 5,
    "streak_7day": 20,
    "event_registration": 10,
    "vector_monthly_checkin": 30,
    "vector_weekly_pulse": 10,
    "goal_set": 15,
    "goal_completed": 25,
}


# --- Event Scoring Profile (Points/Ranks ToR sections 16-20, phase 2) ------
# "What does this event count toward, and who did what" -- set once at event
# creation, then app/services/activity_scoring_service.py applies it
# automatically every time attendance is confirmed. Existing
# Event.points_for_visit (admin-set per event) is untouched -- these are
# *additional*, role-scoped bonuses on top of it, not a replacement.


class EventScoringPreset(StrEnum):
    """Section 17's ready-made presets. STANDARD is the default for every
    existing event (server_default), so nothing changes for events an admin
    hasn't opted into a preset for."""

    STANDARD = "standard"
    VOLUNTEERING = "volunteering"
    CULTURE = "culture"
    PROJECT = "project"
    MEDIA = "media"
    PARTNER = "partner"
    LEADERSHIP = "leadership"


EVENT_SCORING_PRESET_LABELS = {
    EventScoringPreset.STANDARD: "Обычное событие",
    EventScoringPreset.VOLUNTEERING: "Волонтёрская акция",
    EventScoringPreset.CULTURE: "Культурное мероприятие",
    EventScoringPreset.PROJECT: "Проектное мероприятие",
    EventScoringPreset.MEDIA: "Медиа-активность",
    EventScoringPreset.PARTNER: "Партнёрское / внешнее",
    EventScoringPreset.LEADERSHIP: "Лидерское / образовательное",
}

# The activity metric(s) a preset's *contributors* (any role beyond plain
# participant) add to, beyond the always-on events_attended count every
# attendee gets. Mirrors the section 20 worked example: a plain participant
# at a volunteering event only gets attendance + events_attended, while the
# volunteer/organizer roles additionally pick up these preset metrics.
EVENT_SCORING_PRESET_METRICS: dict[str, list[str]] = {
    EventScoringPreset.STANDARD: [],
    EventScoringPreset.VOLUNTEERING: ["volunteer_activities", "social_activities"],
    EventScoringPreset.CULTURE: ["culture_activities"],
    EventScoringPreset.PROJECT: ["project_activities"],
    EventScoringPreset.MEDIA: ["media_activities"],
    EventScoringPreset.PARTNER: ["partner_activities"],
    EventScoringPreset.LEADERSHIP: ["leadership_activities"],
}


class EventParticipantRole(StrEnum):
    """Section 19's per-event roles. PARTICIPANT (the default) carries no
    bonus -- it's just Event.points_for_visit, unchanged."""

    PARTICIPANT = "participant"
    VOLUNTEER = "volunteer"
    ORGANIZER_HELPER = "organizer_helper"
    ORGANIZER = "organizer"
    COORDINATOR = "coordinator"
    SPEAKER = "speaker"
    MODERATOR = "moderator"
    MEDIA = "media"
    PHOTOGRAPHER = "photographer"
    VIDEOGRAPHER = "videographer"
    OTHER = "other"


EVENT_ROLE_LABELS = {
    EventParticipantRole.PARTICIPANT: "Участник",
    EventParticipantRole.VOLUNTEER: "Волонтёр",
    EventParticipantRole.ORGANIZER_HELPER: "Помощь в организации",
    EventParticipantRole.ORGANIZER: "Организатор",
    EventParticipantRole.COORDINATOR: "Координатор",
    EventParticipantRole.SPEAKER: "Спикер",
    EventParticipantRole.MODERATOR: "Модератор",
    EventParticipantRole.MEDIA: "Медиа",
    EventParticipantRole.PHOTOGRAPHER: "Фотограф",
    EventParticipantRole.VIDEOGRAPHER: "Видеограф",
    EventParticipantRole.OTHER: "Другое",
}

# Flat role bonus (ToR section 7). VOLUNTEER isn't here -- it's computed as
# hours * VOLUNTEER_HOURLY_POINTS, capped at VOLUNTEER_HOURS_POINTS_CAP.
# OTHER carries no automatic bonus (admin can still award manually).
EVENT_ROLE_POINTS: dict[str, int] = {
    EventParticipantRole.PARTICIPANT: 0,
    EventParticipantRole.ORGANIZER_HELPER: 150,
    EventParticipantRole.ORGANIZER: 250,
    EventParticipantRole.COORDINATOR: 300,
    EventParticipantRole.SPEAKER: 150,
    EventParticipantRole.MODERATOR: 150,
    EventParticipantRole.MEDIA: 150,
    EventParticipantRole.PHOTOGRAPHER: 150,
    EventParticipantRole.VIDEOGRAPHER: 150,
    EventParticipantRole.OTHER: 0,
}

VOLUNTEER_HOURLY_POINTS = 25
VOLUNTEER_HOURS_POINTS_CAP = 200

# Which "how many times has this person done X" counter a role's bonus adds
# to, on top of the preset's own metrics (see EVENT_SCORING_PRESET_METRICS).
EVENT_ROLE_METRIC: dict[str, str] = {
    EventParticipantRole.ORGANIZER_HELPER: "events_organized",
    EventParticipantRole.ORGANIZER: "events_organized",
    EventParticipantRole.COORDINATOR: "events_organized",
    EventParticipantRole.SPEAKER: "leadership_activities",
    EventParticipantRole.MODERATOR: "leadership_activities",
    EventParticipantRole.MEDIA: "media_activities",
    EventParticipantRole.PHOTOGRAPHER: "media_activities",
    EventParticipantRole.VIDEOGRAPHER: "media_activities",
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
    "Первый шаг",
    "Голос ЭРА",
    "Надёжный участник",
    "Командный игрок",
    "Организатор",
    "Проектный автор",
    "Медиа-двигатель",
    "Амбассадор ЭРА",
    "Наставник",
    "Прорыв месяца",
)

PRIVILEGED_ROLES = {Role.LEADER, Role.HEAD, Role.COUNCIL, Role.ADMIN}
ADMIN_ROLES = {Role.ADMIN}

PERMISSIONS = (
    "panel.view",
    "applications.review",
    "events.manage",
    "projects.review",
    "partners.manage",
    "tasks.manage",
    "points.award",
    "analytics.view",
    "chat.moderate",
    "people.view",
    "people.manage",
    "portfolio.review",
    "broadcasts.create",
    "development.self.read",
    "development.self.write",
    "development.admin.summary.read",
    "development.admin.individual.read",
    "development.admin.analytics.read",
    "development.admin.export",
    "development.methodology.manage",
    "development.content.manage",
)

PERMISSION_LABELS = {
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
    "development.self.read": "Мой вектор: свои данные",
    "development.self.write": "Мой вектор: свои ответы",
    "development.admin.summary.read": "Мой вектор: разрешённые сводки",
    "development.admin.individual.read": "Мой вектор: индивидуальные профили",
    "development.admin.analytics.read": "Мой вектор: групповая аналитика",
    "development.admin.export": "Мой вектор: экспорт агрегатов",
    "development.methodology.manage": "Мой вектор: методики",
    "development.content.manage": "Мой вектор: контент рекомендаций",
}
