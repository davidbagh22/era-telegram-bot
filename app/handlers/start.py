from aiogram import F, Bot, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Task, User
from app.keyboards.common import registration_keyboard, subscription_keyboard
from app.keyboards.participant import main_menu
from app.keyboards.registration import pending_registration_keyboard
from app.services import task_service
from app.services.subscription_service import SubscriptionCheckError, is_channel_member
from app.states.growth import TaskSubmissionStates
from app.utils import texts, ux_texts
from app.utils.constants import ApplicationStatus, PRIVILEGED_ROLES, Role
from app.utils.deep_links import parse_task_submit_payload

router = Router(name="start")


async def show_home(message: Message, user: User, settings: Settings) -> None:
    if user.is_blocked or user.is_archived:
        await message.answer(texts.BLOCKED)
        return
    if user.application_status == ApplicationStatus.PENDING:
        await message.answer(
            texts.APPLICATION_PENDING,
            reply_markup=pending_registration_keyboard(settings.era_channel_url),
        )
        return
    if user.application_status == ApplicationStatus.REJECTED:
        await message.answer(texts.APPLICATION_REJECTED)
        return
    if user.application_status == ApplicationStatus.NEEDS_INFO:
        await message.answer(
            texts.APPLICATION_PENDING,
            reply_markup=pending_registration_keyboard(settings.era_channel_url),
        )
        return
    await message.answer(
        ux_texts.MAIN_MENU,
        reply_markup=main_menu(
            settings.era_channel_url,
            privileged=user.role in PRIVILEGED_ROLES,
            admin=user.role == Role.ADMIN
            or any(
                grant.is_active
                for grant in (getattr(user, "permission_grants", None) or [])
            ),
            miniapp_url=settings.effective_miniapp_url,
        ),
    )


async def _subscription_ok(bot: Bot, telegram_id: int, settings: Settings) -> bool | None:
    try:
        return await is_channel_member(bot, telegram_id, settings)
    except SubscriptionCheckError:
        return None


def _approved_existing_user(user: User | None) -> bool:
    return bool(
        user
        and user.application_status == ApplicationStatus.APPROVED
        and not user.is_blocked
        and not user.is_archived
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
    deep link was valid and the submission prompt was sent."""
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


@router.message(CommandStart(), F.chat.type == "private")
@router.message(Command("menu"), F.chat.type == "private")
async def start(
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
    if subscribed is None:
        if _approved_existing_user(user):
            await show_home(message, user, settings)
            return
        await message.answer(
            getattr(
                texts,
                "SUBSCRIPTION_CHECK_UNAVAILABLE",
                "Проверка подписки временно недоступна. Попробуйте позже или напишите администратору.",
            ),
            reply_markup=subscription_keyboard(settings.era_channel_url),
        )
        return
    if not subscribed:
        await message.answer(
            texts.SUBSCRIPTION_REQUIRED,
            reply_markup=subscription_keyboard(settings.era_channel_url),
        )
        return
    if user is None:
        await message.answer(ux_texts.WELCOME_START, reply_markup=registration_keyboard())
        return
    if await _try_start_task_submission_from_deep_link(message, user, state, session, command):
        return
    await show_home(message, user, settings)


@router.callback_query(F.data == "subscription:check")
async def check_subscription(
    call: CallbackQuery,
    bot: Bot,
    user: User | None,
    settings: Settings,
    state: FSMContext,
) -> None:
    await call.answer()
    await state.clear()
    subscribed = await _subscription_ok(bot, call.from_user.id, settings)
    if subscribed is None:
        if _approved_existing_user(user):
            await show_home(call.message, user, settings)
            return
        await call.message.answer(
            getattr(
                texts,
                "SUBSCRIPTION_CHECK_UNAVAILABLE",
                "Проверка подписки временно недоступна. Попробуйте позже или напишите администратору.",
            ),
            reply_markup=subscription_keyboard(settings.era_channel_url),
        )
        return
    if not subscribed:
        await call.message.answer(
            texts.SUBSCRIPTION_CHECK_FAILED,
            reply_markup=subscription_keyboard(settings.era_channel_url),
        )
        return
    if user is None:
        await call.message.answer(
            texts.SUBSCRIPTION_CONFIRMED, reply_markup=registration_keyboard()
        )
    else:
        await show_home(call.message, user, settings)


@router.callback_query(F.data == "menu:main")
async def main_menu_callback(
    call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext
) -> None:
    await call.answer()
    await state.clear()
    if user is None:
        await call.message.answer(ux_texts.WELCOME_START, reply_markup=registration_keyboard())
        return
    await show_home(call.message, user, settings)


@router.message(Command("rules"), F.chat.type == "private")
async def private_rules(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(texts.CHAT_RULES)
