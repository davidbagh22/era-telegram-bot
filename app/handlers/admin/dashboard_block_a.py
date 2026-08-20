from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import User
from app.keyboards.participant import open_app_button
from app.services.admin_dashboard_service import has_dashboard_access
from app.services.admin_user_card import send_admin_user_card
from app.utils import texts
from app.utils.constants import ApplicationStatus

router = Router(name="admin_dashboard_block_a")


async def _guard(event: Message | CallbackQuery, user: User | None, settings: Settings) -> bool:
    if isinstance(event, CallbackQuery):
        await event.answer()
        message = event.message
        telegram_id = event.from_user.id
    else:
        message = event
        telegram_id = event.from_user.id
    if not has_dashboard_access(user, settings, telegram_id):
        await message.answer(texts.NO_ACCESS)
        return False
    return True


async def _pending_applications(session: AsyncSession, *, limit: int = 26) -> list[User]:
    rows = await session.scalars(
        select(User)
        .where(
            User.application_status.in_(
                [ApplicationStatus.PENDING, ApplicationStatus.NEEDS_INFO]
            ),
            # Older rows can contain NULL. Only explicit True means archived;
            # pending registrations must never silently disappear from review.
            User.is_archived.is_not(True),
        )
        .order_by(User.created_at.desc(), User.id.desc())
        .limit(limit)
    )
    return list(rows.all())


@router.message(Command("admin"))
@router.message(F.text == "⚙️ Управление")
async def admin_dashboard(
    message: Message,
    user: User | None,
    settings: Settings,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    # The Mini App remains the primary admin surface, but the bot must make
    # pending registrations visible even if a Telegram notification was lost.
    if not await _guard(message, user, settings):
        return
    await state.clear()
    pending = await _pending_applications(session, limit=26)
    count = len(pending)
    if count:
        visible_count = min(count, 25)
        suffix = "+" if count > 25 else ""
        await message.answer(
            f"📥 Заявки на рассмотрении: {visible_count}{suffix}.\n"
            "Команда /applications покажет карточки прямо в боте."
        )
    await message.answer(
        texts.ADMIN_PANEL_MOVED,
        reply_markup=open_app_button(settings.effective_miniapp_url),
    )


@router.message(Command("applications"))
async def applications_queue(
    message: Message,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    """Recover pending registrations directly from the database.

    Telegram notifications are delivery hints, not the source of truth. This
    command makes every active pending/needs-info registration reviewable even
    when its original notification was missed.
    """
    if not await _guard(message, user, settings):
        return

    pending = await _pending_applications(session, limit=26)
    if not pending:
        await message.answer("✅ Новых заявок на рассмотрении нет.")
        return

    has_more = len(pending) > 25
    visible = pending[:25]
    await message.answer(
        f"📥 Заявок на рассмотрении: {len(visible)}"
        + ("+" if has_more else "")
        + ". Показываю последние прямо из базы."
    )
    delivered = 0
    for target in visible:
        try:
            await send_admin_user_card(message, session, target, mode="application")
            delivered += 1
        except Exception:
            # One malformed/undeliverable card must not hide the rest of the
            # queue. Do not include personal data in the fallback message.
            await message.answer(f"⚠️ Не удалось показать заявку #{target.id}.")

    if delivered < len(visible):
        await message.answer(
            f"Показано карточек: {delivered} из {len(visible)}. "
            "Остальные остаются в очереди и не потеряны."
        )
    if has_more:
        await message.answer(
            "В очереди есть ещё заявки. Полный список доступен в Admin Mode."
        )


@router.callback_query(F.data == "admin:panel")
async def admin_dashboard_callback(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not await _guard(call, user, settings):
        return
    await state.clear()
    await call.message.answer(
        texts.ADMIN_PANEL_MOVED,
        reply_markup=open_app_button(settings.effective_miniapp_url),
    )


# admin:attention (the "🧭 Что где ждёт" breakdown) was only reachable from
# the removed dashboard menu keyboard below — it has no other entry point
# (verified: `rg '"admin:attention"'` across app/ only ever matched this
# router's own decorator), so it's been dropped rather than left orphaned.
# The Mini App's AdminOverviewScreen already covers this with clickable
# "Требует внимания" items that navigate straight to the object.
