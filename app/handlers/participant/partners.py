from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User
from app.database.partners import Partner, PartnerInitiative, PartnerTask
from app.keyboards.partners import partner_card_keyboard, partner_list_keyboard
from app.utils import texts
from app.utils.constants import ApplicationStatus

router = Router(name="participant_partners")


def ok(user: User | None) -> bool:
    return bool(user and user.application_status == ApplicationStatus.APPROVED and not user.is_blocked and not user.is_archived)


async def send_partners(target: Message, user: User | None, session: AsyncSession) -> None:
    if not ok(user):
        await target.answer(texts.APPLICATION_PENDING)
        return
    partners = (await session.scalars(select(Partner).where(Partner.is_active.is_(True), Partner.is_archived.is_(False)).order_by(Partner.name))).all()
    if not partners:
        await target.answer("🤝 Партнёры ЭРА\n\nПартнёры скоро появятся в этом разделе.")
        return
    await target.answer("🤝 Партнёры ЭРА\n\nПлощадки и организации, с которыми можно расти дальше.", reply_markup=partner_list_keyboard(partners))


@router.message(Command("partners"))
@router.message(F.text == "🤝 Партнёры")
async def partners_command(message: Message, user: User | None, session: AsyncSession) -> None:
    await send_partners(message, user, session)


@router.callback_query(F.data == "partners:list")
async def partners_list(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    await call.answer()
    await send_partners(call.message, user, session)


@router.callback_query(F.data.startswith("partner:view:"))
async def partner_view(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    await call.answer()
    if not ok(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    partner = await session.get(Partner, int(call.data.rsplit(":", 1)[-1]))
    if partner is None or not partner.is_active or partner.is_archived:
        await call.message.answer("Этот партнёр сейчас недоступен.")
        return
    now = datetime.now().astimezone()
    initiatives = (await session.scalars(select(PartnerInitiative).where(PartnerInitiative.partner_id == partner.id, PartnerInitiative.is_active.is_(True), PartnerInitiative.is_archived.is_(False), or_(PartnerInitiative.expires_at.is_(None), PartnerInitiative.expires_at > now)).order_by(PartnerInitiative.title))).all()
    tasks = (await session.scalars(select(PartnerTask).where(PartnerTask.partner_id == partner.id, PartnerTask.is_active.is_(True), PartnerTask.is_archived.is_(False), or_(PartnerTask.deadline.is_(None), PartnerTask.deadline > now)).order_by(PartnerTask.title))).all()
    initiative_lines = "\n".join(f"• {item.title}" for item in initiatives) or "• пока нет активных инициатив"
    task_lines = "\n".join(f"• {item.title} · {item.points} баллов" for item in tasks) or "• пока нет активных заданий"
    body = f"🤝 {partner.name}\n\n{partner.description}\n\nИнициативы:\n{initiative_lines}\n\nЗадания:\n{task_lines}"
    await call.message.answer(body, reply_markup=partner_card_keyboard(partner))
