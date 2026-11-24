from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Badge, PortfolioItem, User, UserBadge
from app.keyboards.common import back_keyboard
from app.keyboards.participant import portfolio_keyboard
from app.repositories.users import user_stats
from app.services.notification_service import safe_answer_media
from app.services.points_service import total_points
from app.utils import texts
from app.utils.constants import ApplicationStatus, ROLE_LABELS, STATUS_LABELS
from app.utils.telegram import send_long_text

router = Router(name="participant_achievements_block4")


def approved(user: User | None) -> bool:
    return bool(user and user.application_status == ApplicationStatus.APPROVED and not user.is_blocked and not user.is_archived)


async def badges_for_user(session: AsyncSession, user_id: int) -> list[Badge]:
    return (await session.scalars(select(Badge).join(UserBadge, UserBadge.badge_id == Badge.id).where(UserBadge.user_id == user_id).order_by(Badge.name))).all()


def achievements_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⭐ Баллы", callback_data="cabinet:points"),
            InlineKeyboardButton(text="🏆 Рейтинг", callback_data="cabinet:rating"),
        ],
        [InlineKeyboardButton(text="🎓 Портфолио", callback_data="cabinet:portfolio")],
        [InlineKeyboardButton(text="← Личный кабинет", callback_data="cabinet:open")],
    ])


@router.callback_query(F.data.in_({"cabinet:achievements", "cabinet:badges", "badges:menu"}))
async def achievements(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    """Знаки и сводка вклада. Баллы/история — отдельный cabinet:points."""
    await call.answer()
    if not approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    stats = await user_stats(session, user.id)
    balance = await total_points(session, user.id)
    badges = await badges_for_user(session, user.id)
    badge_lines = "\n".join(f"• {badge.name} — {badge.description or 'знак ЭРА'}" for badge in badges) or "Пока нет знаков. Они появятся за вклад и результат."
    body = (
        "🏅 Знаки ЭРА\n\n"
        f"Роль: {ROLE_LABELS.get(user.role, user.role)}\n"
        f"Статус: {STATUS_LABELS.get(user.participation_status, user.participation_status)}\n\n"
        f"⭐ Баллы: {balance} · 🏅 знаков: {len(badges)}\n"
        f"📅 {stats.get('events', 0)} · ✅ {stats.get('tasks', 0)} · 💡 {stats.get('projects', 0)} · 🎓 {stats.get('portfolio', 0)}\n\n"
        f"{badge_lines}"
    )
    await send_long_text(call.message, body, reply_markup=achievements_keyboard())


@router.callback_query(F.data == "portfolio:view")
async def portfolio_view(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    await call.answer()
    if not approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    items = (await session.scalars(select(PortfolioItem).where(PortfolioItem.user_id == user.id, PortfolioItem.status.in_(["verified", "pending"])).order_by(desc(PortfolioItem.created_at)))).all()
    if not items:
        await call.message.answer(texts.PORTFOLIO_EMPTY, reply_markup=portfolio_keyboard())
        return
    rows = [[InlineKeyboardButton(text=f"👁 {item.title[:36]}", callback_data=f"portfolio:item:{item.id}")] for item in items]
    rows.append([InlineKeyboardButton(text="← Портфолио", callback_data="cabinet:portfolio")])
    lines = "\n".join(f"• {item.title} — {'на проверке' if item.status == 'pending' else 'подтверждено'}" for item in items)
    await call.message.answer(f"👁 Просмотр портфолио\n\n{lines}\n\nВыберите запись, чтобы открыть её внутри бота.", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("portfolio:item:"))
async def portfolio_item(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    await call.answer()
    if not approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    item = await session.get(PortfolioItem, int(call.data.rsplit(":", 1)[-1]))
    if item is None or item.user_id != user.id:
        await call.message.answer("Запись портфолио недоступна")
        return
    status = "на проверке" if item.status == "pending" else "подтверждено"
    body = (
        f"🎓 {item.title}\n\n"
        f"Тип: {item.item_type}\n"
        f"Статус: {status}\n"
        f"Описание:\n{item.description or 'без описания'}"
    )
    if item.url:
        body += f"\n\nСсылка: {item.url}"
    await call.message.answer(body, reply_markup=back_keyboard("portfolio:view"))
    if item.file_id:
        if not await safe_answer_media(call.message, item.file_id, caption="Материал портфолио"):
            await call.message.answer("Файл прикреплён, но Telegram не дал открыть его повторно.")
