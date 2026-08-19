from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.config import Settings
from app.keyboards.participant import main_inline_keyboard
from app.utils import texts
from app.utils.constants import ApplicationStatus, PRIVILEGED_ROLES, Role

router = Router(name="registration_status")
router.callback_query.filter(F.message.chat.type == "private")


@router.callback_query(F.data == "registration:status:v2")
async def registration_status_v2(
    call: CallbackQuery,
    user,
    settings: Settings,
) -> None:
    """Show the persisted application state instead of collapsing every non-approved state to PENDING."""
    await call.answer()
    if user is None:
        await call.message.answer(texts.WELCOME)
        return

    status = user.application_status
    if status == ApplicationStatus.APPROVED:
        await call.message.answer(
            texts.APPLICATION_APPROVED,
            reply_markup=main_inline_keyboard(
                privileged=user.role in PRIVILEGED_ROLES,
                admin=user.role == Role.ADMIN,
                miniapp_url=settings.effective_miniapp_url,
            ),
        )
        return
    if status == ApplicationStatus.REJECTED:
        # Rejection reasons remain internal-only by product policy.
        await call.message.answer(texts.APPLICATION_REJECTED)
        return
    if status == ApplicationStatus.NEEDS_INFO:
        await call.message.answer(
            "Команде ЭРА нужна дополнительная информация по Вашей заявке.\n\n"
            "Проверьте последнее сообщение от бота и отправьте запрошенное уточнение. "
            "Статус изменится после повторного рассмотрения."
        )
        return

    await call.message.answer(texts.APPLICATION_PENDING)
