from aiogram import F, Bot, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Event, EventActivity, EventRegistration, Task, User
from app.handlers.participant.event_activities_block15 import (
    ACTIVE_REGISTRATION_STATUSES,
    ALLOWED_PROOF_TYPES,
    ActivityProofStates,
)
from app.handlers.participant.event_activities_block15 import (
    _notify_proof as notify_activity_proof,
)
from app.keyboards.common import registration_keyboard, subscription_keyboard
from app.keyboards.participant import main_menu
from app.keyboards.registration import pending_registration_keyboard
from app.services import event_activity_service, task_service
from app.services.subscription_service import SubscriptionCheckError, is_channel_member
from app.states.growth import TaskSubmissionStates
from app.utils import texts, ux_texts
from app.utils.constants import ApplicationStatus, PRIVILEGED_ROLES, Role
from app.utils.deep_links import parse_activity_submit_payload, parse_task_submit_payload

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
    task submission does above — uploads stay a Bot-only FSM. Returns
    True if the deep link was valid and handled (either the submission
    prompt was sent, or a "manual" proof-type activity was submitted
    immediately, mirroring proof_start()'s own short-circuit for that
    type in app/handlers/participant/event_activities_block15.py)."""
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
    if await _try_start_activity_submission_from_deep_link(
        message, user, state, session, bot, settings, command
    ):
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
