"""Native Telegram broadcast composer backed by the existing durable campaign service."""
import secrets

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import User
from app.services.admin_broadcast_service import (
    BroadcastError, MAX_TEXT_LENGTH, preview_recipient_count, send_personal_broadcast,
)
from app.services.authorization_service import is_full_admin
from app.utils import texts

router = Router(name="admin_native_broadcast")
ROLES = {"participant": "Участники", "activist": "Активисты", "leader": "Лидеры",
         "head": "Руководители", "council": "Совет"}


class BroadcastCompose(StatesGroup):
    text = State()
    preview = State()


def allowed(user, settings, telegram_id):
    return bool(user and not user.is_blocked and not user.is_archived
                and user.telegram_id == telegram_id
                and is_full_admin(user, settings, telegram_id))


def choose_keyboard():
    rows = [[InlineKeyboardButton(text="Все одобренные участники",
                                  callback_data="admin:campaign:audience:all")]]
    rows += [[InlineKeyboardButton(text=label, callback_data=f"admin:campaign:audience:{role}")]
             for role, label in ROLES.items()]
    rows.append([InlineKeyboardButton(text="Отмена", callback_data="admin:campaign:compose:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("broadcast_new"))
@router.callback_query(F.data == "admin:campaign:new")
async def create_campaign(event: Message | CallbackQuery, user: User | None,
                          settings: Settings, state: FSMContext):
    telegram_id = event.from_user.id
    target = event.message if isinstance(event, CallbackQuery) else event
    if not allowed(user, settings, telegram_id):
        if isinstance(event, CallbackQuery):
            await event.answer(texts.NO_ACCESS, show_alert=True)
        else:
            await target.answer(texts.NO_ACCESS)
        return
    if isinstance(event, CallbackQuery):
        await event.answer()
    await state.clear()
    await target.answer("📨 <b>Новая рассылка</b>\n\nВыберите, кому отправить сообщение. "
                        "Рассылка не начнётся без отдельного подтверждения.",
                        parse_mode="HTML", reply_markup=choose_keyboard())


@router.callback_query(F.data.startswith("admin:campaign:audience:"))
async def choose_audience(call: CallbackQuery, user: User | None, settings: Settings,
                          state: FSMContext):
    if not allowed(user, settings, call.from_user.id):
        await call.answer(texts.NO_ACCESS, show_alert=True)
        return
    audience = call.data.rsplit(":", 1)[-1]
    if audience not in ROLES and audience != "all":
        await call.answer("Неизвестная аудитория", show_alert=True)
        return
    await call.answer()
    await state.clear()
    await state.update_data(audience="all" if audience == "all" else "role",
                            filter_value=None if audience == "all" else audience,
                            campaign_key=secrets.token_hex(16))
    await state.set_state(BroadcastCompose.text)
    await call.message.answer("Пришлите текст рассылки одним сообщением (до 3500 символов). "
                              "После этого покажу предпросмотр и число получателей.")


@router.message(BroadcastCompose.text, F.text)
async def compose_text(message: Message, user: User | None, settings: Settings,
                       session: AsyncSession, state: FSMContext):
    if not allowed(user, settings, message.from_user.id):
        await message.answer(texts.NO_ACCESS)
        return
    value = (message.text or "").strip()
    if not value or value.startswith("/") or len(value) > MAX_TEXT_LENGTH:
        await message.answer(f"Нужен обычный текст до {MAX_TEXT_LENGTH} символов.")
        return
    data = await state.get_data()
    try:
        count = await preview_recipient_count(session, data["audience"], data.get("filter_value"))
    except BroadcastError:
        await message.answer("Аудитория недоступна. Начните заново через /broadcast_new.")
        await state.clear()
        return
    await state.update_data(text=value)
    await state.set_state(BroadcastCompose.preview)
    audience_label = "Все одобренные участники" if data["audience"] == "all" else ROLES[data["filter_value"]]
    token = data["campaign_key"]
    await message.answer(
        f"📨 <b>Предпросмотр рассылки</b>\nАудитория: {audience_label}\n"
        f"Получателей сейчас: {count}\n\n{value}\n\n"
        "Перед отправкой состав аудитории будет определён заново. "
        "Telegram-пользователи, запретившие сообщения боту, могут не получить рассылку.",
        parse_mode=None,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить отправку", callback_data=f"admin:campaign:confirm:{token}")],
            [InlineKeyboardButton(text="✏️ Изменить текст", callback_data="admin:campaign:compose:edit")],
            [InlineKeyboardButton(text="Отмена", callback_data="admin:campaign:compose:cancel")],
        ]))


@router.callback_query(F.data.in_({"admin:campaign:compose:cancel", "admin:campaign:compose:edit"}))
async def compose_action(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if call.data.endswith("cancel"):
        await state.clear()
        await call.message.answer("Рассылка отменена. Сообщения не отправлены.")
    elif await state.get_state() == BroadcastCompose.preview.state:
        await state.set_state(BroadcastCompose.text)
        await call.message.answer("Отправьте исправленный текст.")


@router.callback_query(F.data.startswith("admin:campaign:confirm:"))
async def confirm_campaign(call: CallbackQuery, user: User | None, settings: Settings,
                           session: AsyncSession, state: FSMContext, bot: Bot):
    if not allowed(user, settings, call.from_user.id):
        await call.answer(texts.NO_ACCESS, show_alert=True)
        return
    data = await state.get_data()
    token = call.data.rsplit(":", 1)[-1]
    if (await state.get_state() != BroadcastCompose.preview.state or
            token != data.get("campaign_key") or not data.get("text")):
        await call.answer("Предпросмотр устарел. Создайте новую рассылку.", show_alert=True)
        return
    await call.answer()
    await state.clear()
    try:
        result = await send_personal_broadcast(
            bot, session, audience=data["audience"], filter_value=data.get("filter_value"),
            text=data["text"], author_id=user.id, settings=settings, campaign_key=token,
        )
    except BroadcastError:
        await session.rollback()
        await call.message.answer("Не удалось запустить рассылку. Проверьте раздел «Рассылки» "
                                  "перед повторной отправкой — кампания могла сохраниться.")
        return
    await call.message.answer(
        f"📨 Рассылка обработана.\nПолучателей: {result.total}\n"
        f"Доставлено: {result.sent}\nНе доставлено: {result.failed}\n"
        f"Уже обработано: {result.duplicates}\n\n"
        "Состояние и пауза — в разделе «Рассылки»."
    )
