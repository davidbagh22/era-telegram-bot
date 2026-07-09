from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Badge, User, UserBadge
from app.keyboards.participant import points_hub_keyboard, profile_sections_keyboard
from app.repositories.users import user_stats
from app.utils import texts, ux_texts
from app.utils.constants import ApplicationStatus

router = Router(name="cabinet_hubs")


async def _guard(call: CallbackQuery, user: User | None) -> bool:
    await call.answer()
    if user is None or user.application_status != ApplicationStatus.APPROVED:
        await call.message.answer(texts.APPLICATION_PENDING)
        return False
    if user.is_blocked or user.is_archived:
        await call.message.answer(texts.BLOCKED)
        return False
    return True


@router.callback_query(F.data == "cabinet:profile")
async def profile_home(
    call: CallbackQuery,
    user: User | None,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if not await _guard(call, user):
        return
    stats = await user_stats(session, user.id)
    badges = (
        await session.scalars(
            select(Badge)
            .join(UserBadge, UserBadge.badge_id == Badge.id)
            .where(UserBadge.user_id == user.id)
            .order_by(Badge.name)
        )
    ).all()
    badge_lines = (
        "\n".join(f"• {badge.name}" for badge in badges)
        if badges
        else "Пока нет знаков — они появятся за вклад, ответственность и результат."
    )
    body = (
        f"{texts.profile_text(user, stats)}"
        f"{ux_texts.profile_empty_hint(user)}\n\n"
        f"🏅 Знаки\n{badge_lines}\n\n"
        "Портфолио, мероприятия, проекты, направления и задачи — кнопками ниже."
    )
    await call.message.answer(
        body,
        reply_markup=profile_sections_keyboard(
            settings.internal_department_chat_url,
            settings.external_department_chat_url,
        ),
    )


@router.callback_query(F.data == "cabinet:points_hub")
async def points_hub(call: CallbackQuery, user: User | None) -> None:
    if not await _guard(call, user):
        return
    await call.message.answer(
        "🏆 Баллы и достижения\n\nБаланс, история операций, знаки и место в рейтинге — здесь.",
        reply_markup=points_hub_keyboard(),
    )
