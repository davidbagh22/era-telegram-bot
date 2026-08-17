from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Event, EventRegistration, Feedback, PointTransaction, Project, User
from app.utils.constants import ApplicationStatus, EventStatus, ProjectStatus, RegistrationStatus


@dataclass(frozen=True)
class EfficiencyMetric:
    key: str
    label: str
    value: float
    display: str
    score: int | None
    note: str


@dataclass(frozen=True)
class EfficiencyRecommendation:
    priority: str
    title: str
    reason: str
    action: str


@dataclass(frozen=True)
class EfficiencySnapshot:
    score: int
    label: str
    period_label: str
    metrics: list[EfficiencyMetric]
    recommendations: list[EfficiencyRecommendation]
    top_interest: str | None
    top_interest_count: int
    data_note: str


def _cap(value: float) -> int:
    return max(0, min(100, round(value)))


def _score_label(score: int) -> str:
    if score >= 85:
        return "Сильная неделя"
    if score >= 70:
        return "Хороший темп"
    if score >= 50:
        return "Есть рост, но есть резерв"
    return "Нужно усилить активность"


def _top_interest(users: list[User]) -> tuple[str | None, int]:
    counter: Counter[str] = Counter()
    for user in users:
        desired = (user.desired_path or "").strip()
        if desired:
            counter[desired] += 1
        for skill in user.skills or []:
            value = str(skill).strip()
            if value:
                counter[value] += 1
    if not counter:
        return None, 0
    return counter.most_common(1)[0]


async def build_efficiency_snapshot(session: AsyncSession) -> EfficiencySnapshot:
    now = datetime.now(timezone.utc)
    today = date.today()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    month_ago_date = today - timedelta(days=30)
    two_weeks_ahead = today + timedelta(days=14)

    approved_users = list(
        (
            await session.scalars(
                select(User).where(
                    User.is_archived.is_(False),
                    User.application_status == ApplicationStatus.APPROVED,
                )
            )
        ).all()
    )
    approved_total = len(approved_users)

    # Do date filtering in SQL instead of comparing ORM datetime objects in
    # Python. SQLite returns naive datetimes while PostgreSQL can return
    # timezone-aware ones; comparing those directly caused the weekly
    # analytics endpoint to fail in E2E even though the data itself was fine.
    new_users_7d = int(
        await session.scalar(
            select(func.count(User.id)).where(
                User.is_archived.is_(False),
                User.application_status == ApplicationStatus.APPROVED,
                User.created_at >= week_ago,
            )
        )
        or 0
    )

    active_users_30d = int(
        await session.scalar(
            select(func.count(func.distinct(PointTransaction.user_id)))
            .join(User, User.id == PointTransaction.user_id)
            .where(
                PointTransaction.created_at >= month_ago,
                User.is_archived.is_(False),
                User.application_status == ApplicationStatus.APPROVED,
            )
        )
        or 0
    )
    active_rate = (active_users_30d / approved_total * 100) if approved_total else 0.0

    event_live_statuses = (
        EventStatus.APPROVED,
        EventStatus.PUBLISHED,
        EventStatus.REGISTRATION_OPEN,
        EventStatus.REGISTRATION_CLOSED,
        EventStatus.ACTIVE,
        EventStatus.COMPLETED,
        EventStatus.REPORT_SUBMITTED,
    )
    events_30d = int(
        await session.scalar(
            select(func.count(Event.id)).where(
                Event.event_date >= month_ago_date,
                Event.event_date <= today,
                Event.status.in_(event_live_statuses),
            )
        )
        or 0
    )
    upcoming_events_14d = int(
        await session.scalar(
            select(func.count(Event.id)).where(
                Event.event_date >= today,
                Event.event_date <= two_weeks_ahead,
                Event.status.in_(event_live_statuses),
            )
        )
        or 0
    )

    projects_created_30d = int(
        await session.scalar(
            select(func.count(Project.id)).where(
                Project.created_at >= month_ago,
                Project.status != ProjectStatus.CANCELLED,
            )
        )
        or 0
    )
    active_projects = int(
        await session.scalar(
            select(func.count(Project.id)).where(
                Project.status.in_((ProjectStatus.APPROVED, ProjectStatus.IN_PROGRESS))
            )
        )
        or 0
    )

    registrations_30d = int(
        await session.scalar(
            select(func.count(EventRegistration.id)).where(
                EventRegistration.created_at >= month_ago,
                EventRegistration.status.in_(
                    (
                        RegistrationStatus.REGISTERED,
                        RegistrationStatus.WILL_COME,
                        RegistrationStatus.ATTENDED,
                    )
                ),
            )
        )
        or 0
    )

    feedback_count = int(
        await session.scalar(select(func.count(Feedback.id)).where(Feedback.created_at >= month_ago))
        or 0
    )
    feedback_avg = float(
        await session.scalar(select(func.avg(Feedback.rating)).where(Feedback.created_at >= month_ago))
        or 0.0
    )

    # Transparent score: engagement carries 45%, organizational output 35%,
    # participant feedback 20%. If there is no feedback in the period, we do
    # not invent a neutral rating; the two observable components are
    # re-normalized to 100%.
    engagement_score = _cap(active_rate)
    event_output_score = _cap((events_30d / 4) * 100)  # healthy baseline: ~1 live event/week
    project_output_score = _cap((projects_created_30d / 2) * 100)  # healthy baseline: 2 new project starts/month
    output_score = round(event_output_score * 0.65 + project_output_score * 0.35)
    feedback_score = _cap((feedback_avg / 5) * 100) if feedback_count else None

    if feedback_score is None:
        score = _cap(engagement_score * 0.5625 + output_score * 0.4375)
    else:
        score = _cap(engagement_score * 0.45 + output_score * 0.35 + feedback_score * 0.20)

    top_interest, top_interest_count = _top_interest(approved_users)

    metrics = [
        EfficiencyMetric(
            key="engagement",
            label="Вовлечённость",
            value=active_rate,
            display=f"{active_users_30d} из {approved_total}",
            score=engagement_score,
            note="участников проявили подтверждённую активность за 30 дней",
        ),
        EfficiencyMetric(
            key="events",
            label="События",
            value=float(events_30d),
            display=str(events_30d),
            score=event_output_score,
            note=f"за 30 дней · ближайшие 14 дней: {upcoming_events_14d}",
        ),
        EfficiencyMetric(
            key="projects",
            label="Проекты",
            value=float(active_projects),
            display=str(active_projects),
            score=project_output_score,
            note=f"в работе · новых за 30 дней: {projects_created_30d}",
        ),
        EfficiencyMetric(
            key="registrations",
            label="Регистрации",
            value=float(registrations_30d),
            display=str(registrations_30d),
            score=None,
            note="регистраций и подтверждений за 30 дней",
        ),
        EfficiencyMetric(
            key="feedback",
            label="Оценка событий",
            value=feedback_avg,
            display=f"{feedback_avg:.1f}/5" if feedback_count else "Нет данных",
            score=feedback_score,
            note=f"по {feedback_count} отзывам" if feedback_count else "нужно собирать обратную связь после событий",
        ),
        EfficiencyMetric(
            key="growth",
            label="Новые участники",
            value=float(new_users_7d),
            display=f"+{new_users_7d}",
            score=None,
            note="одобрено за последние 7 дней",
        ),
    ]

    recommendations: list[EfficiencyRecommendation] = []
    if active_rate < 35:
        recommendations.append(
            EfficiencyRecommendation(
                priority="high",
                title="Вернуть людей в действие",
                reason=f"За 30 дней активность проявили только {active_users_30d} из {approved_total} участников.",
                action="Запустите на этой неделе одну короткую задачу, опрос или открытый набор в проект с понятным результатом за 3–7 дней.",
            )
        )
    elif active_rate < 60:
        recommendations.append(
            EfficiencyRecommendation(
                priority="medium",
                title="Усилить вовлечённость",
                reason=f"Активны {active_rate:.0f}% одобренных участников.",
                action="Дайте 2 конкретные точки входа: одно событие и одну задачу/роль в проекте, а затем адресно напомните неактивным участникам.",
            )
        )

    if upcoming_events_14d == 0:
        recommendations.append(
            EfficiencyRecommendation(
                priority="high",
                title="Пустое окно событий",
                reason="На ближайшие 14 дней нет живых мероприятий в системе.",
                action="Поставьте минимум одно событие на ближайшие две недели и откройте регистрацию заранее.",
            )
        )
    elif events_30d < 3:
        recommendations.append(
            EfficiencyRecommendation(
                priority="medium",
                title="Добавить ритм событий",
                reason=f"За 30 дней в системе зафиксировано {events_30d} живых мероприятий.",
                action="Добавьте ещё 1–2 компактных формата: мастер-класс, интерактив или клубную встречу.",
            )
        )

    if active_projects == 0:
        recommendations.append(
            EfficiencyRecommendation(
                priority="high",
                title="Нет проектов в работе",
                reason="Сейчас нет проектов со статусом «Одобрен» или «В работе».",
                action="Выберите один сильный проект из очереди, назначьте следующий этап, команду и ближайшую задачу.",
            )
        )
    elif projects_created_30d == 0:
        recommendations.append(
            EfficiencyRecommendation(
                priority="medium",
                title="Нужен новый проектный импульс",
                reason="За последние 30 дней не появилось новых проектных инициатив.",
                action="Проведите короткий сбор идей и доведите хотя бы одну до черновика проекта в приложении.",
            )
        )

    if feedback_count >= 3 and feedback_avg < 4:
        recommendations.append(
            EfficiencyRecommendation(
                priority="medium",
                title="Разобрать обратную связь",
                reason=f"Средняя оценка событий за 30 дней — {feedback_avg:.1f}/5.",
                action="Откройте отзывы по последним мероприятиям и исправьте один повторяющийся сценарий уже в следующем событии.",
            )
        )

    if top_interest and top_interest_count >= 3:
        recommendations.append(
            EfficiencyRecommendation(
                priority="opportunity",
                title=f"Есть явный интерес: {top_interest}",
                reason=f"Эта тема встречается в профилях участников {top_interest_count} раз.",
                action=f"Сделайте на этой неделе один контентный материал, встречу или мини-проект по теме «{top_interest}» и измерьте отклик.",
            )
        )

    if new_users_7d >= 5:
        recommendations.append(
            EfficiencyRecommendation(
                priority="opportunity",
                title="Новая волна участников",
                reason=f"За 7 дней одобрено {new_users_7d} новых участников.",
                action="Соберите для них один быстрый маршрут: событие → небольшая задача → знакомство с проектом, чтобы не потерять первую неделю вовлечения.",
            )
        )

    if not recommendations:
        recommendations.append(
            EfficiencyRecommendation(
                priority="opportunity",
                title="Темп стабильный — пора масштабировать",
                reason="Критических провалов по доступным данным не видно.",
                action="Сохраните текущий ритм и на этой неделе протестируйте один новый формат, затем сравните регистрацию, активность и отзывы.",
            )
        )

    return EfficiencySnapshot(
        score=score,
        label=_score_label(score),
        period_label="обновляется по данным последних 7/30 дней",
        metrics=metrics,
        recommendations=recommendations[:5],
        top_interest=top_interest,
        top_interest_count=top_interest_count,
        data_note="Показатель считается только по данным, которые реально есть в ЭРА: активности, событиям, проектам, регистрациям и отзывам.",
    )
