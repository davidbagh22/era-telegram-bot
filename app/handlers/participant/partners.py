from datetime import datetime

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User
from app.database.partners import Partner, PartnerInitiative, PartnerTask
from app.keyboards.partners import partner_card_keyboard, partner_list_keyboard
from app.utils.constants import ApplicationStatus

router = Router(name="participant_partners")


def _approved(user: User | None) -> bool:
    return bool(user and user.application_status == ApplicationStatus.APPROVED and not user.is_blocked and not user.is_archived)


@router.callback_query(F.data == "partners:list")
async def partners_list(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    await call.answer()
    if not _approved(user):
        return
    partners = (
        await session.scalars(
            select(Partner)
            .where(Partner.is_active.is_(True), Partner.is_archived.is_(False))
            .order_by(Partner.name)
        )
    ).all()
    if not partners:
        await call.message.answer("Партнёры скоро появятся в этом разделе.")
        return
    await call.message.answer(
        "🤝 Партнёры ЭРА\n\nПлощадки и организации, с которыми можно расти дальше.",
        reply_markup=partner_list_keyboard(partners),
    )


@router.callback_query(F.data.startswith("partner:view:"))
async def partner_view(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    await call.answer()
    if not _approved(user):
        return
    partner = await session.get(Partner, int(call.data.rsplit(":", 1)[-1]))
    if partner is None or not partner.is_active or partner.is_archived:
        await call.message.answer("Этот партнёр сейчас недоступен.")
        return
    now = datetime.now().astimezone()
    initiatives = (
        await session.scalars(
            select(PartnerInitiative)
            .where(
                PartnerInitiative.partner_id == partner.id,
                PartnerInitiative.is_active.is_(True),
            )
            .order_by(PartnerInitiative.created_at.desc())
        )
    ).all()
    initiatives = [item for item in initiatives if item.expires_at is None or item.expires_at > now]
    tasks = (
        await session.scalars(
            select(PartnerTask)
            .where(PartnerTask.partner_id == partner.id, PartnerTask.is_active.is_(True))
            .order_by(PartnerTask.created_at.desc())
        )
    ).all()
    tasks = [task for task in tasks if task.deadline is None or task.deadline > now]
    body = f"🤝 {partner.name}\n\n{partner.description}\n"
    if initiatives:
        body += "\nИнициативы:\n" + "\n".join(f"• {item.title}" for item in initiatives[:5])
    if tasks:
        body += "\n\nЗадания:\n" + "\n".join(f"• {task.title} · {task.points} баллов" for task in tasks[:5])
    await call.message.answer(body, reply_markup=partner_card_keyboard(partner))
