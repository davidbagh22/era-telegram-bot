from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import User
from app.keyboards.participant import main_menu
from app.keyboards.registration import pending_registration_keyboard
from app.services.audit_service import audit
from app.services.notification_service import safe_send
from app.services.points_service import add_points
from app.utils import texts
from app.utils.constants import ApplicationStatus, PRIVILEGED_ROLES, Role
from app.utils.validators import clean_text

router = Router(name="admin_applications_flow")
WELCOME_POINTS = 100


class ApplicationDecisionStates(StatesGroup):
    comment = State()


def _is_admin(user: User | None, settings: Settings, telegram_id: int) -> bool:
    return bool(
        telegram_id in settings.admin_ids
        or (user and user.role == Role.ADMIN and not user.is_blocked)
        or (
            user
            and not user.is_blocked
            and not user.is_archived
            and any(g.is_active and g.permission == "applications.review" for g in (user.permission_grants or []))
        )
    )


async def _guard(event: CallbackQuery | Message, user: User | None, settings: Settings) -> bool:
    if isinstance(event, CallbackQuery):
        await event.answer()
        message = event.message
        telegram_id = event.from_user.id
    else:
        message = event
        telegram_id = event.from_user.id
    if not _is_admin(user, settings, telegram_id):
        await message.answer(texts.NO_ACCESS)
        return False
    return True


def _back_to_applications() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="← К заявкам", callback_data="admin:applications")]])


@router.callback_query(F.data.startswith("admin:approve_user:"))
async def approve_user(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, bot: Bot) -> None:
    if not await _guard(call, user, settings):
        return
    target = await session.get(User, int(call.data.rsplit(":", 1)[-1]))
    if target is None:
        await call.message.answer("Заявка не найдена", reply_markup=_back_to_applications())
        return
    if target.application_status == ApplicationStatus.APPROVED:
        await call.message.answer("Эта заявка уже одобрена. Повторно баллы не начисляю.", reply_markup=_back_to_applications())
        return
    old = target.application_status
    target.application_status = ApplicationStatus.APPROVED
    target.role = Role.PARTICIPANT
    await add_points(session, user_id=target.id, points=WELCOME_POINTS, reason="Регистрация в боте", approved_by=user.id if user else None)
    await audit(session, actor_id=user.id if user else None, action="user.approved", entity_type="user", entity_id=target.id, old_value={"application_status": old}, new_value={"application_status": target.application_status, "welcome_points": WELCOME_POINTS})
    await call.message.answer(f"Заявка одобрена ✅\n\n{target.first_name} получил доступ и {WELCOME_POINTS} стартовых баллов.", reply_markup=_back_to_applications())
    await safe_send(bot, target.telegram_id, texts.APPLICATION_APPROVED, main_menu(settings.era_channel_url, privileged=target.role in PRIVILEGED_ROLES, admin=target.role == Role.ADMIN))


@router.callback_query(F.data.regexp(r"^admin:(reject_user|info_user):\d+$"))
async def decision_start(call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext) -> None:
    if not await _guard(call, user, settings):
        return
    action = call.data.split(":", 1)[0].replace("admin", "")
    raw_id = int(call.data.rsplit(":", 1)[-1])
    is_info = call.data.startswith("admin:info_user:")
    await state.set_state(ApplicationDecisionStates.comment)
    await state.update_data(application_action="info" if is_info else "reject", application_user_id=raw_id)
    await call.message.answer(
        "Напишите уточняющий вопрос пользователю." if is_info else "Напишите причину отказа.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data="admin:applications")]]),
    )


@router.message(ApplicationDecisionStates.comment)
async def decision_finish(message: Message, user: User | None, settings: Settings, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    if not await _guard(message, user, settings):
        return
    comment = clean_text(message.text or "", 2000)
    if not comment:
        await message.answer("Комментарий обязателен")
        return
    data = await state.get_data()
    target = await session.get(User, int(data["application_user_id"]))
    if target is None:
        await state.clear()
        await message.answer("Заявка не найдена", reply_markup=_back_to_applications())
        return
    if data["application_action"] == "info":
        target.application_status = ApplicationStatus.NEEDS_INFO
        await safe_send(bot, target.telegram_id, texts.APPLICATION_NEEDS_INFO.format(comment=comment), reply_markup=pending_registration_keyboard(settings.era_channel_url))
        await message.answer("Уточняющий вопрос отправлен. Когда пользователь ответит, заявка вернётся в очередь.", reply_markup=_back_to_applications())
    else:
        target.application_status = ApplicationStatus.REJECTED
        await safe_send(bot, target.telegram_id, f"{texts.APPLICATION_REJECTED}\n\nКомментарий команды ЭРА:\n{comment}")
        await message.answer("Заявка отклонена.", reply_markup=_back_to_applications())
    await audit(session, actor_id=user.id if user else None, action=f"user.application_{data['application_action']}", entity_type="user", entity_id=target.id, new_value={"comment": comment})
    await state.clear()
