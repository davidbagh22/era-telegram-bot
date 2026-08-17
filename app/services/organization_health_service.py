from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Broadcast,
    DataDeletionRequest,
    DepartmentApplication,
    Event,
    EventActivitySubmission,
    EventRegistration,
    Feedback,
    PointTransaction,
    Project,
    ProjectMember,
    Task,
    TaskDelivery,
    TaskSubmission,
    User,
    UserDepartment,
    UserDirection,
)
from app.services import development_analytics
from app.services.admin_dashboard_service import dashboard_metrics
from app.utils.constants import (
    ApplicationStatus,
    EventStatus,
    ProjectStatus,
    RegistrationStatus,
    Role,
    TaskStatus,
)


@dataclass(frozen=True)
class HealthMetric:
    key: str
    category: str
    label: str
    value: float
    display: str
    note: str
    score: int | None = None


@dataclass(frozen=True)
class VectorDimension:
    key: str
    label: str
    value: int
    delta: int | None


@dataclass(frozen=True)
class OrganizationHealthSnapshot:
    pulse: int | None
    pulse_label: str
    pulse_coverage: int
    pulse_sample_size: int
    pulse_suppressed: bool
    vector_dimensions: list[VectorDimension]
    metrics: list[HealthMetric]
    risks: list[str]
    period_label: str
    data_note: str


def _cap(value: float) -> int:
    return max(0, min(100, round(value)))


def _pct(part: int | float, total: int | float) -> float:
    return round((part / total) * 100, 1) if total else 0.0


def _score_label(score: int | None, *, suppressed: bool = False) -> str:
    if suppressed or score is None:
        return "Нужно больше Check-in"
    if score >= 80:
        return "Сообщество в сильном состоянии"
    if score >= 65:
        return "Состояние устойчивое"
    if score >= 50:
        return "Есть напряжение, но ресурс сохранён"
    return "Сообществу нужна поддержка"


async def _count(session: AsyncSession, model, *conditions) -> int:
    query = select(func.count()).select_from(model)
    for condition in conditions:
        query = query.where(condition)
    return int(await session.scalar(query) or 0)


async def build_organization_health(session: AsyncSession) -> OrganizationHealthSnapshot:
    """Build a broad, factual organization-health snapshot.

    The second top-level KPI — ``pulse`` — comes only from the privacy-safe
    aggregate current-state part of "Мой вектор". Stable traits, interests,
    notes and individual answers never enter the pulse. Cohorts smaller than
    the development privacy threshold stay suppressed.
    """

    now = datetime.now(timezone.utc)
    today = date.today()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    quarter_ago = now - timedelta(days=90)
    month_ago_date = today - timedelta(days=30)
    two_weeks_ahead = today + timedelta(days=14)

    approved_filter = (
        User.application_status == ApplicationStatus.APPROVED,
        User.is_archived.is_(False),
        User.is_blocked.is_(False),
    )

    approved_total = await _count(session, User, *approved_filter)
    new_7d = await _count(session, User, *approved_filter, User.created_at >= week_ago)
    new_30d = await _count(session, User, *approved_filter, User.created_at >= month_ago)
    leaders = await _count(
        session,
        User,
        *approved_filter,
        User.role.in_([Role.LEADER, Role.HEAD, Role.COUNCIL, Role.ADMIN]),
    )
    activists = await _count(session, User, *approved_filter, User.role == Role.ACTIVIST)
    progressed = await _count(
        session,
        User,
        *approved_filter,
        User.role.in_([Role.ACTIVIST, Role.LEADER, Role.HEAD, Role.COUNCIL, Role.ADMIN]),
    )

    async def active_users_since(cutoff: datetime) -> int:
        return int(
            await session.scalar(
                select(func.count(func.distinct(PointTransaction.user_id)))
                .join(User, User.id == PointTransaction.user_id)
                .where(PointTransaction.created_at >= cutoff, *approved_filter)
            )
            or 0
        )

    active_7d = await active_users_since(week_ago)
    active_30d = await active_users_since(month_ago)
    active_90d = await active_users_since(quarter_ago)
    dormant_30d = max(approved_total - active_30d, 0)

    retention_denominator = await _count(session, User, *approved_filter, User.created_at < month_ago)
    retained_30d = int(
        await session.scalar(
            select(func.count(func.distinct(User.id)))
            .join(PointTransaction, PointTransaction.user_id == User.id)
            .where(
                *approved_filter,
                User.created_at < month_ago,
                PointTransaction.created_at >= month_ago,
            )
        )
        or 0
    )

    department_users = int(
        await session.scalar(
            select(func.count(func.distinct(UserDepartment.user_id)))
            .join(User, User.id == UserDepartment.user_id)
            .where(*approved_filter)
        )
        or 0
    )
    direction_users = int(
        await session.scalar(
            select(func.count(func.distinct(UserDirection.user_id)))
            .join(User, User.id == UserDirection.user_id)
            .where(*approved_filter)
        )
        or 0
    )

    live_event_statuses = [
        EventStatus.APPROVED,
        EventStatus.PUBLISHED,
        EventStatus.REGISTRATION_OPEN,
        EventStatus.REGISTRATION_CLOSED,
        EventStatus.ACTIVE,
        EventStatus.COMPLETED,
        EventStatus.REPORT_SUBMITTED,
    ]
    events_30d = await _count(
        session,
        Event,
        Event.event_date >= month_ago_date,
        Event.event_date <= today,
        Event.status.in_(live_event_statuses),
    )
    upcoming_14d = await _count(
        session,
        Event,
        Event.event_date >= today,
        Event.event_date <= two_weeks_ahead,
        Event.status.in_(live_event_statuses),
    )
    event_registrations_30d = int(
        await session.scalar(
            select(func.count(EventRegistration.id))
            .join(Event, Event.id == EventRegistration.event_id)
            .where(
                Event.event_date >= month_ago_date,
                Event.event_date <= today,
                EventRegistration.status.in_([
                    RegistrationStatus.REGISTERED,
                    RegistrationStatus.WILL_COME,
                    RegistrationStatus.ATTENDED,
                    RegistrationStatus.NO_SHOW,
                ]),
            )
        )
        or 0
    )
    attended_30d = int(
        await session.scalar(
            select(func.count(EventRegistration.id))
            .join(Event, Event.id == EventRegistration.event_id)
            .where(
                Event.event_date >= month_ago_date,
                Event.event_date <= today,
                EventRegistration.status == RegistrationStatus.ATTENDED,
            )
        )
        or 0
    )
    no_show_30d = int(
        await session.scalar(
            select(func.count(EventRegistration.id))
            .join(Event, Event.id == EventRegistration.event_id)
            .where(
                Event.event_date >= month_ago_date,
                Event.event_date <= today,
                EventRegistration.status == RegistrationStatus.NO_SHOW,
            )
        )
        or 0
    )
    attendance_decided = attended_30d + no_show_30d
    attendance_rate = _pct(attended_30d, attendance_decided)

    feedback_count = int(
        await session.scalar(
            select(func.count(Feedback.id))
            .join(Event, Event.id == Feedback.event_id)
            .where(Event.event_date >= month_ago_date, Event.event_date <= today)
        )
        or 0
    )
    feedback_avg = float(
        await session.scalar(
            select(func.avg(Feedback.rating))
            .join(Event, Event.id == Feedback.event_id)
            .where(Event.event_date >= month_ago_date, Event.event_date <= today)
        )
        or 0.0
    )
    feedback_rate = _pct(feedback_count, attended_30d)

    active_projects = await _count(
        session,
        Project,
        Project.status.in_([ProjectStatus.APPROVED, ProjectStatus.IN_PROGRESS]),
    )
    new_projects_30d = await _count(
        session,
        Project,
        Project.created_at >= month_ago,
        Project.status != ProjectStatus.CANCELLED,
    )
    completed_projects = await _count(session, Project, Project.status == ProjectStatus.COMPLETED)
    project_members = await _count(
        session,
        ProjectMember,
        ProjectMember.joined_at.is_not(None),
        ProjectMember.status.in_(["approved", "active", "member"]),
    )

    open_tasks = await _count(
        session,
        Task,
        Task.status.in_([TaskStatus.NEW, TaskStatus.PUBLISHED, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW]),
    )
    completed_tasks_30d = await _count(
        session,
        Task,
        Task.status == TaskStatus.COMPLETED,
        Task.updated_at >= month_ago,
    )
    overdue_tasks = await _count(
        session,
        Task,
        Task.deadline < now,
        Task.status.not_in([TaskStatus.COMPLETED, TaskStatus.CANCELLED]),
    )
    task_submissions_30d = await _count(session, TaskSubmission, TaskSubmission.created_at >= month_ago)
    task_approved_30d = await _count(
        session,
        TaskSubmission,
        TaskSubmission.created_at >= month_ago,
        TaskSubmission.status == "approved",
    )
    activity_submissions_30d = await _count(
        session, EventActivitySubmission, EventActivitySubmission.created_at >= month_ago
    )
    activity_approved_30d = await _count(
        session,
        EventActivitySubmission,
        EventActivitySubmission.created_at >= month_ago,
        EventActivitySubmission.status == "approved",
    )

    point_actions_30d = await _count(session, PointTransaction, PointTransaction.created_at >= month_ago)
    points_30d = int(
        await session.scalar(
            select(func.coalesce(func.sum(PointTransaction.points), 0)).where(
                PointTransaction.created_at >= month_ago
            )
        )
        or 0
    )

    sent_deliveries_30d = await _count(
        session,
        TaskDelivery,
        TaskDelivery.created_at >= month_ago,
        TaskDelivery.status == "sent",
    )
    failed_deliveries_30d = await _count(
        session,
        TaskDelivery,
        TaskDelivery.created_at >= month_ago,
        TaskDelivery.status == "failed",
    )
    delivery_total = sent_deliveries_30d + failed_deliveries_30d
    broadcasts_30d = await _count(
        session,
        Broadcast,
        Broadcast.sent_at.is_not(None),
        Broadcast.sent_at >= month_ago,
    )
    pending_data_rights = await _count(
        session, DataDeletionRequest, DataDeletionRequest.status == "pending"
    )
    pending_department_apps = await _count(
        session, DepartmentApplication, DepartmentApplication.status == "pending"
    )
    queues = await dashboard_metrics(session)

    vector = await development_analytics.community_analytics(session, period_days=30)
    vector_suppressed = bool(vector.get("suppressed", True))
    pulse = None if vector_suppressed else int(vector.get("index") or 0)
    vector_dimensions: list[VectorDimension] = []
    if not vector_suppressed:
        from app.services import development_service as dev

        state = vector.get("state") or {}
        delta = vector.get("delta") or {}
        vector_dimensions = [
            VectorDimension(
                key=code,
                label=dev.STATE_LABELS[code],
                value=int(state.get(code, 0)),
                delta=int(delta[code]) if code in delta else None,
            )
            for code in dev.STATE_DIMENSIONS
        ]

    metrics = [
        HealthMetric("approved", "Люди", "Одобрено участников", approved_total, str(approved_total), "текущая база без архивных и заблокированных"),
        HealthMetric("new_7d", "Люди", "Новые за 7 дней", new_7d, f"+{new_7d}", "одобрены за последнюю неделю"),
        HealthMetric("new_30d", "Люди", "Новые за 30 дней", new_30d, f"+{new_30d}", "одобрены за последний месяц"),
        HealthMetric("leaders", "Люди", "Лидеров и руководителей", leaders, str(leaders), f"{_pct(leaders, approved_total):.1f}% сообщества"),
        HealthMetric("activists", "Люди", "Активистов", activists, str(activists), "роль «активист» в системе"),
        HealthMetric("growth_conversion", "Люди", "Рост участник → активный/лидер", _pct(progressed, approved_total), f"{_pct(progressed, approved_total):.1f}%", "доля одобренных, перешедших из базовой роли", _cap(_pct(progressed, approved_total))),
        HealthMetric("department_coverage", "Люди", "Выбрали департамент", _pct(department_users, approved_total), f"{_pct(department_users, approved_total):.1f}%", "структурная включённость"),
        HealthMetric("direction_coverage", "Люди", "Выбрали направление", _pct(direction_users, approved_total), f"{_pct(direction_users, approved_total):.1f}%", "предметная включённость"),
        HealthMetric("active_7d", "Вовлечённость", "Активны за 7 дней", active_7d, f"{active_7d} · {_pct(active_7d, approved_total):.1f}%", "есть подтверждённое действие/баллы"),
        HealthMetric("active_30d", "Вовлечённость", "Активны за 30 дней", active_30d, f"{active_30d} · {_pct(active_30d, approved_total):.1f}%", "основной показатель текущей вовлечённости", _cap(_pct(active_30d, approved_total))),
        HealthMetric("active_90d", "Вовлечённость", "Активны за 90 дней", active_90d, f"{active_90d} · {_pct(active_90d, approved_total):.1f}%", "широкий контур удержания"),
        HealthMetric("retention_30d", "Вовлечённость", "30-дневное удержание", _pct(retained_30d, retention_denominator), f"{_pct(retained_30d, retention_denominator):.1f}%", "из участников старше 30 дней проявили активность за последний месяц", _cap(_pct(retained_30d, retention_denominator))),
        HealthMetric("dormant_30d", "Вовлечённость", "Без активности 30 дней", dormant_30d, str(dormant_30d), "одобрены, но без подтверждённых действий за месяц"),
        HealthMetric("events_30d", "События", "Мероприятий за 30 дней", events_30d, str(events_30d), "проведённые/живые события"),
        HealthMetric("upcoming_14d", "События", "Событий на 14 дней", upcoming_14d, str(upcoming_14d), "запланированный ритм"),
        HealthMetric("event_registrations", "События", "Регистраций за 30 дней", event_registrations_30d, str(event_registrations_30d), "по событиям последнего месяца"),
        HealthMetric("attendance_rate", "События", "Явка", attendance_rate, f"{attendance_rate:.1f}%", f"пришли {attended_30d} · no-show {no_show_30d}", _cap(attendance_rate)),
        HealthMetric("feedback", "События", "Оценка мероприятий", feedback_avg, f"{feedback_avg:.1f}/5" if feedback_count else "Нет данных", f"{feedback_count} отзывов · охват {_pct(feedback_count, attended_30d):.1f}%", _cap((feedback_avg / 5) * 100) if feedback_count else None),
        HealthMetric("feedback_rate", "События", "Охват обратной связью", feedback_rate, f"{feedback_rate:.1f}%", "доля посетивших, оставивших отзыв"),
        HealthMetric("active_projects", "Проекты", "Проектов в работе", active_projects, str(active_projects), "одобрены или уже реализуются"),
        HealthMetric("new_projects_30d", "Проекты", "Новых проектов за 30 дней", new_projects_30d, str(new_projects_30d), "новый проектный поток"),
        HealthMetric("completed_projects", "Проекты", "Завершено проектов", completed_projects, str(completed_projects), "накопленный подтверждённый результат"),
        HealthMetric("project_members", "Проекты", "Участий в командах", project_members, str(project_members), "подтверждённые включения в проектные команды"),
        HealthMetric("open_tasks", "Исполнение", "Открытых заданий", open_tasks, str(open_tasks), "новые, опубликованные, в работе или на проверке"),
        HealthMetric("completed_tasks_30d", "Исполнение", "Заданий завершено за 30 дней", completed_tasks_30d, str(completed_tasks_30d), "реальный операционный выпуск"),
        HealthMetric("overdue_tasks", "Исполнение", "Просроченных заданий", overdue_tasks, str(overdue_tasks), "срок прошёл, задача не закрыта"),
        HealthMetric("task_acceptance", "Исполнение", "Принято результатов заданий", _pct(task_approved_30d, task_submissions_30d), f"{_pct(task_approved_30d, task_submissions_30d):.1f}%", f"{task_approved_30d} из {task_submissions_30d} отправок за 30 дней"),
        HealthMetric("activity_acceptance", "Исполнение", "Принято активностей событий", _pct(activity_approved_30d, activity_submissions_30d), f"{_pct(activity_approved_30d, activity_submissions_30d):.1f}%", f"{activity_approved_30d} из {activity_submissions_30d} отправок за 30 дней"),
        HealthMetric("point_actions", "Исполнение", "Подтверждённых действий", point_actions_30d, str(point_actions_30d), f"{points_30d:+d} баллов за 30 дней"),
        HealthMetric("queue", "Операции", "На очереди решений", queues.attention_total, str(queues.attention_total), "заявки, модерация, результаты, вопросы и отчёты"),
        HealthMetric("department_apps", "Операции", "Заявок в департаменты", pending_department_apps, str(pending_department_apps), "ждут решения"),
        HealthMetric("data_rights", "Операции", "Запросов по данным", pending_data_rights, str(pending_data_rights), "запросы на удаление/анонимизацию ждут обработки"),
        HealthMetric("task_delivery", "Операции", "Доставка заданий", _pct(sent_deliveries_30d, delivery_total), f"{_pct(sent_deliveries_30d, delivery_total):.1f}%" if delivery_total else "Нет отправок", f"успешно {sent_deliveries_30d} · ошибок {failed_deliveries_30d}"),
        HealthMetric("broadcasts", "Операции", "Рассылок за 30 дней", broadcasts_30d, str(broadcasts_30d), "отправленные рассылки"),
    ]

    risks: list[str] = []
    if _pct(active_30d, approved_total) < 35 and approved_total:
        risks.append("Низкая 30-дневная вовлечённость: нужен быстрый маршрут возвращения людей в действие.")
    if retention_denominator and _pct(retained_30d, retention_denominator) < 35:
        risks.append("Слабое удержание старших участников: проверьте переход участник → активный → лидер.")
    if upcoming_14d == 0:
        risks.append("На ближайшие 14 дней нет живых событий в системе.")
    if overdue_tasks > 0:
        risks.append(f"Просрочено заданий: {overdue_tasks}. Их стоит закрыть, переназначить или обновить срок.")
    if failed_deliveries_30d > 0:
        risks.append(f"Есть ошибки доставки заданий в Telegram: {failed_deliveries_30d} за 30 дней.")
    if queues.attention_total >= 10:
        risks.append(f"Очередь решений выросла до {queues.attention_total}: админ-процессы начинают тормозить участников.")
    if vector_suppressed:
        risks.append("Пульс по «Моему вектору» пока скрыт: нужно минимум 5 безопасно агрегируемых Check-in.")
    elif pulse is not None and pulse < 50:
        risks.append("Пульс сообщества ниже 50/100: не увеличивайте нагрузку без разбора пяти областей состояния.")

    return OrganizationHealthSnapshot(
        pulse=pulse,
        pulse_label=_score_label(pulse, suppressed=vector_suppressed),
        pulse_coverage=int(vector.get("coverage_percent") or 0),
        pulse_sample_size=int(vector.get("sample_size") or 0),
        pulse_suppressed=vector_suppressed,
        vector_dimensions=vector_dimensions,
        metrics=metrics,
        risks=risks[:8],
        period_label="операционные показатели: последние 7/30/90 дней · Пульс: последние 30 дней",
        data_note=(
            "Пульс рассчитывается только по агрегированным пяти текущим состояниям «Моего вектора» "
            "и показывается при безопасной выборке от 5 человек. Черты, интересы, личные заметки и "
            "индивидуальные ответы в Пульс не входят. Остальные показатели считаются по фактическим "
            "событиям платформы."
        ),
    )
