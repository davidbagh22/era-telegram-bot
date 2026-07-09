from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.database.models import User
from app.keyboards.common import back_keyboard
from app.utils import texts
from app.utils.constants import ApplicationStatus

router = Router(name="participant_portfolio_navigation")


async def _guard(call: CallbackQuery, user: User | None) -> bool:
    await call.answer()
    if user is None or user.application_status != ApplicationStatus.APPROVED:
        await call.message.answer(texts.APPLICATION_PENDING)
        return False
    if user.is_blocked or user.is_archived:
        await call.message.answer(texts.BLOCKED)
        return False
    return True


@router.callback_query(F.data == "portfolio:upload")
async def portfolio_upload_info(call: CallbackQuery, user: User | None) -> None:
    if not await _guard(call, user):
        return
    await call.message.answer(
        "📎 Добавить достижение\n\n"
        "Чтобы достижение попало в портфолио, отправьте материал команде ЭРА через раздел «Связь → Задать вопрос». "
        "После проверки оно появится в Вашем профиле и резюме ЭРА.",
        reply_markup=back_keyboard("cabinet:portfolio"),
    )


@router.callback_query(F.data == "portfolio:view")
async def legacy_portfolio_view(call: CallbackQuery, user: User | None) -> None:
    if not await _guard(call, user):
        return
    await call.message.answer(
        "Портфолио открывается через раздел «Мои данные → Портфолио».",
        reply_markup=back_keyboard("cabinet:portfolio"),
    )
