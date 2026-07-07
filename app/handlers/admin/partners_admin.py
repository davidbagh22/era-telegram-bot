from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import User
from app.database.partners import Partner
from app.keyboards.partners import admin_partner_card_keyboard, admin_partners_keyboard
from app.states.partners_admin import PartnerAdminStates
from app.utils.constants import Role

router = Router(name="admin_partners")


def admin_ok(user: User | None, settings: Settings, telegram_id: int) -> bool:
    return telegram_id in settings.admin_ids or bool(user and user.role == Role.ADMIN and not user.is_blocked and not user.is_archived)


@router.callback_query(F.data == "admin:menu:growth")
async def growth_menu(call: CallbackQuery, user: User | None, settings: Settings) -> None:
    await call.answer()
    if not admin_ok(user, settings, call.from_user.id):
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Начислить баллы или знак", callback_data="admin:points")], [InlineKeyboardButton(text="Каталог возможностей", callback_data="admin:rewards")], [InlineKeyboardButton(text="Партнёры", callback_data="admin:partners")], [InlineKeyboardButton(text="Аукционы", callback_data="admin:auctions")], [InlineKeyboardButton(text="Назад", callback_data="admin:panel")]])
    await call.message.edit_text("Баллы и развитие", reply_markup=keyboard)


@router.callback_query(F.data == "admin:partners")
async def list_partners(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    await call.answer()
    if not admin_ok(user, settings, call.from_user.id):
        return
    partners = (await session.scalars(select(Partner).where(Partner.is_archived.is_(False)).order_by(Partner.name))).all()
    await call.message.answer("🤝 Партнёры\n\nУправление партнёрами ЭРА.", reply_markup=admin_partners_keyboard(partners))


@router.callback_query(F.data == "admin:partner:add")
async def add_start(call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext) -> None:
    await call.answer()
    if not admin_ok(user, settings, call.from_user.id):
        return
    await state.set_state(PartnerAdminStates.name)
    await call.message.answer("Название партнёра:")


@router.message(PartnerAdminStates.name)
async def add_name(message: Message, state: FSMContext) -> None:
    name = " ".join((message.text or "").split()).strip()
    if not name:
        await message.answer("Название не должно быть пустым.")
        return
    await state.update_data(name=name[:255])
    await state.set_state(PartnerAdminStates.description)
    await message.answer("Краткое описание партнёра:")


@router.message(PartnerAdminStates.description)
async def add_description(message: Message, state: FSMContext) -> None:
    description = (message.text or "").strip()
    if not description:
        await message.answer("Описание не должно быть пустым.")
        return
    await state.update_data(description=description[:2000])
    await state.set_state(PartnerAdminStates.source)
    await message.answer("Ссылка на источник. Можно отправить '-' если ссылки пока нет.")


@router.message(PartnerAdminStates.source)
async def add_source(message: Message, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext) -> None:
    if not admin_ok(user, settings, message.from_user.id):
        return
    raw = (message.text or "").strip()
    source_url = None if raw == "-" else raw
    data = await state.get_data()
    partner = Partner(name=data["name"], description=data["description"], source_url=source_url, created_by=user.id if user else None)
    session.add(partner)
    await session.flush()
    await state.clear()
    await message.answer("Партнёр добавлен ✅", reply_markup=admin_partner_card_keyboard(partner.id, partner.is_active))


@router.callback_query(F.data.startswith("admin:partner:view:"))
async def view_partner(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    await call.answer()
    if not admin_ok(user, settings, call.from_user.id):
        return
    partner = await session.get(Partner, int(call.data.rsplit(":", 1)[-1]))
    if partner is None:
        await call.message.answer("Партнёр не найден.")
        return
    await call.message.answer(f"🤝 {partner.name}\n\n{partner.description}\n\nИсточник: {partner.source_url or 'не указан'}", reply_markup=admin_partner_card_keyboard(partner.id, partner.is_active))


@router.callback_query(F.data.startswith("admin:partner:toggle:"))
async def toggle_partner(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    await call.answer()
    if not admin_ok(user, settings, call.from_user.id):
        return
    partner = await session.get(Partner, int(call.data.rsplit(":", 1)[-1]))
    if partner:
        partner.is_active = not partner.is_active
        await session.flush()
        await call.message.answer("Статус партнёра обновлён.", reply_markup=admin_partner_card_keyboard(partner.id, partner.is_active))


@router.callback_query(F.data.startswith("admin:partner:archive:"))
async def archive_partner(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    await call.answer()
    if not admin_ok(user, settings, call.from_user.id):
        return
    partner = await session.get(Partner, int(call.data.rsplit(":", 1)[-1]))
    if partner:
        partner.is_active = False
        partner.is_archived = True
        await session.flush()
        await call.message.answer("Партнёр отправлен в архив.")
