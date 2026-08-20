from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.database.models import User
from app.keyboards.participant import points_hub_keyboard
from app.utils import texts
from app.utils.constants import ApplicationStatus

router = Router(name="cabinet_hubs")


async def _guard(call: CallbackQuery, user: User | None) -> bool:
    await call.answer()
    if user is None or user.application_status != ApplicationStatus.APPROVED:
        await call.message.answer(texts.APPLICATION_PENDING)
        return False
    if user.is_blocked or user.is_archived:
        await call.message.answer(texts.BLOCKED)
        return False
    return True


@router.callback_query(F.data == "cabinet:points_hub")
async def points_hub(call: CallbackQuery, user: User | None) -> None:
    """Extra points sub-hub; the canonical profile callback lives in cabinet.py."""
    if not await _guard(call, user):
        return
    await call.message.answer(
        "🏆 Баллы и достижения\n\nБаланс, история операций, знаки и место в рейтинге — здесь.",
        reply_markup=points_hub_keyboard(),
    )
