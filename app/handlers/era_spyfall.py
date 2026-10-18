"""Small group Spyfall game with private roles and a public vote."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import AppSetting, User
from app.handlers.era_game_room import (
    _data,
    _enabled,
    _lock,
    _registered,
    _save,
    _topic_link,
)
from app.services.general_topics_service import ensure_topic

router = Router(name="era_spyfall")
MIN_PLAYERS = 4
MAX_PLAYERS = 12
LOCATIONS = (
    "Университет",
    "Киноклуб",
    "Аэропорт",
    "Кафе",
    "Музей",
    "Библиотека",
    "Концерт",
    "Аквапарк",
    "Театр",
    "Книжная ярмарка",
    "Телестудия",
    "Коворкинг",
    "Гейм-центр",
    "Поезд",
    "Пляж",
    "Цирк",
    "Галерея",
    "Космическая станция",
    "Фудкорт",
    "Горнолыжный курорт",
)


def _room_key(chat_id: int, thread_id: int | None) -> str:
    return f"era_spyfall:{chat_id}:{thread_id}"


def _card(room: dict) -> tuple[str, InlineKeyboardMarkup | None]:
    players = room.get("players", {})
    members = (
        "\n".join(
            f"• {escape(players.get(str(uid), 'Участник'))}"
            + (" · личка готова" if str(uid) in room.get("private_ready", []) else "")
            for uid in room.get("participants", [])
        )
        or "Пока никого"
    )
    if room.get("status") == "finished":
        return room.get("result", "Раунд завершён."), None
    heading = "<b>🕵 Шпион</b>\n\n"
    if room.get("status") == "lobby":
        ready = len(room.get("private_ready", []))
        text = (
            heading + "Найди шпиона по вопросам о месте.\n"
            f"Игроки: {len(room.get('participants', []))}/{MAX_PLAYERS}\n"
            f"Личные сообщения: {ready}/{len(room.get('participants', []))}\n\n"
            f"{members}\n\n"
            "Каждому нужна открытая личка с ботом, чтобы получить роль."
        )
        token = room["token"]
        link = f"https://t.me/{room['bot_username']}?start=spy_{token}"
        rows = [
            [InlineKeyboardButton(text="🙋 Войти", callback_data=f"spy:join:{token}")],
            [InlineKeyboardButton(text="🚪 Выйти", callback_data=f"spy:leave:{token}")],
            [InlineKeyboardButton(text="🔓 Подключить личку", url=link)],
        ]
        if (
            room.get("creator_id") == room.get("active_user")
            and len(room.get("participants", [])) >= MIN_PLAYERS
            and ready == len(room.get("participants", []))
        ):
            rows.append(
                [
                    InlineKeyboardButton(
                        text="▶️ Начать", callback_data=f"spy:start:{token}"
                    )
                ]
            )
        return text, InlineKeyboardMarkup(inline_keyboard=rows)
    if room.get("status") == "playing":
        text = (
            heading + f"Локация известна {len(room['participants']) - 1} игрокам.\n\n"
            "Обсуждайте и задавайте друг другу вопросы. "
            "Шпиону нужно догадаться, где вы."
        )
        return text, InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🗳 Перейти к голосованию",
                        callback_data=f"spy:vote:{room['token']}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🕵 Я шпион: угадать место",
                        callback_data=f"spy:guess:{room['token']}",
                    )
                ],
            ]
        )
    if room.get("status") == "voting":
        votes = room.get("votes", {})
        text = (
            heading + f"Кто шпион? Голоса: {len(votes)}/{len(room['participants'])}\n\n"
            f"{members}"
        )
        buttons = [
            [
                InlineKeyboardButton(
                    text=players.get(str(uid), "Участник")[:35],
                    callback_data=f"spy:pick:{room['token']}:{index}",
                )
            ]
            for index, uid in enumerate(room["participants"])
        ]
        return text, InlineKeyboardMarkup(inline_keyboard=buttons)
    return heading + "Раунд не найден.", None


async def _update(bot, room: dict) -> None:
    text, markup = _card(room)
    if room.get("message_id"):
        await bot.edit_message_text(
            chat_id=room["chat_id"],
            message_id=room["message_id"],
            text=text,
            reply_markup=markup,
            parse_mode="HTML",
        )


async def _get_room(
    session: AsyncSession, chat_id: int, thread_id: int | None, *, lock: bool = False
):
    key = _room_key(chat_id, thread_id)
    if lock:
        await _lock(session, key)
    row = await session.scalar(
        select(AppSetting).where(AppSetting.key == key).with_for_update()
    )
    return key, _data(row)


async def _can_play(
    message: Message,
    settings: Settings,
    user: User | None,
    telegram_id: int | None = None,
) -> bool:
    player_id = telegram_id or (message.from_user.id if message.from_user else 0)
    return bool(
        player_id
        and message.chat.id == settings.general_chat_id
        and message.message_thread_id
        and _enabled(settings, player_id)
        and _registered(user, player_id)
        and await ensure_topic(message.bot, settings, "games")
        == message.message_thread_id
    )


async def _create(
    message: Message,
    settings: Settings,
    session: AsyncSession,
    user: User | None,
    actor_id: int | None = None,
    actor_name: str | None = None,
) -> None:
    if not await _can_play(message, settings, user, actor_id):
        return
    key, current = await _get_room(
        session, message.chat.id, message.message_thread_id, lock=True
    )
    now = datetime.now(timezone.utc)
    if current.get("status") in {"lobby", "playing", "voting"} and current.get(
        "expires_at"
    ):
        if datetime.fromisoformat(current["expires_at"]) > now:
            await message.answer("В теме уже идёт игра. Подключайся к текущему раунду.")
            return
    token = secrets.token_hex(5)
    creator = actor_id or message.from_user.id
    room = {
        "id": key,
        "token": token,
        "status": "lobby",
        "chat_id": message.chat.id,
        "thread_id": message.message_thread_id,
        "creator_id": creator,
        "active_user": creator,
        "bot_username": settings.bot_username or "ERA_1bot",
        "participants": [creator],
        "players": {str(creator): (actor_name or message.from_user.full_name)[:45]},
        "private_ready": [],
        "votes": {},
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=15)).isoformat(),
    }
    await _save(session, key, room)
    await session.commit()
    text, markup = _card(room)
    sent = await message.answer(text, reply_markup=markup, parse_mode="HTML")
    room["message_id"] = sent.message_id
    await _save(session, key, room)
    await session.commit()


@router.message(Command("spy"))
async def spy_command(
    message: Message,
    settings: Settings,
    session: AsyncSession,
    user: User | None = None,
):
    if message.chat.type == "private":
        await message.answer("Открой «Шпион» из темы «Интерактив» в общем чате.")
        return
    if message.chat.id != settings.general_chat_id or not message.from_user:
        return
    topic_id = await ensure_topic(message.bot, settings, "games")
    if topic_id and message.message_thread_id != topic_id:
        url = _topic_link(settings, topic_id)
        await message.answer(
            "Запусти «Шпиона» в теме «Интерактив».",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="Открыть игры", url=url)]]
            ),
        )
        return
    await _create(message, settings, session, user)


@router.callback_query(F.data == "era_spyfall:create")
async def spy_menu_callback(
    query: CallbackQuery,
    settings: Settings,
    session: AsyncSession,
    user: User | None = None,
):
    if not isinstance(query.message, Message) or not await _can_play(
        query.message, settings, user, query.from_user.id if query.from_user else None
    ):
        await query.answer(
            "Шпион запускается в теме «Интерактив» для участников ЭРА.", show_alert=True
        )
        return
    await query.answer()
    await _create(
        query.message,
        settings,
        session,
        user,
        query.from_user.id,
        query.from_user.full_name,
    )


async def activate_private(
    message: Message, payload: str, session: AsyncSession, user: User | None = None
) -> bool:
    """Record a player opening the bot from the Spyfall deep link."""
    if not payload.startswith("spy_") or not message.from_user:
        return False
    token = payload[4:]
    if not _registered(user, message.from_user.id):
        await message.answer("Для роли в игре нужна одобренная регистрация в ЭРА.")
        return True
    rows = (
        await session.scalars(
            select(AppSetting).where(AppSetting.key.like("era_spyfall:%"))
        )
    ).all()
    for row in rows:
        room = _data(row)
        if room.get("token") != token or room.get("status") != "lobby":
            continue
        if message.from_user.id not in room.get("participants", []):
            await message.answer(
                "Сначала войди в лобби «Шпион» по кнопке в общем чате."
            )
            return True
        ready = room.setdefault("private_ready", [])
        if str(message.from_user.id) not in ready:
            ready.append(str(message.from_user.id))
            room["active_user"] = room.get("creator_id")
            await _save(session, row.key, room)
            await session.commit()
            await _update(message.bot, room)
        await message.answer(
            "Личка готова. Вернись в общий чат — бот пришлёт сюда "
            "твою роль после старта."
        )
        return True
    await message.answer("Это лобби уже закрыто. Открой новое через /spy в общем чате.")
    return True


@router.callback_query(F.data.startswith("spy:") & ~F.data.startswith("spy:answer:"))
async def spy_callback(
    query: CallbackQuery,
    settings: Settings,
    session: AsyncSession,
    user: User | None = None,
):
    if not isinstance(query.message, Message) or not query.from_user:
        await query.answer()
        return
    parts = (query.data or "").split(":")
    token = parts[2] if len(parts) > 2 else ""
    key, room = await _get_room(
        session, query.message.chat.id, query.message.message_thread_id, lock=True
    )
    if not room or room.get("token") != token or room.get("status") == "finished":
        await query.answer("Раунд уже закрыт.", show_alert=True)
        return
    if room.get("expires_at") and datetime.fromisoformat(
        room["expires_at"]
    ) <= datetime.now(timezone.utc):
        room.update(
            status="finished",
            result="⏱ Раунд завершён по времени. Запустите новую игру через /spy.",
        )
        await _save(session, key, room)
        await session.commit()
        await _update(query.bot, room)
        await query.answer("Время раунда истекло.", show_alert=True)
        return
    uid = query.from_user.id
    room["active_user"] = uid
    if parts[1] == "join":
        if not _registered(user, uid):
            await query.answer(
                "Для игры нужна одобренная регистрация в ЭРА.", show_alert=True
            )
            return
        if room["status"] != "lobby" or uid in room["participants"]:
            await query.answer("Ты уже в игре или раунд начался.")
            return
        if len(room["participants"]) >= MAX_PLAYERS:
            await query.answer("Лобби заполнено.", show_alert=True)
            return
        room["participants"].append(uid)
        room["players"][str(uid)] = query.from_user.full_name[:45]
        await _save(session, key, room)
        await session.commit()
        await _update(query.bot, room)
        await query.answer("Ты в лобби!")
        return
    if parts[1] == "leave" and room.get("status") == "lobby":
        if uid not in room["participants"]:
            await query.answer("Ты не в лобби.")
            return
        room["participants"] = [
            player for player in room["participants"] if player != uid
        ]
        room["private_ready"] = [
            player for player in room.get("private_ready", []) if player != str(uid)
        ]
        room.get("players", {}).pop(str(uid), None)
        if not room["participants"]:
            room.update(status="finished", result="Лобби закрыто.")
        elif uid == room.get("creator_id"):
            room["creator_id"] = room["participants"][0]
            room["active_user"] = room["creator_id"]
        await _save(session, key, room)
        await session.commit()
        await _update(query.bot, room)
        await query.answer("Ты вышел из лобби.")
        return
    if uid not in room.get("participants", []):
        await query.answer("Ты не участник этого раунда.", show_alert=True)
        return
    if parts[1] == "start":
        ready = room.get("private_ready", [])
        if uid != room.get("creator_id"):
            await query.answer("Начать может создатель лобби.", show_alert=True)
            return
        if len(room["participants"]) < MIN_PLAYERS or len(ready) != len(
            room["participants"]
        ):
            await query.answer(
                "Нужно 4 игрока и открытая личка у каждого.", show_alert=True
            )
            return
        spy = secrets.choice(room["participants"])
        location = secrets.choice(LOCATIONS)
        for player in room["participants"]:
            role = (
                "🕵 Ты шпион. Узнай локацию, не выдав себя!"
                if player == spy
                else f"📍 Локация: <b>{escape(location)}</b>"
            )
            try:
                await query.bot.send_message(
                    player, f"<b>Твоя роль · Шпион</b>\n\n{role}", parse_mode="HTML"
                )
            except TelegramAPIError:
                room["status"] = "finished"
                room["result"] = (
                    "Раунд отменён: не удалось отправить роли. Откройте бота "
                    "по кнопке лички и начните новый раунд."
                )
                await _save(session, key, room)
                await session.commit()
                await _update(query.bot, room)
                await query.answer(
                    "Не удалось доставить роль. Раунд отменён.", show_alert=True
                )
                return
        room.update(
            status="playing",
            spy_id=spy,
            location=location,
            votes={},
            active_user=None,
            expires_at=(datetime.now(timezone.utc) + timedelta(minutes=8)).isoformat(),
        )
        await _save(session, key, room)
        await session.commit()
        await _update(query.bot, room)
        await query.answer("Игра началась!")
        return
    if parts[1] == "vote" and room.get("status") == "playing":
        room.update(status="voting", votes={}, active_user=None)
        await _save(session, key, room)
        await session.commit()
        await _update(query.bot, room)
        await query.answer("Голосование началось")
        return
    if parts[1] == "pick" and room.get("status") == "voting":
        if str(uid) in room.get("votes", {}):
            await query.answer("Твой голос уже учтён.")
            return
        try:
            target = room["participants"][int(parts[3])]
        except (ValueError, IndexError):
            await query.answer("Кнопка устарела.", show_alert=True)
            return
        room.setdefault("votes", {})[str(uid)] = target
        if len(room["votes"]) == len(room["participants"]):
            counts = {
                player: list(room["votes"].values()).count(player)
                for player in room["participants"]
            }
            top = max(counts.values())
            suspects = [player for player, count in counts.items() if count == top]
            caught = len(suspects) == 1 and suspects[0] == room.get("spy_id")
            if room.get("spy_guessed"):
                result = (
                    f"🏆 Шпион угадал локацию и победил! "
                    f"Это было: {escape(room['location'])}."
                )
            elif caught:
                spy_name = escape(room["players"].get(str(room["spy_id"]), "игрок"))
                result = (
                    f"🎉 Шпиона нашли! Это был {spy_name}. "
                    f"Локация: {escape(room['location'])}."
                )
            else:
                spy_name = escape(room["players"].get(str(room["spy_id"]), "игрок"))
                result = (
                    f"🕵 Шпион победил! Это был {spy_name}. "
                    f"Локация: {escape(room['location'])}."
                )
            room.update(status="finished", result=result)
        await _save(session, key, room)
        await session.commit()
        await _update(query.bot, room)
        await query.answer("Голос принят.")
        return
    if parts[1] == "guess" and room.get("status") in {"playing", "voting"}:
        if uid != room.get("spy_id"):
            await query.answer("Эта кнопка только для шпиона.", show_alert=True)
            return
        buttons = [
            [
                InlineKeyboardButton(
                    text=location, callback_data=f"spy:answer:{token}:{index}"
                )
            ]
            for index, location in enumerate(LOCATIONS)
        ]
        await query.bot.send_message(
            uid,
            "🕵 Выбери локацию:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )
        await query.answer("Проверь личные сообщения.")
        return
    await query.answer()


@router.callback_query(F.data.startswith("spy:answer:"))
async def spy_guess_callback(query: CallbackQuery, session: AsyncSession):
    if not query.from_user:
        await query.answer()
        return
    _, _, token, raw_index = (query.data or "").split(":", 3)
    rows = (
        await session.scalars(
            select(AppSetting).where(AppSetting.key.like("era_spyfall:%"))
        )
    ).all()
    for row in rows:
        room = _data(row)
        if room.get("token") != token or room.get("spy_id") != query.from_user.id:
            continue
        if room.get("expires_at") and datetime.fromisoformat(
            room["expires_at"]
        ) <= datetime.now(timezone.utc):
            room.update(
                status="finished",
                result="⏱ Раунд завершён по времени. Запустите новую игру через /spy.",
            )
            await _save(session, row.key, room)
            await session.commit()
            await _update(query.bot, room)
            await query.answer("Время раунда истекло.", show_alert=True)
            return
        try:
            guess = LOCATIONS[int(raw_index)]
        except (ValueError, IndexError):
            await query.answer("Кнопка устарела.", show_alert=True)
            return
        correct = guess == room.get("location")
        room["spy_guessed"] = correct
        room.update(
            status="finished",
            result=(
                "🏆 Шпион угадал локацию и победил! "
                f"Это было: {escape(room['location'])}."
                if correct
                else "🎉 Шпион ошибся с локацией. Победила команда! "
                f"Место было: {escape(room['location'])}."
            ),
        )
        await _save(session, row.key, room)
        await session.commit()
        await _update(query.bot, room)
        await query.answer(
            "Верно! Ты победил." if correct else "Не угадал. Команда победила.",
            show_alert=True,
        )
        return
    await query.answer("Раунд уже закрыт.", show_alert=True)
