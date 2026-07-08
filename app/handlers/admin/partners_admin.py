from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import User
from app.database.partners import Partner, PartnerInitiative, PartnerTask
from app.keyboards.partners import (
    admin_partner_archive_confirm_keyboard,
    admin_partner_card_keyboard,
    admin_partners_keyboard,
)
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
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Начислить баллы или знак", callback_data="admin:points")],
        [InlineKeyboardButton(text="Каталог возможностей", callback_data="admin:rewards")],
        [InlineKeyboardButton(text="Партнёры", callback_data="admin:partners")],
        [InlineKeyboardButton(text="Аукционы", callback_data="admin:auctions")],
        [InlineKeyboardButton(text="Назад", callback_data="admin:panel")],
    ])
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


async def _partner_card(partner: Partner, session: AsyncSession) -> str:
    initiatives = (await session.scalars(select(PartnerInitiative).where(PartnerInitiative.partner_id == partner.id, PartnerInitiative.is_archived.is_(False)).order_by(PartnerInitiative.title))).all()
    tasks = (await session.scalars(select(PartnerTask).where(PartnerTask.partner_id == partner.id, PartnerTask.is_archived.is_(False)).order_by(PartnerTask.title))).all()
    initiative_lines = "\n".join(f"• {'🟢' if item.is_active else '⚪️'} {item.title}" for item in initiatives) or "• нет"
    task_lines = "\n".join(f"• {'🟢' if item.is_active else '⚪️'} {item.title} · {item.points} баллов" for item in tasks) or "• нет"
    return f"🤝 {partner.name}\n\n{partner.description}\n\nИсточник: {partner.source_url or 'не указан'}\nСтатус: {'активен' if partner.is_active else 'выключен'}\n\nИнициативы:\n{initiative_lines}\n\nЗадания:\n{task_lines}"


@router.callback_query(F.data.startswith("admin:partner:view:"))
async def view_partner(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    await call.answer()
    if not admin_ok(user, settings, call.from_user.id):
        return
    partner = await session.get(Partner, int(call.data.rsplit(":", 1)[-1]))
    if partner is None:
        await call.message.answer("Партнёр не найден.")
        return
    await call.message.answer(await _partner_card(partner, session), reply_markup=admin_partner_card_keyboard(partner.id, partner.is_active))


@router.callback_query(F.data.startswith("admin:partner:edit:"))
async def edit_start(call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext) -> None:
    await call.answer()
    if not admin_ok(user, settings, call.from_user.id):
        return
    _, _, _, field, raw_id = call.data.split(":")
    await state.update_data(partner_id=int(raw_id), field=field)
    await state.set_state(PartnerAdminStates.edit_value)
    labels = {"name": "новое название", "description": "новое описание", "source": "новую ссылку или '-'"}
    await call.message.answer(f"Отправьте {labels.get(field, 'новое значение')}:")


@router.message(PartnerAdminStates.edit_value)
async def edit_value(message: Message, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext) -> None:
    if not admin_ok(user, settings, message.from_user.id):
        return
    data = await state.get_data()
    partner = await session.get(Partner, int(data["partner_id"]))
    if partner is None:
        await state.clear()
        await message.answer("Партнёр не найден.")
        return
    value = (message.text or "").strip()
    field = data.get("field")
    if field == "name" and value:
        partner.name = value[:255]
    elif field == "description" and value:
        partner.description = value[:2000]
    elif field == "source":
        partner.source_url = None if value == "-" else value[:500]
    else:
        await message.answer("Значение не должно быть пустым.")
        return
    await session.flush()
    await state.clear()
    await message.answer("Партнёр обновлён ✅", reply_markup=admin_partner_card_keyboard(partner.id, partner.is_active))


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


@router.callback_query(F.data.startswith("admin:partner:archive:confirm:"))
async def archive_confirm(call: CallbackQuery, user: User | None, settings: Settings) -> None:
    await call.answer()
    if not admin_ok(user, settings, call.from_user.id):
        return
    partner_id = int(call.data.rsplit(":", 1)[-1])
    await call.message.answer("Архивировать партнёра? Он пропадёт из пользовательского раздела.", reply_markup=admin_partner_archive_confirm_keyboard(partner_id))


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


@router.callback_query(F.data.startswith("admin:partner:initiative:add:"))
async def initiative_start(call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext) -> None:
    await call.answer()
    if not admin_ok(user, settings, call.from_user.id):
        return
    await state.update_data(partner_id=int(call.data.rsplit(":", 1)[-1]))
    await state.set_state(PartnerAdminStates.initiative_title)
    await call.message.answer("Название инициативы:")


@router.message(PartnerAdminStates.initiative_title)
async def initiative_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=(message.text or "").strip()[:255])
    await state.set_state(PartnerAdminStates.initiative_description)
    await message.answer("Описание инициативы:")


@router.message(PartnerAdminStates.initiative_description)
async def initiative_description(message: Message, state: FSMContext) -> None:
    await state.update_data(description=(message.text or "").strip()[:2000])
    await state.set_state(PartnerAdminStates.initiative_source)
    await message.answer("Ссылка на инициативу или '-':")


@router.message(PartnerAdminStates.initiative_source)
async def initiative_source(message: Message, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext) -> None:
    if not admin_ok(user, settings, message.from_user.id):
        return
    data = await state.get_data()
    raw = (message.text or "").strip()
    item = PartnerInitiative(partner_id=int(data["partner_id"]), title=data["title"] or "Инициатива", description=data["description"] or "Описание уточняется", source_url=None if raw == "-" else raw)
    session.add(item)
    await session.flush()
    await state.clear()
    await message.answer("Инициатива добавлена ✅")


@router.callback_query(F.data.startswith("admin:partner:task:add:"))
async def task_start(call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext) -> None:
    await call.answer()
    if not admin_ok(user, settings, call.from_user.id):
        return
    await state.update_data(partner_id=int(call.data.rsplit(":", 1)[-1]))
    await state.set_state(PartnerAdminStates.task_title)
    await call.message.answer("Название задания:")


@router.message(PartnerAdminStates.task_title)
async def task_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=(message.text or "").strip()[:255])
    await state.set_state(PartnerAdminStates.task_description)
    await message.answer("Описание задания:")


@router.message(PartnerAdminStates.task_description)
async def task_description(message: Message, state: FSMContext) -> None:
    await state.update_data(description=(message.text or "").strip()[:2000])
    await state.set_state(PartnerAdminStates.task_points)
    await message.answer("Сколько баллов за выполнение? Числом.")


@router.message(PartnerAdminStates.task_points)
async def task_points(message: Message, state: FSMContext) -> None:
    try:
        points = max(0, int((message.text or "0").strip()))
    except ValueError:
        await message.answer("Отправьте число.")
        return
    await state.update_data(points=points)
    await state.set_state(PartnerAdminStates.task_source)
    await message.answer("Ссылка на задание или '-':")


@router.message(PartnerAdminStates.task_source)
async def task_source(message: Message, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext) -> None:
    if not admin_ok(user, settings, message.from_user.id):
        return
    data = await state.get_data()
    raw = (message.text or "").strip()
    item = PartnerTask(partner_id=int(data["partner_id"]), title=data["title"] or "Задание", description=data["description"] or "Описание уточняется", points=int(data.get("points", 0)), source_url=None if raw == "-" else raw)
    session.add(item)
    await session.flush()
    await state.clear()
    await message.answer("Задание партнёра добавлено ✅")
