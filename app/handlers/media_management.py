import secrets

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import User
from app.services import media_leadership_service as leadership
from app.services.media_service import media_config

router = Router(name="media_management")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


class MediaLeaderStates(StatesGroup):
    target = State()


@router.message(Command("media_calendar"))
async def calendar_command(message: Message, user: User | None, session: AsyncSession, settings: Settings):
    from app.services.media_workspace_service import require_access
    from app.utils.deep_links import miniapp_path_url
    if user is None or message.from_user.id != user.telegram_id:
        await message.answer("Сначала войдите в ЭРА и присоединитесь к медиаотделу.")
        return
    try:
        await require_access(session, user, settings)
    except PermissionError:
        await message.answer("Календарь доступен действующим участникам медиаотдела.")
        return
    if not settings.effective_miniapp_url:
        await message.answer("Мини-приложение временно недоступно.")
        return
    await message.answer("Контент-план медиаотдела\n\nВыберите направление. Время публикаций — по Еревану.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=title, web_app=WebAppInfo(url=miniapp_path_url(settings.effective_miniapp_url, f"media/{area}")))
            for area, title in (("era", "ЭРА"), ("ksoors", "КСООРС"))]]))


def keyboard(rows):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=text, callback_data=value) for text, value in row] for row in rows])


async def guard(event, user, session, settings):
    if user is None or event.from_user.id != user.telegram_id:
        await event.answer("Доступ отсутствует.")
        return False
    try:
        await leadership.require_chair(session, user, settings)
    except ValueError:
        if isinstance(event, CallbackQuery):
            await event.answer("Только председатель ЭРА может управлять руководителем медиа.", show_alert=True)
        else:
            await event.answer("Только председатель ЭРА может управлять руководителем медиа.")
        return False
    return True


@router.callback_query(F.data == "media:leader")
async def leader_menu(call: CallbackQuery, user: User | None, session: AsyncSession, settings: Settings):
    if not await guard(call, user, session, settings):
        return
    await call.answer()
    await render_leader_menu(call.message, session, settings)


async def render_leader_menu(message: Message, session: AsyncSession, settings: Settings):
    direction, _ = await leadership.leadership_state(session)
    current = await session.get(User, direction.leader_id) if direction.leader_id else None
    config = await media_config(session)
    enabled = bool(config.get("join_enabled", True))
    await message.answer(
        "Управление → Департаменты → Медиа → Руководитель\n\n"
        + (f"Руководитель: {current.first_name} {current.last_name or ''} · Telegram ID {current.telegram_id}"
           if current else "Руководитель пока не назначен.")
        + f"\nПриглашение: {'включено' if enabled else 'отключено'}.",
        reply_markup=keyboard([
            [("Назначить", "media:leader:choose"), ("Заменить", "media:leader:choose")],
            [("Снять", "media:leader:remove"), ("Посмотреть руководителя", "media:leader")],
            [("Отключить приглашение" if enabled else "Включить приглашение", f"media:invite:{'off' if enabled else 'on'}")],
        ]))


@router.message(Command("media_leader"))
@router.message(F.text == "🎬 Руководитель медиа")
async def leader_command(message: Message, user: User | None, session: AsyncSession, settings: Settings):
    if not await guard(message, user, session, settings):
        return
    await render_leader_menu(message, session, settings)


@router.callback_query(F.data == "media:leader:choose")
async def choose_leader(call: CallbackQuery, user: User | None, state: FSMContext, session: AsyncSession, settings: Settings):
    if not await guard(call, user, session, settings):
        return
    await call.answer()
    _, revision = await leadership.leadership_state(session)
    await state.set_state(MediaLeaderStates.target)
    await state.update_data(media_leader_revision=revision, media_leader_confirmation=None)
    await call.message.answer("Введите Telegram ID зарегистрированного участника. Назначение потребует подтверждения.")


@router.message(MediaLeaderStates.target, F.text.regexp(r"^[0-9]{1,20}$"))
async def receive_target(message: Message, user: User | None, state: FSMContext, session: AsyncSession, settings: Settings):
    if not await guard(message, user, session, settings):
        return
    try:
        target = await leadership.leader_target(session, int(message.text))
    except ValueError:
        await message.answer("Нужен Telegram ID действующего участника с одобренной регистрацией.")
        return
    nonce = secrets.token_hex(8)
    await state.update_data(media_leader_target=target.telegram_id, media_leader_confirmation=nonce)
    await message.answer(f"Назначить {target.first_name} {target.last_name or ''} руководителем медиа?\n"
                         f"Telegram ID: {target.telegram_id}. Доступ прежнего руководителя будет отозван.",
                         reply_markup=keyboard([[("Подтвердить назначение", f"media:leader:confirm:{nonce}")]]))


@router.callback_query(F.data == "media:leader:remove")
async def remove_leader(call: CallbackQuery, user: User | None, state: FSMContext, session: AsyncSession, settings: Settings):
    if not await guard(call, user, session, settings):
        return
    await call.answer()
    direction, revision = await leadership.leadership_state(session)
    if not direction.leader_id:
        await call.message.answer("Руководитель не назначен.")
        return
    nonce = secrets.token_hex(8)
    await state.update_data(media_leader_target=None, media_leader_revision=revision, media_leader_confirmation=nonce)
    await call.message.answer("Снять руководителя медиа? Управленческий доступ закроется сразу.",
                             reply_markup=keyboard([[("Подтвердить снятие", f"media:leader:confirm:{nonce}")]]))


@router.message(MediaLeaderStates.target, F.text, ~F.text.startswith("/"))
async def invalid_target(message: Message, user: User | None, session: AsyncSession, settings: Settings):
    if await guard(message, user, session, settings):
        await message.answer("Нужен числовой Telegram ID зарегистрированного участника. /cancel — отменить.")


@router.callback_query(F.data.startswith("media:leader:confirm:"))
async def confirm_leader(call: CallbackQuery, user: User | None, state: FSMContext, session: AsyncSession, settings: Settings, bot):
    if not await guard(call, user, session, settings):
        return
    await call.answer()
    data = await state.get_data()
    if not data.get("media_leader_confirmation") or data["media_leader_confirmation"] != call.data.rsplit(":", 1)[-1]:
        await call.message.answer("Подтверждение устарело. Откройте управление руководителем заново.")
        return
    try:
        direction, _ = await leadership.leadership_state(session)
        previous_id = direction.leader_id
        target = await leadership.change_leader(session, user, settings,
            target_telegram_id=data.get("media_leader_target"), expected_revision=data["media_leader_revision"])
    except ValueError:
        await call.message.answer("Назначение изменилось или доступ отозван. Откройте управление заново.")
        return
    await session.commit()
    await state.update_data(media_leader_confirmation=None)
    if await state.get_state() == MediaLeaderStates.target.state:
        await state.set_state(None)
    await call.message.answer("Руководитель медиа назначен." if target else "Руководитель медиа снят.")
    from app.services.notification_service import safe_send_once
    from app.utils.deep_links import miniapp_path_url
    _, revision = await leadership.leadership_state(session)
    if target:
        markup = None
        if settings.effective_miniapp_url:
            markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Управление медиа",
                web_app=WebAppInfo(url=miniapp_path_url(settings.effective_miniapp_url, "media")))]])
        await safe_send_once(bot, settings, target.telegram_id, "Вы назначены руководителем медиаотдела ЭРА.",
                            delivery_key=f"media:leader:{revision}:{target.id}", notification_type="media_leader", reply_markup=markup)
    if previous_id and (target is None or previous_id != target.id):
        previous = await session.get(User, previous_id)
        if previous:
            await safe_send_once(bot, settings, previous.telegram_id, "Полномочия руководителя медиаотдела ЭРА завершены.",
                                delivery_key=f"media:leader-ended:{revision}:{previous.id}", notification_type="media_leader")


@router.callback_query(F.data.in_({"media:invite:on", "media:invite:off"}))
async def invitation_toggle(call: CallbackQuery, user: User | None, session: AsyncSession, settings: Settings):
    if not await guard(call, user, session, settings):
        return
    await leadership.set_invitation(session, user, settings, enabled=call.data.endswith(":on"))
    await session.commit()
    await call.answer("Приглашение обновлено.")
    await leader_menu(call, user, session, settings)


async def knowledge_guard(event, user, session, settings):
    from app.services.media_workspace_service import require_access
    if user is not None and event.from_user.id == user.telegram_id:
        try:
            await require_access(session, user, settings)
            return True
        except PermissionError:
            pass
    if isinstance(event, CallbackQuery):
        await event.answer("База знаний доступна участникам медиаотдела.", show_alert=True)
    else:
        await event.answer("База знаний доступна участникам медиаотдела.")
    return False


@router.message(Command("media_knowledge"))
async def knowledge_command(message: Message, user: User | None, session: AsyncSession, settings: Settings):
    from html import escape
    from app.services.media_knowledge_service import list_items
    if not await knowledge_guard(message, user, session, settings):
        return
    query = (message.text or "").partition(" ")[2].strip().casefold()
    items = [item for item in await list_items(session) if item.kind not in {"chat", "channel"}
        and (not query or query in f"{item.title} {item.description or ''}".casefold())]
    rows = [[(item.title[:55], f"media:knowledge:{item.id}")] for item in items[:20]]
    text = "База знаний медиа\n\n" + ("Выберите материал." if items else "По запросу материалов пока нет.")
    text += "\nПоиск: /media_knowledge слово"
    if len(items) > 20:
        text += "\nПоказаны первые 20 материалов. Уточните поиск или откройте каталог в приложении."
    await message.answer(escape(text), reply_markup=keyboard(rows) if rows else None)


@router.callback_query(F.data.regexp(r"^media:knowledge:[0-9]+$"))
async def knowledge_item(call: CallbackQuery, user: User | None, session: AsyncSession, settings: Settings):
    from html import escape
    from app.database.media_models import MediaLibraryItem
    from app.services.media_knowledge_service import CATEGORIES
    if not await knowledge_guard(call, user, session, settings):
        return
    item = await session.get(MediaLibraryItem, int(call.data.rsplit(":", 1)[-1]))
    if item is None or not item.is_active or item.kind in {"chat", "channel"}:
        await call.answer("Материал скрыт или недоступен.", show_alert=True)
        return
    await call.answer()
    text = f"{item.title}\n{CATEGORIES.get(item.category, 'Рабочие материалы')}\n\n{item.description or ''}"
    for offset in range(0, len(text), 1800):
        await call.message.answer(escape(text[offset:offset + 1800]))
    if item.url.startswith("https://"):
        await call.message.answer("Ссылка на материал", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Открыть материал", url=item.url)]]))
