from aiogram import F, Bot, Router
from aiogram.filters import Command, CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Event, EventActivity, EventRegistration, Task, User
from app.handlers.faq_start import try_handle_faq_payload
from app.handlers.participant.event_activities_block15 import (
    ACTIVE_REGISTRATION_STATUSES,
    ALLOWED_PROOF_TYPES,
    ActivityProofStates,
)
from app.handlers.participant.event_activities_block15 import (
    _notify_proof as notify_activity_proof,
)
from app.handlers.participant.navigation import (
    _approved,
    _has_admin_access,
    _send_event_list,
    _send_main_menu,
    _send_personal_cabinet,
)
from app.keyboards.common import registration_keyboard, subscription_keyboard
from app.keyboards.participant import contact_keyboard, open_app_button, project_menu_keyboard
from app.services import event_activity_service, task_service
from app.services.points_service import total_points
from app.services.subscription_service import SubscriptionCheckError, is_channel_member
from app.states.growth import TaskSubmissionStates
from app.utils import texts
from app.utils.constants import PRIVILEGED_ROLES
from app.utils.deep_links import parse_activity_submit_payload, parse_task_submit_payload

router = Router(name="emergency")

MENU_BUTTONS = {
    "👤 Личный кабинет",
    "📅 Афиша",
    "💡 Проекты",
    "⭐ Возможности",
    "💬 Связь",
    "⚙️ Панель",
    "🧭 Главное меню",
}
CANCEL_TEXTS = {"Отмена", "отмена", "❌ Отмена", "Отменить", "отменить"}


async def _subscription_ok(
    bot: Bot, telegram_id: int, settings: Settings
) -> bool | None:
    try:
        return await is_channel_member(bot, telegram_id, settings)
    except SubscriptionCheckError:
        return None


@router.message(CommandStart(), F.chat.type != "private")
async def group_start(message: Message, bot: Bot, state: FSMContext) -> None:
    await state.clear()
    me = await bot.get_me()
    await message.answer(
        "Регистрация проходит в личном чате с ботом. Откройте бот и нажмите Start.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(
                    text="Открыть бот",
                    url=f"https://t.me/{me.username}?start=registration",
                )
            ]]
        ),
    )


async def _try_start_task_submission_from_deep_link(
    message: Message,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    command: CommandObject | None,
) -> bool:
    """Mini App "Отправить результат" hands off here (section 15 of the
    platform brief) — uploads stay a Bot-only FSM. Returns True if the
    deep link was valid and the submission prompt was sent.

    Lives here (not app/handlers/start.py) because emergency.router is
    included first in the dispatcher (app/bot.py) and rescue_start's
    StateFilter("*") matches any FSM state, so it — not start.py's start()
    — is what a real "/start task_submit_<id>" deep link actually reaches.
    """
    if command is None or not command.args:
        return False
    task_id = parse_task_submit_payload(command.args)
    if task_id is None:
        return False
    task = await session.get(Task, task_id)
    if (
        task is None
        or task.status in task_service.ARCHIVE_STATUSES
        or not await task_service.can_submit(session, task, user)
    ):
        return False
    await state.set_state(TaskSubmissionStates.result)
    await state.update_data(task_id=task.id)
    await message.answer(
        f"Отправьте результат по задаче «{task.title}» текстом, фотографией, видео или файлом"
    )
    return True


async def _try_start_activity_submission_from_deep_link(
    message: Message,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    settings: Settings,
    command: CommandObject | None,
) -> bool:
    """Mini App's Event Activities screen hands off here the same way
    task submission does above — uploads stay a Bot-only FSM."""
    if command is None or not command.args:
        return False
    activity_id = parse_activity_submit_payload(command.args)
    if activity_id is None:
        return False
    activity = await session.get(EventActivity, activity_id)
    if activity is None or not activity.is_active:
        return False
    registration = await session.scalar(
        select(EventRegistration).where(
            EventRegistration.event_id == activity.event_id,
            EventRegistration.user_id == user.id,
            EventRegistration.status.in_(ACTIVE_REGISTRATION_STATUSES),
        )
    )
    if registration is None:
        return False
    existing = await event_activity_service.get_submission(session, activity.id, user.id)
    if existing and existing.status == "approved":
        await message.answer("Эта активность уже принята. Повторная отправка закрыта.")
        return True
    if existing and existing.status == "pending":
        await message.answer("Ваш результат уже на проверке.")
        return True
    proof_type = activity.submission_type if activity.submission_type in ALLOWED_PROOF_TYPES else "text"
    if proof_type == "manual":
        submission = await event_activity_service.submit_manual(session, activity, user)
        event = await session.get(Event, activity.event_id)
        await notify_activity_proof(bot, settings, submission, activity, event, user)
        await message.answer("Заявка отправлена на проверку.")
        return True
    await state.set_state(ActivityProofStates.proof)
    await state.update_data(activity_id=activity.id, proof_type=proof_type)
    prompts = {
        "photo": "Отправьте фотографию.",
        "link": "Отправьте ссылку.",
        "text": "Отправьте текстовое подтверждение.",
        "file": "Отправьте документ или файл.",
    }
    await message.answer(
        f"✨ {activity.title}\n\n{activity.description}\n\n"
        f"Баллы: +{activity.points}\n{prompts[proof_type]}"
    )
    return True


@router.message(StateFilter("*"), CommandStart(), F.chat.type == "private")
@router.message(StateFilter("*"), Command("menu"), F.chat.type == "private")
async def rescue_start(
    message: Message,
    bot: Bot,
    user: User | None,
    settings: Settings,
    state: FSMContext,
    session: AsyncSession,
    command: CommandObject | None = None,
) -> None:
    await state.clear()
    subscribed = await _subscription_ok(bot, message.from_user.id, settings)
    if subscribed is False:
        await message.answer(
            texts.SUBSCRIPTION_REQUIRED,
            reply_markup=subscription_keyboard(settings.era_channel_url),
        )
        return
    if subscribed is None and not _approved(user):
        await message.answer(
            getattr(
                texts,
                "SUBSCRIPTION_CHECK_UNAVAILABLE",
                "Проверка подписки временно недоступна. Попробуйте немного позже.",
            ),
            reply_markup=subscription_keyboard(settings.era_channel_url),
        )
        return
    if user is None:
        await message.answer(texts.WELCOME, reply_markup=registration_keyboard())
        return
    if await try_handle_faq_payload(
        message,
        user,
        settings,
        state,
        command.args if command else None,
    ):
        return
    if await _try_start_task_submission_from_deep_link(message, user, state, session, command):
        return
    if await _try_start_activity_submission_from_deep_link(
        message, user, state, session, bot, settings, command
    ):
        return
    await _send_main_menu(message, user, settings)


@router.message(StateFilter("*"), Command("cancel"), F.chat.type == "private")
@router.message(StateFilter("*"), F.text.in_(CANCEL_TEXTS), F.chat.type == "private")
async def cancel_any(
    message: Message,
    user: User | None,
    settings: Settings,
    state: FSMContext,
) -> None:
    await state.clear()
    if _approved(user):
        await message.answer("Текущее действие отменено. Выберите раздел в меню ниже.")
        await _send_main_menu(message, user, settings)
        return
    if user is None:
        await message.answer(texts.WELCOME, reply_markup=registration_keyboard())
        return
    await message.answer(texts.APPLICATION_PENDING)


@router.message(
    StateFilter("*"),
    F.text.in_(MENU_BUTTONS),
    F.chat.type == "private",
)
async def rescue_menu_button(
    message: Message,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    await state.clear()
    if not _approved(user):
        await message.answer(texts.APPLICATION_PENDING)
        return

    text = message.text or ""
    if text == "👤 Личный кабинет":
        await _send_personal_cabinet(message, user, session, settings)
        return
    if text == "📅 Афиша":
        await _send_event_list(message, user, session)
        return
    if text == "💡 Проекты":
        await message.answer(
            "💡 Проекты\n\nСоздавайте инициативы, дорабатывайте идеи и собирайте команду.",
            reply_markup=project_menu_keyboard(),
        )
        return
    if text == "⭐ Возможности":
        balance = await total_points(session, user.id)
        await message.answer(
            f"⭐ Возможности\n\nВаш баланс: {balance} баллов",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="⭐ Открыть возможности", callback_data="rewards:menu")],
                    [InlineKeyboardButton(text="← Главное меню", callback_data="menu:main")],
                ]
            ),
        )
        return
    if text == "💬 Связь":
        await message.answer(
            "💬 Связь\n\nВыберите, что Вам нужно.",
            reply_markup=contact_keyboard(),
        )
        return
    if text == "⚙️ Панель":
        if _has_admin_access(user):
            await message.answer(
                texts.ADMIN_PANEL_MOVED,
                reply_markup=open_app_button(settings.effective_miniapp_url),
            )
            return
        if user.role in PRIVILEGED_ROLES:
            await message.answer(
                texts.LEADER_PANEL_MOVED,
                reply_markup=open_app_button(settings.effective_miniapp_url),
            )
            return
        await message.answer(texts.NO_ACCESS)
        return
    await _send_main_menu(message, user, settings)
