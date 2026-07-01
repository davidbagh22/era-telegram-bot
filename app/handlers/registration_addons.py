from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.handlers.registration import _application_notification
from app.keyboards.admin import application_actions
from app.keyboards.participant import main_menu
from app.keyboards.registration import pending_registration_keyboard
from app.repositories.users import create_user_from_registration
from app.services.audit_service import audit
from app.services.notification_service import notify_admins
from app.services.points_service import add_points
from app.states.registration import RegistrationStates
from app.utils import texts
from app.utils.constants import ApplicationStatus, PRIVILEGED_ROLES, Role

router = Router(name="registration_addons")


def _application_notification_full(user) -> str:
    base = _application_notification(user)
    marker = f"📍 Город: {user.city or 'не указан'}\n"
    phone_line = f"📱 Телефон: {user.phone or 'не указан'}\n"
    if phone_line.strip() in base:
        return base
    return base.replace(marker, marker + phone_line)


@router.callback_query(RegistrationStates.consent, F.data == "reg:consent:yes")
async def finish_registration_full_notice(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    settings: Settings,
) -> None:
    await call.answer()
    data = await state.get_data()
    user, created = await create_user_from_registration(
        session,
        telegram_id=call.from_user.id,
        username=call.from_user.username,
        data=data,
    )
    if call.from_user.id in settings.admin_ids:
        user.role = Role.ADMIN
        user.application_status = ApplicationStatus.APPROVED
        if created:
            await add_points(
                session,
                user_id=user.id,
                points=5,
                reason="Регистрация в боте",
                approved_by=user.id,
            )
    if created:
        await audit(
            session,
            actor_id=user.id,
            action="user.registered",
            entity_type="user",
            entity_id=user.id,
            new_value={"telegram_id": user.telegram_id},
        )
    await session.flush()
    await state.clear()
    if user.application_status == ApplicationStatus.APPROVED:
        await call.message.answer(texts.APPLICATION_APPROVED)
        await call.message.answer(
            texts.MAIN_MENU,
            reply_markup=main_menu(
                settings.era_channel_url,
                privileged=user.role in PRIVILEGED_ROLES,
                admin=user.role == Role.ADMIN,
            ),
        )
    else:
        await call.message.answer(
            texts.REG_DONE,
            reply_markup=pending_registration_keyboard(settings.era_channel_url),
        )
        await notify_admins(
            bot,
            settings,
            _application_notification_full(user),
            reply_markup=application_actions(user.id),
        )
