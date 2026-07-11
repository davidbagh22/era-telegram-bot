from __future__ import annotations

from datetime import datetime, timezone

from aiogram import F, Bot, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import User
from app.database.partners import Partner, PartnerInitiative, PartnerOfferApplication
from app.services.notification_service import notify_admins
from app.services.points_service import total_points
from app.utils import texts
from app.utils.constants import ApplicationStatus

router = Router(name="participant_partner_offers_block16")


def approved(user: User | None) -> bool:
    return bool(user and user.application_status == ApplicationStatus.APPROVED and not user.is_blocked and not user.is_archived)


def opportunities_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤝 Партнёрские предложения", callback_data="offers:list")],
        [InlineKeyboardButton(text="📜 Мои заявки", callback_data="offers:mine")],
        [InlineKeyboardButton(text="🎁 Каталог возможностей", callback_data="rewards:menu")],
        [InlineKeyboardButton(text="← Главное меню", callback_data="menu:main")],
    ])


def offer_list_keyboard(rows: list[tuple[PartnerInitiative, Partner]]) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=f"{offer.title[:35]} · {offer.point_cost} баллов", callback_data=f"offer:view:{offer.id}")]
        for offer, _ in rows
    ]
    buttons.append([InlineKeyboardButton(text="📜 Мои заявки", callback_data="offers:mine")])
    buttons.append([InlineKeyboardButton(text="← Возможности", callback_data="offers:menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data == "offers:menu")
async def offers_menu(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    await call.answer()
    if not approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    balance = await total_points(session, user.id)
    await call.message.answer(
        "⭐ Возможности\n\nЗдесь собраны предложения, доступы и бонусы, которые открываются через активность в ЭРА.\n\n"
        f"Ваш баланс: {balance} баллов",
        reply_markup=opportunities_keyboard(),
    )


@router.callback_query(F.data == "offers:list")
async def offers_list(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    await call.answer()
    if not approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(PartnerInitiative, Partner)
        .join(Partner, Partner.id == PartnerInitiative.partner_id)
        .where(
            PartnerInitiative.is_active.is_(True),
            PartnerInitiative.is_archived.is_(False),
            Partner.is_active.is_(True),
            Partner.is_archived.is_(False),
            (PartnerInitiative.expires_at.is_(None) | (PartnerInitiative.expires_at >= now)),
        )
        .order_by(Partner.name, PartnerInitiative.title)
    )
    rows = list(result.all())
    if not rows:
        await call.message.answer(
            "🤝 Партнёрские предложения\n\nВозможности пока формируются. ЭРА собирает сертификаты, рекомендации, приглашения и специальные предложения для активных участников.",
            reply_markup=opportunities_keyboard(),
        )
        return
    await call.message.answer(
        "🤝 Партнёрские предложения\n\nВыберите предложение. Заявка отправится команде ЭРА на проверку.",
        reply_markup=offer_list_keyboard(rows),
    )


@router.callback_query(F.data.startswith("offer:view:"))
async def offer_view(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    await call.answer()
    if not approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    offer = await session.get(PartnerInitiative, int(call.data.rsplit(":", 1)[-1]))
    if not offer or not offer.is_active or offer.is_archived:
        await call.message.answer("Это предложение сейчас недоступно.")
        return
    partner = await session.get(Partner, offer.partner_id)
    application = await session.scalar(select(PartnerOfferApplication).where(
        PartnerOfferApplication.initiative_id == offer.id,
        PartnerOfferApplication.user_id == user.id,
    ))
    applied = bool(application and application.status in {"pending", "approved"})
    remaining = "без ограничения"
    if offer.quantity is not None:
        used = int(await session.scalar(select(func.count(PartnerOfferApplication.id)).where(
            PartnerOfferApplication.initiative_id == offer.id,
            PartnerOfferApplication.status.in_(["pending", "approved"]),
        )) or 0)
        remaining = str(max(offer.quantity - used, 0))
    text = (
        f"🤝 {partner.name if partner else 'Партнёр ЭРА'}\n\n"
        f"{offer.title}\n\n{offer.description}\n\n"
        f"Стоимость: {offer.point_cost} баллов\n"
        f"Доступно мест: {remaining}"
    )
    if offer.expires_at:
        text += f"\nДедлайн: {offer.expires_at:%d.%m.%Y}"
    if offer.instruction:
        text += f"\n\nКак получить:\n{offer.instruction}"
    rows = []
    if applied:
        rows.append([InlineKeyboardButton(text="Заявка уже отправлена", callback_data="offers:mine")])
    else:
        rows.append([InlineKeyboardButton(text="Подать заявку", callback_data=f"offer:apply:{offer.id}")])
    if offer.source_url:
        rows.append([InlineKeyboardButton(text="Подробнее", url=offer.source_url)])
    rows.append([InlineKeyboardButton(text="← К предложениям", callback_data="offers:list")])
    await call.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("offer:apply:"))
async def offer_apply(call: CallbackQuery, user: User | None, session: AsyncSession, bot: Bot, settings: Settings) -> None:
    await call.answer()
    if not approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    offer = await session.get(PartnerInitiative, int(call.data.rsplit(":", 1)[-1]))
    if not offer or not offer.is_active or offer.is_archived:
        await call.message.answer("Это предложение сейчас недоступно.")
        return
    existing = await session.scalar(select(PartnerOfferApplication).where(
        PartnerOfferApplication.initiative_id == offer.id,
        PartnerOfferApplication.user_id == user.id,
    ))
    if existing and existing.status in {"pending", "approved"}:
        await call.message.answer("Заявка уже отправлена.")
        return
    balance = await total_points(session, user.id)
    if balance < offer.point_cost:
        await call.message.answer(f"Недостаточно баллов. Нужно: {offer.point_cost}. Ваш баланс: {balance}.")
        return
    if offer.quantity is not None:
        used = int(await session.scalar(select(func.count(PartnerOfferApplication.id)).where(
            PartnerOfferApplication.initiative_id == offer.id,
            PartnerOfferApplication.status.in_(["pending", "approved"]),
        )) or 0)
        if used >= offer.quantity:
            await call.message.answer("Свободных мест по этому предложению больше нет.")
            return
    if existing:
        existing.status = "pending"
        existing.reviewed_by = None
        existing.admin_comment = None
        application = existing
    else:
        application = PartnerOfferApplication(initiative_id=offer.id, user_id=user.id, status="pending")
        session.add(application)
    await session.flush()
    await call.message.answer("Заявка отправлена. Баллы спишутся только после одобрения администратором.")
    await notify_admins(
        bot,
        settings,
        f"Новая заявка на партнёрское предложение\n\n{offer.title}\nУчастник: {user.first_name} {user.last_name or ''}\nСтоимость: {offer.point_cost} баллов",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Открыть заявки", callback_data="admin:offers:applications")]
        ]),
    )


@router.callback_query(F.data == "offers:mine")
async def my_offer_applications(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    await call.answer()
    if not approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    result = await session.execute(
        select(PartnerOfferApplication, PartnerInitiative)
        .join(PartnerInitiative, PartnerInitiative.id == PartnerOfferApplication.initiative_id)
        .where(PartnerOfferApplication.user_id == user.id)
        .order_by(PartnerOfferApplication.created_at.desc())
    )
    rows = list(result.all())
    if not rows:
        await call.message.answer("📜 Мои заявки\n\nЗаявок пока нет.", reply_markup=opportunities_keyboard())
        return
    labels = {"pending": "на проверке", "approved": "одобрена", "rejected": "отклонена"}
    text = "📜 Мои заявки\n\n" + "\n".join(
        f"• {offer.title} — {labels.get(app.status, app.status)}" for app, offer in rows
    )
    await call.message.answer(text, reply_markup=opportunities_keyboard())
