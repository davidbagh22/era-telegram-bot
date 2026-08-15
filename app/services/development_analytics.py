from __future__ import annotations

from collections import Counter
from statistics import mean
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.development_models import (
    AdminVisibilitySetting,
    MonthlyCheckin,
    MonthlyContext,
    UserVectorProfile,
)
from app.database.models import User
from app.services import development_service as dev
from app.utils.constants import ApplicationStatus

MINIMUM_COHORT = 5
RIASEC_LABELS = {
    "R": "Практическое",
    "I": "Исследование",
    "A": "Творчество",
    "S": "Люди и коммуникация",
    "E": "Инициативы и влияние",
    "C": "Организация и структура",
}


async def community_analytics(session: AsyncSession, period_days: int = 30) -> dict[str, Any]:
    """Return development analytics without exposing individual sensitive rows.

    Only users who explicitly keep their development summary visible are
    included. Interests additionally respect the separate interests flag.
    Cohorts below MINIMUM_COHORT are suppressed before any distribution is
    calculated so an admin cannot infer a person's answers from a tiny group.
    """
    days = max(1, min(period_days, 365))
    cutoff = dev.utcnow() - dev.timedelta(days=days)

    participant_count = int(
        (
            await session.scalar(
                select(func.count())
                .select_from(User)
                .where(
                    User.application_status == ApplicationStatus.APPROVED,
                    User.is_archived.is_(False),
                    User.is_blocked.is_(False),
                )
            )
        )
        or 0
    )

    visible_rows = list(
        (
            await session.scalars(
                select(AdminVisibilitySetting).where(AdminVisibilitySetting.summary_visible.is_(True))
            )
        ).all()
    )
    visibility = {row.user_id: row for row in visible_rows}
    if not visibility:
        return _suppressed(participant_count, 0)

    completed = list(
        (
            await session.scalars(
                select(MonthlyCheckin).where(
                    MonthlyCheckin.status == "completed",
                    MonthlyCheckin.completed_at >= cutoff,
                    MonthlyCheckin.user_id.in_(visibility.keys()),
                )
            )
        ).all()
    )

    latest_by_user: dict[int, MonthlyCheckin] = {}
    for row in sorted(completed, key=lambda item: item.completed_at or dev.utcnow(), reverse=True):
        latest_by_user.setdefault(row.user_id, row)
    sample = list(latest_by_user.values())
    n = len(sample)
    coverage = round((n / participant_count) * 100) if participant_count else 0
    if n < MINIMUM_COHORT:
        return _suppressed(participant_count, n, coverage)

    state = {
        code: round(mean(int(row.state_json.get(code, 0)) for row in sample))
        for code in dev.STATE_DIMENSIONS
    }
    delta: dict[str, int] = {}
    for code in dev.STATE_DIMENSIONS:
        values = [int(row.delta_json[code]) for row in sample if code in (row.delta_json or {})]
        if values:
            delta[code] = round(mean(values))

    checkin_ids = [row.id for row in sample]
    contexts = list(
        (
            await session.scalars(
                select(MonthlyContext).where(MonthlyContext.checkin_id.in_(checkin_ids))
            )
        ).all()
    )
    wants_counter: Counter[str] = Counter()
    for context in contexts:
        wants_counter.update(set(context.development_wants_json or []))

    user_ids = [row.user_id for row in sample]
    profiles = list(
        (
            await session.scalars(
                select(UserVectorProfile).where(UserVectorProfile.user_id.in_(user_ids))
            )
        ).all()
    )
    interests_counter: Counter[str] = Counter()
    interest_denominator = 0
    for profile in profiles:
        visible = visibility.get(profile.user_id)
        if visible is None or not visible.interests_visible:
            continue
        top_code = (profile.interests_json or {}).get("top_code")
        if not isinstance(top_code, list) or not top_code:
            continue
        interest_denominator += 1
        interests_counter.update(set(str(code) for code in top_code[:3]))

    wants = [
        {"key": key, "count": count, "percent": round((count / n) * 100)}
        for key, count in wants_counter.most_common()
    ]
    interests = [
        {
            "key": RIASEC_LABELS.get(key, key),
            "count": count,
            "percent": round((count / interest_denominator) * 100) if interest_denominator else 0,
        }
        for key, count in interests_counter.most_common()
    ]

    return {
        "sample_size": n,
        "eligible_profiles": participant_count,
        "coverage_percent": coverage,
        "minimum_cohort": MINIMUM_COHORT,
        "suppressed": False,
        "period_days": days,
        "state": state,
        "delta": delta,
        "index": dev.vector_index(state),
        "development_wants": wants,
        "interests": interests,
        "recommendation": _organization_recommendation(state, delta, wants),
        "disclaimer": (
            "Агрегат добровольных Check-in с учётом настроек приватности. "
            "Не используется для психологического рейтинга, автоматического отбора "
            "или назначения ролей."
        ),
    }


def _suppressed(participant_count: int, sample_size: int, coverage: int | None = None) -> dict[str, Any]:
    if coverage is None:
        coverage = round((sample_size / participant_count) * 100) if participant_count else 0
    return {
        "sample_size": sample_size,
        "eligible_profiles": participant_count,
        "coverage_percent": coverage,
        "minimum_cohort": MINIMUM_COHORT,
        "suppressed": True,
        "state": None,
        "message": "Недостаточно ответов для безопасной групповой аналитики.",
    }


def _organization_recommendation(
    state: dict[str, int],
    delta: dict[str, int],
    wants: list[dict[str, Any]],
) -> str:
    top_want = wants[0]["key"] if wants else None
    energy_delta = delta.get("energy", 0)
    if state["energy"] < 50 or energy_delta <= -10:
        return (
            "Энергия сообщества сейчас уязвимее остальных областей. Не стоит наращивать "
            "обязательную нагрузку: полезнее добавить лёгкий формат общения, восстановления "
            "или короткую активность без длинных обязательств."
        )
    if state["agency"] < 55 and top_want in {"собственные проекты", "лидерство", "самостоятельность"}:
        return (
            "Интерес к собственной инициативе есть, но ощущение опоры ниже остальных областей. "
            "Лучше дать короткий практический формат, где за один вечер человек проходит путь "
            "от идеи до первого маленького результата."
        )
    if top_want:
        return (
            f"Самый частый выбранный вектор развития сейчас — «{top_want}». "
            "Планируя следующий формат, лучше дать возможность попробовать это на практике, "
            "а не только послушать теорию."
        )
    weakest = min(dev.STATE_DIMENSIONS, key=lambda code: state[code])
    return (
        f"Самая уязвимая область общего снимка сейчас — «{dev.STATE_LABELS[weakest]}». "
        "Следующий формат стоит проверить на то, помогает ли он этой потребности, а не создаёт дополнительную нагрузку."
    )
