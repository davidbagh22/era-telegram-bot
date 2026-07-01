from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import User
from app.handlers.participant.cabinet import _send_journey
from app.handlers.participant.events import _send_event_list
from app.handlers.participant.projects import _send_projects_menu
from app.keyboards.admin import admin_panel_keyboard
from app.keyboards.leader import leader_panel_keyboard
from app.keyboards.participant import contact_keyboard, main_inline_keyboard, team_keyboard
from app.repositories.users import rating, user_stats
from app.services.points_service import total_points
from app.utils import texts
from app.utils.constants import ApplicationStatus, PRIVILEGED_ROLES, Role

router = Router(name="participant_navigation")


def _approved(user: User | None) -> bool:
    return bool(
        user
        and user.application_status == ApplicationStatus.APPROVED
        and not user.is_blocked
        and not user.is_archived
    )


def _has_admin_access(user: User | None) -> bool:
    if not user:
        return False
    if user.role == Role.ADMIN:
        return True
    return any(
        grant.is_active
        for grant in (getattr(user, "permission_grants", None) or [])
    )


async def _send_main_menu(message: Message, user: User | None) -> None:
    if not _approved(user):
        await message.answer(texts.APPLICATION_PENDING)
        return
    admin = _has_admin_access(user)
    privileged = user.role in PRIVILEGED_ROLES
    await message.answer(
        "Главное меню ЭРА",
        reply_markup=main_inline_keyboard(privileged=privileged, admin=admin),
    )


@router.message(F.text == "👤 Личный кабинет")
async def personal_cabinet_button(
    message: Message,
    user: User | None,
    session: AsyncSession,
    settings: Settings,
    state: FSMContext,
) -> None:
    await state.clear()
    if not _approved(user):
        await message.answer(texts.APPLICATION_PENDING)
        return
    await _send_journey(message, user, session, settings)


@router.message(F.text == "📅 Афиша")
async def schedule_button(
    message: Message, user: User | None, session: AsyncSession, state: FSMContext
) -> None:
    await state.clear()
    await _send_event_list(message, user, session)


@router.message(F.text == "⭐ Возможности")
async def opportunities_button(
    message: Message, user: User | None, session: AsyncSession, state: FSMContext
) -> None:
    await state.clear()
    if not _approved(user):
        await message.answer(texts.APPLICATION_PENDING)
        return
    balance = await total_points(session, user.id)
    await message.answer(
        f"⭐ Возможности\n\nВаш баланс: {balance} баллов\n\n"
        "Здесь будут доступны каталог возможностей, аукционы, награды и специальные форматы ЭРА.",
        reply_markup=main_inline_keyboard(privileged=user.role in PRIVILEGED_ROLES, admin=_has_admin_access(user)),
    )
    # Открываем текущий рабочий раздел возможностей отдельным сообщением через callback-кнопку
    await message.answer("Откройте раздел:", reply_markup=contact_keyboard().model_copy(update={"inline_keyboard": [[contact_keyboard().inline_keyboard[0][0]]]}))


@router.message(F.text == "💬 Связь")
async def contact_button(
    message: Message, user: User | None, state: FSMContext
) -> None:
    await state.clear()
    if not _approved(user):
        await message.answer(texts.APPLICATION_PENDING)
        return
    await message.answer(
        "💬 Связь\n\nЗдесь можно задать вопрос, найти команду ЭРА, открыть правила или информацию о боте.",
        reply_markup=contact_keyboard(),
    )


@router.callback_query(F.data == "contact:menu")
async def contact_callback(call: CallbackQuery, user: User | None) -> None:
    await call.answer()
    if not _approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    await call.message.answer(
        "💬 Связь\n\nВыберите, что Вам нужно.", reply_markup=contact_keyboard()
    )


@router.callback_query(F.data == "team:menu")
async def team_callback(call: CallbackQuery, user: User | None, settings: Settings) -> None:
    await call.answer()
    if not _approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    await call.message.answer(
        "👥 Команда ЭРА\n\nДепартаменты, контакты, руководители направлений и чаты.",
        reply_markup=team_keyboard(settings.general_chat_url),
    )


@router.callback_query(F.data == "rules:open")
async def rules_callback(call: CallbackQuery) -> None:
    await call.answer()
    await call.message.answer(texts.CHAT_RULES, reply_markup=contact_keyboard())


@router.message(F.text == "⚙️ Панель")
async def panel_button(
    message: Message, user: User | None, state: FSMContext
) -> None:
    await state.clear()
    if not _approved(user):
        await message.answer(texts.NO_ACCESS)
        return
    if _has_admin_access(user):
        await message.answer(texts.ADMIN_PANEL, reply_markup=admin_panel_keyboard())
        return
    if user.role in PRIVILEGED_ROLES:
        await message.answer(texts.LEADER_PANEL, reply_markup=leader_panel_keyboard())
        return
    await message.answer(texts.NO_ACCESS)


@router.callback_query(F.data == "panel:open")
async def panel_callback(call: CallbackQuery, user: User | None) -> None:
    await call.answer()
    if not _approved(user):
        await call.message.answer(texts.NO_ACCESS)
        return
    if _has_admin_access(user):
        await call.message.answer(texts.ADMIN_PANEL, reply_markup=admin_panel_keyboard())
        return
    if user.role in PRIVILEGED_ROLES:
        await call.message.answer(texts.LEADER_PANEL, reply_markup=leader_panel_keyboard())
        return
    await call.message.answer(texts.NO_ACCESS)


@router.message(F.text == "🧭 Главное меню")
@router.callback_query(F.data == "menu:main")
async def main_menu_entry(event, user: User | None, state: FSMContext) -> None:
    if isinstance(event, CallbackQuery):
        await event.answer()
        message = event.message
    else:
        message = event
    await state.clear()
    await _send_main_menu(message, user)
