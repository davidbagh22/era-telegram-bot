from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Broadcast,
    DataDeletionRequest,
    DepartmentApplication,
    Event,
    EventActivitySubmission,
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
from app.database.participation_models import ParticipationLifecycle
from app.services.analytics_snapshot_service import ACTIVE_PROJECT_STATUSES, activity_cohort_counts, build_event_analytics, count_new_members, count_verified_users
from app.services import development_analytics
from app.services.admin_dashboard_service import dashboard_metrics
from app.services.meaningful_activity_service import (
    meaningful_points_condition,
)
from app.services.participation_lifecycle_service import MODE_ACTIVE, MODE_EXITED, MODE_LIGHT
from app.utils.constants import (
    ApplicationStatus,
    EventStatus,
    ProjectStatus,
    Role,
    TaskStatus,
)


@dataclass(frozen=True)
class HealthMetric:
    key: str
    category: str
    label: str
    value: float | None
    display: str
    note: str
    score: int | None = None
    numerator: float | None = None
    denominator: float | None = None
    unit: str = "count"
    data_state: str = "valid"


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
        return "Нужно больше отметок в «Моём векторе»"
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


def _current_roster_conditions():
    return (
        User.application_status == ApplicationStatus.APPROVED,
        User.is_archived.is_(False),
        User.is_blocked.is_(False),
        or_(
            ParticipationLifecycle.user_id.is_(None),
            ParticipationLifecycle.participation_mode != MODE_EXITED,
        ),
    )


def _active_denominator_conditions():
    return (
        User.application_status == ApplicationStatus.APPROVED,
        User.is_archived.is_(False),
        User.is_blocked.is_(False),
        or_(
            ParticipationLifecycle.user_id.is_(None),
            ParticipationLifecycle.participation_mode.in_([MODE_ACTIVE, MODE_LIGHT]),
        ),
    )


async def _user_count(session: AsyncSession, *conditions) -> int:
    return int(
        await session.scalar(
            select(func.count(User.id))
            .select_from(User)
            .outerjoin(ParticipationLifecycle, ParticipationLifecycle.user_id == User.id)
            .where(*conditions)
        )
        or 0
    )


async def _meaningful_active_count(session: AsyncSession, cutoff: datetime) -> int:
    return await count_verified_users(session, cutoff, datetime.now(timezone.utc))


async def build_organization_health(session: AsyncSession) -> OrganizationHealthSnapshot:
    """Build factual organization health from verified operational activity.

    Digital engagement points (daily app entry, Vector check-ins, profile
    actions, etc.) remain reputation events but never make Active Base or
    retention look healthier. Participation mode is also respected: PAUSED,
    OBSERVER and EXITED are removed from the active denominator while their
    history remains intact.
    """

    now = datetime.now(timezone.utc)
    today = date.today()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    quarter_ago = now - timedelta(days=90)
    two_weeks_ahead = today + timedelta(days=14)

    approved_total = await _user_count(session, *_current_roster_conditions())
    active_denominator = approved_total
    new_7d = await count_new_members(session, week_ago, now)
    new_30d = await count_new_members(session, month_ago, now)
    leaders = await _user_count(
        session,
        *_current_roster_conditions(),
        User.role.in_([Role.LEADER, Role.HEAD, Role.COUNCIL, Role.ADMIN]),
    )
    activists = await _user_count(
        session, *_current_roster_conditions(), User.role == Role.ACTIVIST
    )
    progressed = await _user_count(
        session,
        *_current_roster_conditions(),
        User.role.in_([Role.ACTIVIST, Role.LEADER, Role.HEAD, Role.COUNCIL, Role.ADMIN]),
    )

    active_7d = await _meaningful_active_count(session, week_ago)
    active_30d = await _meaningful_active_count(session, month_ago)
    active_90d = await _meaningful_active_count(session, quarter_ago)
    dormant_30d = max(active_denominator - active_30d, 0)

    _, retention_denominator, retained_30d, _, _ = await activity_cohort_counts(session, now=now)


    department_users = int(
        await session.scalar(
            select(func.count(func.distinct(UserDepartment.user_id)))
            .join(User, User.id == UserDepartment.user_id)
            .outerjoin(ParticipationLifecycle, ParticipationLifecycle.user_id == User.id)
            .where(*_current_roster_conditions())
        )
        or 0
    )
    direction_users = int(
        await session.scalar(
            select(func.count(func.distinct(UserDirection.user_id)))
            .join(User, User.id == UserDirection.user_id)
            .outerjoin(ParticipationLifecycle, ParticipationLifecycle.user_id == User.id)
            .where(*_current_roster_conditions())
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
    event_metrics = {metric.key: metric for metric in (await build_event_analytics(session, now=now)).metrics}
    events_30d = event_metrics['held'].value
    upcoming_14d = await _count(
        session,
        Event,
        Event.event_date >= today,
        Event.event_date <= two_weeks_ahead,
        Event.status.in_(live_event_statuses),
    )
    event_registrations_30d = event_metrics['registrations'].value
    attended_30d = event_metrics['attended'].value
    attendance_rate = event_metrics['attendance'].value
    feedback_count = event_metrics['ratings'].value
    feedback_avg = event_metrics['average'].value
    feedback_rate = event_metrics['feedback_coverage'].value

    active_projects = await _count(
        session,
        Project,
        Project.status.in_(ACTIVE_PROJECT_STATUSES),
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
        ProjectMember.status.in_(["accepted", "active", "completed"]),
        ProjectMember.contribution_status == "confirmed",
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

    point_actions_30d = await _count(
        session,
        PointTransaction,
        PointTransaction.created_at >= month_ago,
        meaningful_points_condition(),
    )
    points_30d = int(
        await session.scalar(
            select(func.coalesce(func.sum(PointTransaction.points), 0)).where(
                PointTransaction.created_at >= month_ago,
                meaningful_points_condition(),
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
        HealthMetric("approved", "Люди", "Текущий состав", approved_total, str(approved_total), "одобрены, не заблокированы, не архивированы и не вышли"),
        HealthMetric("new_7d", "Люди", "Новые за 7 дней", new_7d, f"+{new_7d}", "первое одобрение по аудиту; текущая база, старые записи без истории не восстановлены"),
        HealthMetric("new_30d", "Люди", "Новые за 30 дней", new_30d, f"+{new_30d}", "первое одобрение по аудиту; текущая база, старые записи без истории не восстановлены"),
        HealthMetric("leaders", "Люди", "Лидеров и руководителей", leaders, str(leaders), f"{_pct(leaders, approved_total):.1f}% текущего состава"),
        HealthMetric("activists", "Люди", "Роль «Активист»", activists, str(activists), "организационная роль, а не показатель активной базы"),
        HealthMetric("growth_conversion", "Люди", "Доля активных/управленческих ролей", _pct(progressed, approved_total), f"{_pct(progressed, approved_total):.1f}%", "текущие роли; не историческая конверсия", _cap(_pct(progressed, approved_total)), numerator=progressed, denominator=approved_total, unit="%"),
        HealthMetric("department_coverage", "Люди", "Выбрали департамент", _pct(department_users, approved_total), f"{_pct(department_users, approved_total):.1f}%", "структурная включённость", numerator=department_users, denominator=approved_total, unit="%"),
        HealthMetric("direction_coverage", "Люди", "Выбрали направление", _pct(direction_users, approved_total), f"{_pct(direction_users, approved_total):.1f}%", "предметная включённость", numerator=direction_users, denominator=approved_total, unit="%"),
        HealthMetric("active_7d", "Вовлечённость", "Активность за 7 дней", active_7d, f"{active_7d} · {_pct(active_7d, active_denominator):.1f}%", "только подтверждённые результаты; должности отдельно"),
        HealthMetric("active_30d", "Вовлечённость", "Активность за 30 дней", active_30d, f"{active_30d} · {_pct(active_30d, active_denominator):.1f}%", "цифровая активность не считается реальным действием", _cap(_pct(active_30d, active_denominator))),
        HealthMetric("active_90d", "Вовлечённость", "Активность за 90 дней", active_90d, f"{active_90d} · {_pct(active_90d, active_denominator):.1f}%", "широкий контур реальной активности"),
        HealthMetric("retention_30d", "Вовлечённость", "30-дневное удержание", (_pct(retained_30d, retention_denominator) if retention_denominator else None), (f"{_pct(retained_30d, retention_denominator):.1f}%" if retention_denominator else "Нет данных"), "вернувшиеся из подтверждённо активной когорты предыдущих 30 дней; текущий состав", (_cap(_pct(retained_30d, retention_denominator)) if retention_denominator else None), numerator=retained_30d, denominator=retention_denominator, unit="%"),
        HealthMetric("dormant_30d", "Вовлечённость", "Без активности 30 дней", dormant_30d, str(dormant_30d), "текущие approved участники без blocked/archived и режима «Вышел»"),
        HealthMetric("events_30d", "События", "Мероприятий за 30 дней", events_30d, str(events_30d), "завершённые события за полные локальные дни"),
        HealthMetric("upcoming_14d", "События", "Событий на 14 дней", upcoming_14d, str(upcoming_14d), "запланированный ритм"),
        HealthMetric("event_registrations", "События", "Регистраций за 30 дней", event_registrations_30d, str(event_registrations_30d), "по событиям последнего месяца"),
        HealthMetric("attendance_rate", "События", "Явка", attendance_rate, (f"{attendance_rate:.1f}%" if attendance_rate is not None else "Нет данных"), f"пришли {attended_30d} · зарегистрировано {event_registrations_30d}", (_cap(attendance_rate) if attendance_rate is not None else None), numerator=attended_30d, denominator=event_registrations_30d, unit="%"),
        HealthMetric("feedback", "События", "Оценка мероприятий", feedback_avg, f"{feedback_avg:.1f}/5" if feedback_count else "Нет данных", f"{feedback_count} отзывов", _cap((feedback_avg / 5) * 100) if feedback_count else None, numerator=None, denominator=feedback_count, unit="rating"),
        HealthMetric("feedback_rate", "События", "Охват обратной связью", feedback_rate, (f"{feedback_rate:.1f}%" if feedback_rate is not None else "Нет данных"), "доля посетивших, оставивших отзыв", numerator=event_metrics['feedback_coverage'].numerator, denominator=attended_30d, unit="%"),
        HealthMetric("active_projects", "Проекты", "Действующие проекты", active_projects, str(active_projects), "статусы approved/in_progress; без черновиков и завершённых"),
        HealthMetric("new_projects_30d", "Проекты", "Новых проектов за 30 дней", new_projects_30d, str(new_projects_30d), "новый проектный поток"),
        HealthMetric("completed_projects", "Проекты", "Завершено проектов", completed_projects, str(completed_projects), "накопленный подтверждённый результат"),
        HealthMetric("project_members", "Проекты", "Подтверждённых вкладов", project_members, str(project_members), "учитывается только подтверждённый вклад участника в проект"),
        HealthMetric("open_tasks", "Исполнение", "Открытых заданий", open_tasks, str(open_tasks), "новые, опубликованные, в работе или на проверке"),
        HealthMetric("completed_tasks_30d", "Исполнение", "Заданий завершено за 30 дней", completed_tasks_30d, str(completed_tasks_30d), "реальный операционный выпуск"),
        HealthMetric("overdue_tasks", "Исполнение", "Просроченных заданий", overdue_tasks, str(overdue_tasks), "срок прошёл, задача не закрыта"),
        HealthMetric("task_acceptance", "Исполнение", "Принято результатов заданий", _pct(task_approved_30d, task_submissions_30d), f"{_pct(task_approved_30d, task_submissions_30d):.1f}%", f"{task_approved_30d} из {task_submissions_30d} отправок за 30 дней", numerator=task_approved_30d, denominator=task_submissions_30d, unit="%"),
        HealthMetric("activity_acceptance", "Исполнение", "Принято активностей событий", _pct(activity_approved_30d, activity_submissions_30d), f"{_pct(activity_approved_30d, activity_submissions_30d):.1f}%", f"{activity_approved_30d} из {activity_submissions_30d} отправок за 30 дней", numerator=activity_approved_30d, denominator=activity_submissions_30d, unit="%"),
        HealthMetric("point_actions", "Исполнение", "Подтверждённых реальных действий", point_actions_30d, str(point_actions_30d), f"{points_30d:+d} баллов за подтверждённые реальные действия за 30 дней"),
        HealthMetric("queue", "Операции", "На очереди решений", queues.attention_total, str(queues.attention_total), "заявки, модерация, результаты, вопросы и отчёты"),
        HealthMetric("department_apps", "Операции", "Заявок в департаменты", pending_department_apps, str(pending_department_apps), "ждут решения"),
        HealthMetric("data_rights", "Операции", "Запросов по данным", pending_data_rights, str(pending_data_rights), "запросы на удаление/анонимизацию ждут обработки"),
        HealthMetric("task_delivery", "Операции", "Доставка заданий", _pct(sent_deliveries_30d, delivery_total), f"{_pct(sent_deliveries_30d, delivery_total):.1f}%" if delivery_total else "Нет отправок", f"успешно {sent_deliveries_30d} · ошибок {failed_deliveries_30d}", numerator=sent_deliveries_30d, denominator=delivery_total, unit="%"),
        HealthMetric("broadcasts", "Операции", "Рассылок за 30 дней", broadcasts_30d, str(broadcasts_30d), "отправленные рассылки"),
    ]

    metrics = [replace(item, value=None, display="Нет данных", score=None, data_state="unavailable")
               if item.unit != "count" and not item.denominator else item for item in metrics]

    risks: list[str] = []
    if _pct(active_30d, active_denominator) < 35 and active_denominator:
        risks.append("Низкая активность за 30 дней: нужен быстрый маршрут возвращения людей в реальное действие.")
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
        risks.append("Пульс по «Моему вектору» пока скрыт: нужно минимум 5 безопасно агрегируемых отметок.")
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
            "Активная база и удержание считают только подтверждённые результаты; ответственность учитывается отдельно. "
            "цифровая активность, вход в приложение и сам факт должности или департамента не создают активность. "
            "Текущая база исключает blocked/archived и режим «Вышел». Пульс рассчитывается только "
            "по агрегированным пяти текущим состояниям «Моего вектора» при безопасной выборке от 5 человек; исходные "
            "ответы и личные заметки не используются."
        ),
    )
