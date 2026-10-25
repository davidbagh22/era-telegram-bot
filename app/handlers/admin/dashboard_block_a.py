from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import User
from app.keyboards.admin import admin_home_keyboard
from app.services.application_review_service import application_review_version
from app.services.admin_dashboard_service import has_dashboard_access
from app.services.admin_user_card import send_admin_user_card
from app.utils import texts
from app.utils.constants import ApplicationStatus

router = Router(name="admin_dashboard_block_a")
applications_router = Router(name="delegated_applications_queue")
PAGE_SIZE = 8


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
            User.application_status.in_([ApplicationStatus.PENDING, ApplicationStatus.NEEDS_INFO]),
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
    session: AsyncSession | None = None,
) -> None:
    if not await _guard(message, user, settings):
        return
    await state.clear()
    await message.answer(
        "⚙️ <b>Управление ЭРА</b>\n\n"
        "Сводка, заявки и основные действия доступны прямо здесь.\n"
        "Выберите раздел или откройте приложение ЭРА.",
        parse_mode="HTML", reply_markup=admin_home_keyboard(settings.effective_miniapp_url),
    )


async def _show_application_list(message: Message, session: AsyncSession, *, page: int = 0, edit: bool = False, can_summary: bool = True) -> None:
    conditions = (
        User.application_status.in_([ApplicationStatus.PENDING, ApplicationStatus.NEEDS_INFO]),
        User.is_archived.is_not(True),
    )
    total = int(await session.scalar(select(func.count()).select_from(User).where(*conditions)) or 0)
    page = min(max(0, page), max(0, (total - 1) // PAGE_SIZE))
    pending = list((await session.scalars(select(User).where(*conditions)
        .order_by(User.created_at, User.id).offset(page * PAGE_SIZE).limit(PAGE_SIZE))).all())
    rows = [[InlineKeyboardButton(
        text=("💬 " if target.application_status == ApplicationStatus.NEEDS_INFO else "📝 ")
             + f"#{target.id} · {target.first_name} {target.last_name or ''}"[:52],
        callback_data=f"admin:application:{target.id}",
    )] for target in pending]
    navigation = []
    if page:
        navigation.append(InlineKeyboardButton(text="← Назад", callback_data=f"admin:applications:page:{page-1}"))
    if (page + 1) * PAGE_SIZE < total:
        navigation.append(InlineKeyboardButton(text="Далее →", callback_data=f"admin:applications:page:{page+1}"))
    if navigation:
        rows.append(navigation)
    rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data=f"admin:applications:page:{page}")])
    if can_summary:
        rows[-1].append(InlineKeyboardButton(text="📊 Сводка", callback_data="admin:management:open"))
    rows.append([InlineKeyboardButton(text="← Рабочие разделы", callback_data="staff:home")])
    text = (f"📥 <b>Заявки ЭРА · {total}</b>\n\n"
            + (f"Страница {page+1} из {(total+PAGE_SIZE-1)//PAGE_SIZE}. Сначала самые ранние заявки.\n"
               "📝 Ожидает решения · 💬 Запрошено уточнение\n\nВыберите человека, чтобы открыть анкету и принять решение."
               if pending else "✅ Заявок на рассмотрении нет."))
    markup = InlineKeyboardMarkup(inline_keyboard=rows)
    if edit:
        from aiogram.exceptions import TelegramBadRequest
        try:
            await message.edit_text(text, parse_mode="HTML", reply_markup=markup)
            return
        except TelegramBadRequest as exc:
            if "not modified" in str(exc).lower():
                return
            # A removed/old menu should not make the queue inaccessible.
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


@applications_router.message(Command("applications"))
@applications_router.message(Command("applications_review"))
@applications_router.message(F.text == "📥 Заявки")
async def applications_queue(
    message: Message,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _application_guard(message, user, settings, session):
        return
    await _show_application_list(message, session, can_summary=has_dashboard_access(user,settings,message.from_user.id))


@applications_router.callback_query(F.data == "admin:applications")
@applications_router.callback_query(F.data.regexp(r"^admin:applications:page:\d{1,6}$"))
async def applications_callback(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _application_guard(call, user, settings, session):
        return
    page = int(call.data.rsplit(":", 1)[-1]) if ":page:" in call.data else 0
    await _show_application_list(call.message, session, page=page, edit=":page:" in call.data,
                                 can_summary=has_dashboard_access(user,settings,call.from_user.id))


@applications_router.callback_query(F.data.regexp(r"^admin:application:\d+$"))
async def application_detail(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _application_guard(call, user, settings, session):
        return
    target = await session.get(User, int(call.data.rsplit(":", 1)[-1]))
    if target is None or target.is_archived:
        await call.message.answer("Эта заявка недоступна. Обновите список заявок.")
        return
    if (not has_dashboard_access(user,settings,call.from_user.id) and target.application_status not in
            {ApplicationStatus.PENDING, ApplicationStatus.NEEDS_INFO}):
        await call.message.answer("Эта заявка уже рассмотрена. Обновите очередь.")
        return
    revision = await application_review_version(session, target.id)
    await send_admin_user_card(call.message, session, target, mode="application", review_version=revision)


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
    await call.message.answer("⚙️ Управление ЭРА\n\nВыберите нужный раздел.",
                              reply_markup=admin_home_keyboard(settings.effective_miniapp_url))


# Both surfaces share services and permissions; Telegram owns these native actions.


async def _application_guard(event, user, settings, session):
    from app.services.staff_access_service import can_operate_queue
    if isinstance(event, CallbackQuery):
        await event.answer()
        message = event.message
    else:
        message = event
    if not await can_operate_queue(session, user, settings, "applications.review", telegram_id=event.from_user.id):
        await message.answer(texts.NO_ACCESS)
        return False
    return True
