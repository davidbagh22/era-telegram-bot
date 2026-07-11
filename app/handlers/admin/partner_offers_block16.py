from __future__ import annotations

from datetime import datetime

from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import User
from app.database.partners import Partner, PartnerInitiative, PartnerOfferApplication
from app.handlers.admin.partners_admin import admin_ok
from app.services.notification_service import safe_send
from app.services.points_service import add_points, total_points
from app.utils.validators import clean_text

router = Router(name="admin_partner_offers_block16")


class OfferAdminStates(StatesGroup):
    create = State()


def offers_admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить предложение", callback_data="admin:offers:add")],
        [InlineKeyboardButton(text="📦 Все предложения", callback_data="admin:offers:list")],
        [InlineKeyboardButton(text="📥 Заявки участников", callback_data="admin:offers:applications")],
        [InlineKeyboardButton(text="← К партнёрам", callback_data="admin:partners")],
    ])


@router.callback_query(F.data == "admin:offers")
async def offers_admin(call: CallbackQuery, user: User | None, settings: Settings) -> None:
    await call.answer()
    if not admin_ok(user, settings, call.from_user.id):
        return
    await call.message.answer("🤝 Партнёрские предложения\n\nУправление предложениями и заявками участников.", reply_markup=offers_admin_keyboard())


@router.callback_query(F.data == "admin:offers:add")
async def offer_add_start(call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext) -> None:
    await call.answer()
    if not admin_ok(user, settings, call.from_user.id):
        return
    await state.set_state(OfferAdminStates.create)
    await call.message.answer(
        "Отправьте предложение одной строкой:\n\n"
        "ID партнёра | Название | Стоимость | Количество или - | Дедлайн ДД.ММ.ГГГГ или - | Описание | Инструкция | Ссылка или -\n\n"
        "Пример:\n1 | Сертификат участника | 200 | 20 | 31.12.2026 | Сертификат от партнёра | После одобрения с Вами свяжется команда | -"
    )


@router.message(OfferAdminStates.create)
async def offer_add_finish(message: Message, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext) -> None:
    if not admin_ok(user, settings, message.from_user.id):
        return
    parts = [part.strip() for part in (message.text or "").split("|")]
    if len(parts) < 8:
        await message.answer("Нужно 8 полей через символ |. Проверьте формат.")
        return
    try:
        partner_id = int(parts[0])
        point_cost = int(parts[2])
        quantity = None if parts[3] == "-" else int(parts[3])
        expires_at = None if parts[4] == "-" else datetime.strptime(parts[4], "%d.%m.%Y")
    except ValueError:
        await message.answer("Проверьте ID, стоимость, количество и дату.")
        return
    partner = await session.get(Partner, partner_id)
    if not partner or partner.is_archived:
        await message.answer("Партнёр с таким ID не найден.")
        return
    title = clean_text(parts[1], 255)
    description = clean_text(parts[5], 3000)
    instruction = clean_text(parts[6], 3000)
    source_url = None if parts[7] == "-" else parts[7][:500]
    if not title or not description or point_cost < 0 or (quantity is not None and quantity < 1):
        await message.answer("Название, описание, стоимость или количество заполнены неверно.")
        return
    offer = PartnerInitiative(
        partner_id=partner.id,
        title=title,
        description=description,
        point_cost=point_cost,
        quantity=quantity,
        expires_at=expires_at,
        instruction=instruction,
        source_url=source_url,
        is_active=True,
        is_archived=False,
    )
    session.add(offer)
    await session.flush()
    await state.clear()
    await message.answer(f"Предложение добавлено: {offer.title}", reply_markup=offers_admin_keyboard())


@router.callback_query(F.data == "admin:offers:list")
async def offers_list(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    await call.answer()
    if not admin_ok(user, settings, call.from_user.id):
        return
    result = await session.execute(
        select(PartnerInitiative, Partner)
        .join(Partner, Partner.id == PartnerInitiative.partner_id)
        .where(PartnerInitiative.is_archived.is_(False))
        .order_by(Partner.name, PartnerInitiative.title)
    )
    rows = list(result.all())
    if not rows:
        await call.message.answer("Предложений пока нет.", reply_markup=offers_admin_keyboard())
        return
    buttons = [
        [InlineKeyboardButton(text=f"{offer.title[:30]} · {'вкл' if offer.is_active else 'скрыто'}", callback_data=f"admin:offer:view:{offer.id}")]
        for offer, _ in rows
    ]
    buttons.append([InlineKeyboardButton(text="← Назад", callback_data="admin:offers")])
    await call.message.answer("📦 Все предложения", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("admin:offer:view:"))
async def offer_view(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    await call.answer()
    if not admin_ok(user, settings, call.from_user.id):
        return
    offer = await session.get(PartnerInitiative, int(call.data.rsplit(":", 1)[-1]))
    if not offer:
        await call.message.answer("Предложение не найдено.")
        return
    partner = await session.get(Partner, offer.partner_id)
    await call.message.answer(
        f"{offer.title}\n\nПартнёр: {partner.name if partner else '—'}\nСтоимость: {offer.point_cost}\nКоличество: {offer.quantity or 'без ограничения'}\nСтатус: {'активно' if offer.is_active else 'скрыто'}\n\n{offer.description}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Скрыть" if offer.is_active else "Активировать", callback_data=f"admin:offer:toggle:{offer.id}")],
            [InlineKeyboardButton(text="Архивировать", callback_data=f"admin:offer:archive:{offer.id}")],
            [InlineKeyboardButton(text="← Все предложения", callback_data="admin:offers:list")],
        ]),
    )


@router.callback_query(F.data.startswith("admin:offer:toggle:"))
async def offer_toggle(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    await call.answer()
    if not admin_ok(user, settings, call.from_user.id):
        return
    offer = await session.get(PartnerInitiative, int(call.data.rsplit(":", 1)[-1]))
    if offer:
        offer.is_active = not offer.is_active
        await session.flush()
    await call.message.answer("Статус предложения обновлён.", reply_markup=offers_admin_keyboard())


@router.callback_query(F.data.startswith("admin:offer:archive:"))
async def offer_archive(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    await call.answer()
    if not admin_ok(user, settings, call.from_user.id):
        return
    offer = await session.get(PartnerInitiative, int(call.data.rsplit(":", 1)[-1]))
    if offer:
        offer.is_active = False
        offer.is_archived = True
        await session.flush()
    await call.message.answer("Предложение архивировано.", reply_markup=offers_admin_keyboard())


def application_keyboard(application_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Одобрить и списать баллы", callback_data=f"admin:offerapp:approve:{application_id}")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:offerapp:reject:{application_id}")],
    ])


@router.callback_query(F.data == "admin:offers:applications")
async def applications_list(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    await call.answer()
    if not admin_ok(user, settings, call.from_user.id):
        return
    result = await session.execute(
        select(PartnerOfferApplication, PartnerInitiative, User)
        .join(PartnerInitiative, PartnerInitiative.id == PartnerOfferApplication.initiative_id)
        .join(User, User.id == PartnerOfferApplication.user_id)
        .where(PartnerOfferApplication.status == "pending")
        .order_by(PartnerOfferApplication.created_at)
    )
    rows = list(result.all())
    if not rows:
        await call.message.answer("Новых заявок нет.", reply_markup=offers_admin_keyboard())
        return
    await call.message.answer(f"Заявок на проверке: {len(rows)}")
    for application, offer, participant in rows:
        balance = await total_points(session, participant.id)
        await call.message.answer(
            f"{offer.title}\nУчастник: {participant.first_name} {participant.last_name or ''}\nСтоимость: {offer.point_cost}\nБаланс: {balance}",
            reply_markup=application_keyboard(application.id),
        )


@router.callback_query(F.data.startswith("admin:offerapp:approve:"))
async def application_approve(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, bot: Bot) -> None:
    await call.answer()
    if not admin_ok(user, settings, call.from_user.id):
        return
    application = await session.get(PartnerOfferApplication, int(call.data.rsplit(":", 1)[-1]))
    if not application or application.status != "pending":
        await call.message.answer("Заявка уже обработана.")
        return
    offer = await session.get(PartnerInitiative, application.initiative_id)
    participant = await session.get(User, application.user_id)
    if not offer or not participant:
        await call.message.answer("Предложение или участник не найдены.")
        return
    balance = await total_points(session, participant.id)
    if balance < offer.point_cost:
        await call.message.answer("У участника уже недостаточно баллов. Заявка не одобрена.")
        return
    if offer.point_cost:
        await add_points(
            session,
            user_id=participant.id,
            points=-offer.point_cost,
            reason=f"Партнёрское предложение: {offer.title}",
            approved_by=user.id if user else None,
        )
    application.status = "approved"
    application.reviewed_by = user.id if user else None
    await session.flush()
    await safe_send(bot, participant.telegram_id, f"Ваша заявка «{offer.title}» одобрена. Списано: {offer.point_cost} баллов. Команда ЭРА свяжется с Вами.")
    await call.message.answer("Заявка одобрена. Баллы списаны один раз.")


@router.callback_query(F.data.startswith("admin:offerapp:reject:"))
async def application_reject(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, bot: Bot) -> None:
    await call.answer()
    if not admin_ok(user, settings, call.from_user.id):
        return
    application = await session.get(PartnerOfferApplication, int(call.data.rsplit(":", 1)[-1]))
    if not application or application.status != "pending":
        await call.message.answer("Заявка уже обработана.")
        return
    offer = await session.get(PartnerInitiative, application.initiative_id)
    participant = await session.get(User, application.user_id)
    application.status = "rejected"
    application.reviewed_by = user.id if user else None
    await session.flush()
    if participant and offer:
        await safe_send(bot, participant.telegram_id, f"Заявка «{offer.title}» отклонена. Баллы не списаны.")
    await call.message.answer("Заявка отклонена. Баллы не списаны.")
