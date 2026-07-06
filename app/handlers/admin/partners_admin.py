from urllib.parse import urlparse

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User
from app.database.partners import Partner
from app.keyboards.partners import admin_partner_card_keyboard, admin_partners_keyboard
from app.states.partners_admin import PartnerAdminStates
from app.utils.constants import Role

router = Router(name="admin_partners")


def _admin(user: User | None) -> bool:
    return bool(user and user.role == Role.ADMIN and not user.is_blocked and not user.is_archived)


def _normalize_url(value: str) -> str | None:
    value = " ".join((value or "").split()).strip()
    if not value or len(value) > 500:
        return None
    if "://" not in value:
        value = "https://" + value
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or "." not in parsed.netloc:
        return None
    return value


def _growth_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Начислить баллы или знак", callback_data="admin:points")],
            [InlineKeyboardButton(text="Каталог возможностей", callback_data="admin:rewards")],
            [InlineKeyboardButton(text="Партнёры", callback_data="admin:partners")],
            [InlineKeyboardButton(text="Аукционы", callback_data="admin:auctions")],
            [InlineKeyboardButton(text="Портфолио и сертификаты", callback_data="admin:portfolio")],
            [InlineKeyboardButton(text="Предложения лидеров", callback_data="admin:proposals")],
            [InlineKeyboardButton(text="Назад", callback_data="admin:panel")],
        ]
    )


@router.callback_query(F.data == "admin:menu:growth")
async def admin_growth_menu(call: CallbackQuery, user: User | None) -> None:
    await call.answer()
    if not _admin(user):
        return
    await call.message.edit_text("Баллы и развитие", reply_markup=_growth_keyboard())


@router.callback_query(F.data == "admin:partners")
async def admin_partners(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    await call.answer()
    if not _admin(user):
        return
    partners = (
        await session.scalars(
            select(Partner).where(Partner.is_archived.is_(False)).order_by(Partner.name)
        )
    ).all()
    await call.message.answer(
        "🤝 Партнёры\n\nБаза партнёров, ссылок и контактов ЭРА.",
        reply_markup=admin_partners_keyboard(partners),
    )


@router.callback_query(F.data == "admin:partner:add")
async def partner_add_start(call: CallbackQuery, user: User | None, state: FSMContext) -> None:
    await call.answer()
    if not _admin(user):
        return
    await state.set_state(PartnerAdminStates.name)
    await call.message.answer("Название партнёра:")


@router.message(PartnerAdminStates.name)
async def partner_add_name(message: Message, user: User | None, state: FSMContext) -> None:
    if not _admin(user):
        return
    name = " ".join((message.text or "").split()).strip()
    if not name:
        await message.answer("Название не должно быть пустым.")
        return
    await state.update_data(name=name[:255])
    await state.set_state(PartnerAdminStates.description)
    await message.answer("Краткое описание партнёра:")


@router.message(PartnerAdminStates.description)
async def partner_add_description(message: Message, user: User | None, state: FSMContext) -> None:
    if not _admin(user):
        return
    description = (message.text or "").strip()
    if not description:
        await message.answer("Описание не должно быть пустым.")
        return
    await state.update_data(description=description[:2000])
    await state.set_state(PartnerAdminStates.source)
    await message.answer("Ссылка на источник / платформу партнёра:")


@router.message(PartnerAdminStates.source)
async def partner_add_source(message: Message, user: User | None, session: AsyncSession, state: FSMContext) -> None:
    if not _admin(user):
        return
    source_url = _normalize_url(message.text or "")
    if source_url is None:
        await message.answer("Ссылка выглядит некорректно. Пример: example.com или https://example.com")
        return
    data = await state.get_data()
    partner = Partner(
        name=data["name"],
        description=data["description"],
        source_url=source_url,
        created_by=user.id,
    )
    session.add(partner)
    await session.flush()
    await state.clear()
    await message.answer("Партнёр добавлен ✅", reply_markup=admin_partner_card_keyboard(partner.id, partner.is_active))


@router.callback_query(F.data.startswith("admin:partner:view:"))
async def partner_admin_view(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    await call.answer()
    if not _admin(user):
        return
    partner = await session.get(Partner, int(call.data.rsplit(":", 1)[-1]))
    if partner is None:
        await call.message.answer("Партнёр не найден.")
        return
    text = (
        f"🤝 {partner.name}\n\n{partner.description}\n\n"
        f"Источник: {partner.source_url}\n"
        f"Статус: {'активен' if partner.is_active else 'выключен'}"
    )
    await call.message.answer(text, reply_markup=admin_partner_card_keyboard(partner.id, partner.is_active))


@router.callback_query(F.data.startswith("admin:partner:toggle:"))
async def partner_toggle(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    await call.answer()
    if not _admin(user):
        return
    partner = await session.get(Partner, int(call.data.rsplit(":", 1)[-1]))
    if partner is None:
        return
    partner.is_active = not partner.is_active
    await session.flush()
    await call.message.answer("Статус партнёра обновлён.", reply_markup=admin_partner_card_keyboard(partner.id, partner.is_active))


@router.callback_query(F.data.startswith("admin:partner:archive:"))
async def partner_archive(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    await call.answer()
    if not _admin(user):
        return
    partner = await session.get(Partner, int(call.data.rsplit(":", 1)[-1]))
    if partner is None:
        return
    partner.is_archived = True
    partner.is_active = False
    await session.flush()
    await call.message.answer("Партнёр отправлен в архив.")


@router.callback_query(F.data.startswith("admin:partner:edit_url:"))
async def partner_edit_source_start(call: CallbackQuery, user: User | None, state: FSMContext) -> None:
    await call.answer()
    if not _admin(user):
        return
    await state.update_data(partner_id=int(call.data.rsplit(":", 1)[-1]))
    await state.set_state(PartnerAdminStates.edit_source)
    await call.message.answer("Отправьте новую ссылку на источник партнёра:")


@router.message(PartnerAdminStates.edit_source)
async def partner_edit_source_save(message: Message, user: User | None, session: AsyncSession, state: FSMContext) -> None:
    if not _admin(user):
        return
    source_url = _normalize_url(message.text or "")
    if source_url is None:
        await message.answer("Ссылка выглядит некорректно.")
        return
    data = await state.get_data()
    partner = await session.get(Partner, int(data["partner_id"]))
    if partner is None:
        await state.clear()
        await message.answer("Партнёр не найден.")
        return
    partner.source_url = source_url
    await session.flush()
    await state.clear()
    await message.answer("Ссылка обновлена ✅", reply_markup=admin_partner_card_keyboard(partner.id, partner.is_active))
