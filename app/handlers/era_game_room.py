"""Telegram-only game-room pilot: no public empty-room counters or fake players.

All gameplay is restricted to the configured general-chat forum topic.
Feature is OFF by default until end-to-end validation and content expansion.
"""
from __future__ import annotations

import hashlib
import json
import logging
import secrets
import asyncio
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select, text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import AppSetting
from app.services.game_content import GameItem, QUIZ_QUESTIONS, items_for_mode
from app.services.game_formats import GameMode, check_answer, score_answer
from app.services.general_topics_service import ensure_topic
from app.services.game_rewards_service import award_game_points

logger = logging.getLogger(__name__)
router = Router(name="era_game_room")
MIN_PLAYERS = 2
MAX_PLAYERS = 8
WAIT_SECONDS = 180
READY_SECONDS = 20

QUESTIONS = QUIZ_QUESTIONS


def menu_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡ Быстрый квиз", callback_data="era_game:solo")],
        [InlineKeyboardButton(text="🤝 Собрать команду", callback_data="era_game:team")],
        [InlineKeyboardButton(text="✅ Правда или миф", callback_data="era_game:play:true_or_myth")],
        [InlineKeyboardButton(text="🌍 Угадай страну", callback_data="era_game:play:guess_country")],
        [InlineKeyboardButton(text="🕰 Хронология", callback_data="era_game:play:chronology")],
        [InlineKeyboardButton(text="🔤 Словесная цепочка", callback_data="era_game:play:word_chain")],
        [InlineKeyboardButton(text="💭 Ассоциации", callback_data="era_game:play:associations")],
        [InlineKeyboardButton(text="🧠 Логика", callback_data="era_game:play:logic")],
        [InlineKeyboardButton(text="🎭 Культурный блиц", callback_data="era_game:play:culture")],
        [InlineKeyboardButton(text="🧩 Память", callback_data="era_game:play:memory")],
        [InlineKeyboardButton(text="🏆 Командная дуэль", callback_data="era_game:duel")],
        [InlineKeyboardButton(text="↩️ Продолжить игру", callback_data="era_game:resume")],
        [InlineKeyboardButton(text="📚 Правила", callback_data="era_game:rules")],
    ])


def lobby_markup(room_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🙋 Присоединиться", callback_data=f"era_game:join:{room_id}")],
        [InlineKeyboardButton(text="🚪 Выйти", callback_data=f"era_game:leave:{room_id}")],
    ])


def ready_markup(reference: str) -> InlineKeyboardMarkup:
    keyboard = lobby_markup(reference)
    keyboard.inline_keyboard.insert(0, [InlineKeyboardButton(text="✅ Готов играть", callback_data=f"era_game:ready:{reference}")])
    return keyboard


def duel_markup(reference: str, *, ready: bool = False) -> InlineKeyboardMarkup:
    if ready:
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Готов играть", callback_data=f"era_game:ready:{reference}")
        ], [InlineKeyboardButton(text="🚪 Выйти", callback_data=f"era_game:leave:{reference}")]])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔴 В команду А", callback_data=f"era_game:duel_join:{reference}:A")],
        [InlineKeyboardButton(text="🔵 В команду Б", callback_data=f"era_game:duel_join:{reference}:B")],
        [InlineKeyboardButton(text="🚪 Выйти", callback_data=f"era_game:leave:{reference}")],
    ])


def quiz_markup(room_id: str, options: tuple[str, ...]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=option, callback_data=f"era_game:answer:{room_id}:{index}")]
        for index, option in enumerate(options)
    ])


def format_markup(reference: str, item: GameItem, *, hints_used: int = 0) -> InlineKeyboardMarkup:
    keyboard = [[InlineKeyboardButton(
        text=option[:60], callback_data=f"era_game:format_answer:{reference}:{index}"
    )] for index, option in enumerate(item.challenge.options)]
    if item.challenge.hints and hints_used < len(item.challenge.hints):
        keyboard.append([InlineKeyboardButton(
            text=f"💡 Подсказка {hints_used + 1}/{len(item.challenge.hints)}",
            callback_data=f"era_game:hint:{reference}",
        )])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


async def _reserve_format_item(
    session: AsyncSession, *, mode: GameMode, user_id: int, now: datetime
) -> GameItem | None:
    """Reserve the next source-backed item for one user and format for 180 days."""
    items = items_for_mode(mode)
    usage_key = f"era_game:content_usage:{mode.value}:{user_id}"
    await _lock(session, usage_key)
    row = await session.scalar(select(AppSetting).where(AppSetting.key == usage_key).with_for_update())
    usage = _data(row)
    cutoff = now - timedelta(days=180)
    active: set[str] = set()
    cleaned: dict[str, str] = {}
    for item_id, timestamp in usage.items():
        try:
            used_at = datetime.fromisoformat(timestamp)
            if used_at.tzinfo is None:
                used_at = used_at.replace(tzinfo=timezone.utc)
            if used_at > cutoff:
                active.add(str(item_id))
                cleaned[str(item_id)] = used_at.isoformat()
        except (TypeError, ValueError):
            logger.warning("Invalid game content reservation %s", item_id)
    item = next((candidate for candidate in items if candidate.id not in active), None)
    if item is None:
        await _save(session, usage_key, cleaned)
        return None
    cleaned[item.id] = now.isoformat()
    await _save(session, usage_key, cleaned)
    return item


def _format_item(room: dict) -> GameItem | None:
    try:
        mode = GameMode(room["mode"])
    except (KeyError, ValueError):
        return None
    return next((item for item in items_for_mode(mode) if item.id == room.get("item_id")), None)


def _format_prompt(room: dict) -> tuple[str, InlineKeyboardMarkup | None] | None:
    item = _format_item(room)
    if item is None:
        return None
    challenge = item.challenge
    text = f"{challenge.prompt}\n\n<i>Тема: {item.category}</i>"
    if challenge.mode == GameMode.MEMORY:
        if not room.get("memory_revealed"):
            return (
                f"{challenge.prompt}\n\n<i>Запомни последовательность: она будет показана 5 секунд.</i>",
                None,
            )
        instruction = challenge.prompt.split(":", 1)[0].rstrip()
        text = f"🧩 <b>Память</b>\n{instruction}\n\nПоследовательность скрыта. Какой она была?"
    reference = f"{room['id']}~{room['token']}"
    return text, format_markup(reference, item, hints_used=room.get("hints_used", 0))


async def _reveal_memory(
    session: AsyncSession, *, key: str, token: str, message: Message, sent: Message | None = None
) -> bool:
    """Persist the recall phase before exposing answer buttons; safe across restarts."""
    await _lock(session, key)
    row = await session.scalar(select(AppSetting).where(AppSetting.key == key).with_for_update())
    room = _data(row)
    now = datetime.now(timezone.utc)
    if not room or room.get("token") != token or room.get("status") != "playing":
        return False
    if datetime.fromisoformat(room["expires_at"]) <= now:
        room["status"] = "expired"
        await _save(session, key, room)
        await session.commit()
        return False
    room["memory_revealed"] = True
    await _save(session, key, room)
    await session.commit()
    rendered = _format_prompt(room)
    if rendered is None:
        return False
    text, markup = rendered
    if sent is not None:
        await sent.edit_text(text, reply_markup=markup, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=markup, parse_mode="HTML")
    return True


async def _start_format(query: CallbackQuery, settings: Settings, session: AsyncSession,
                        message: Message, mode_value: str) -> None:
    try:
        mode = GameMode(mode_value)
    except ValueError:
        await query.answer("Неизвестный формат.", show_alert=True)
        return
    if mode in {GameMode.SOLO_QUIZ, GameMode.TEAM_QUIZ, GameMode.TEAM_DUEL}:
        await query.answer("Этот формат запускается отдельно.", show_alert=True)
        return
    uid = query.from_user.id
    room_id = f"f{list(GameMode).index(mode)}-{uid}"
    key = _key(message.chat.id, message.message_thread_id, room_id)
    await _lock(session, key)
    row = await session.scalar(select(AppSetting).where(AppSetting.key == key).with_for_update())
    current = _data(row)
    now = datetime.now(timezone.utc)
    if current.get("status") == "playing" and datetime.fromisoformat(current["expires_at"]) > now:
        await query.answer("Игра уже открыта. Нажми «Продолжить игру».", show_alert=True)
        return
    item = await _reserve_format_item(session, mode=mode, user_id=uid, now=now)
    if item is None:
        await session.commit()
        await query.answer("Задания этого формата пока закончились. История повторов сохранена.", show_alert=True)
        return
    token = secrets.token_hex(6)
    room = {
        "id": room_id, "token": token, "session_token": token,
        "mode": mode.value, "item_id": item.id, "status": "playing",
        "participants": [uid], "answers": {}, "scores": {}, "hints_used": 0,
        "created_at": now.isoformat(), "expires_at": (now + timedelta(minutes=5)).isoformat(),
    }
    if mode == GameMode.MEMORY:
        room["memory_revealed"] = False
        room["memory_ready_at"] = (now + timedelta(seconds=5)).isoformat()
    await _save(session, key, room)
    await session.commit()
    rendered = _format_prompt(room)
    if rendered is None:
        await query.answer("Материал игры недоступен.", show_alert=True)
        return
    text, markup = rendered
    if mode == GameMode.MEMORY:
        sent = await message.answer(text, parse_mode="HTML")
        await query.answer("Запоминай последовательность.")
        await asyncio.sleep(5)
        await _reveal_memory(session, key=key, token=token, message=message, sent=sent)
        return
    await message.answer(text, reply_markup=markup, parse_mode="HTML")
    await query.answer()


async def _format_action(query: CallbackQuery, settings: Settings, session: AsyncSession, message: Message,
                         action: list[str]) -> bool:
    operation = action[1]
    if operation not in {"format_answer", "hint"}:
        return False
    expected_parts = 4 if operation == "format_answer" else 3
    if len(action) != expected_parts:
        await query.answer("Эта кнопка устарела.", show_alert=True)
        return True
    reference = action[2]
    room_id, sep, token = reference.partition("~")
    if not sep or not token:
        await query.answer("Эта кнопка устарела.", show_alert=True)
        return True
    key = _key(message.chat.id, message.message_thread_id, room_id)
    await _lock(session, key)
    row = await session.scalar(select(AppSetting).where(AppSetting.key == key).with_for_update())
    room = _data(row)
    now = datetime.now(timezone.utc)
    if not room or room.get("token") != token or room.get("status") != "playing":
        await query.answer("Раунд уже завершён.", show_alert=True)
        return True
    if datetime.fromisoformat(room["expires_at"]) <= now:
        room["status"] = "expired"
        await _save(session, key, room)
        await session.commit()
        await query.answer("Время раунда истекло.", show_alert=True)
        return True
    uid = query.from_user.id
    if uid not in room.get("participants", []):
        await query.answer("Ты не участник этого раунда.", show_alert=True)
        return True
    item = _format_item(room)
    if item is None:
        await query.answer("Материал игры недоступен.", show_alert=True)
        return True
    if item.challenge.mode == GameMode.MEMORY and not room.get("memory_revealed"):
        await query.answer("Сначала запомни последовательность.", show_alert=True)
        return True
    if operation == "hint":
        hints = item.challenge.hints
        hints_used = room.get("hints_used", 0)
        if hints_used >= len(hints):
            await query.answer("Подсказки закончились.", show_alert=True)
            return True
        hint = hints[hints_used]
        room["hints_used"] = hints_used + 1
        await _save(session, key, room)
        await session.commit()
        await query.answer(f"Подсказка {hints_used + 1}: {hint}", show_alert=True)
        try:
            await message.edit_reply_markup(
                reply_markup=format_markup(reference, item, hints_used=room["hints_used"])
            )
        except TelegramAPIError:
            logger.info("Could not refresh the game hint button for %s", room_id)
        return True
    if room.get("answers", {}).get(str(uid)) is not None:
        await query.answer("Ответ уже принят.", show_alert=True)
        return True
    try:
        choice = int(action[3])
    except ValueError:
        await query.answer("Ответ не распознан.", show_alert=True)
        return True
    if choice not in range(len(item.challenge.options)):
        await query.answer("Такого варианта нет.", show_alert=True)
        return True
    selected = item.challenge.options[choice]
    correct = check_answer(item.challenge, selected, previous_word=item.previous_word)
    score = score_answer(item.challenge, selected, hints_used=room.get("hints_used", 0),
                         previous_word=item.previous_word)
    room.setdefault("answers", {})[str(uid)] = choice
    room.setdefault("scores", {})[str(uid)] = score
    room["status"] = "finished"
    room["finished_at"] = now.isoformat()
    if correct and settings.games_rewards_enabled:
        await award_game_points(session, telegram_id=uid, round_id=room["session_token"], amount=score)
    await _save(session, key, room)
    await session.commit()
    result = "✅ Верно!" if correct else f"❌ Пока неверно. Ответ: <b>{item.challenge.answer}</b>."
    if item.challenge.explanation:
        result += f"\n\nℹ️ {item.challenge.explanation}"
    result += f"\n\nОчки за раунд: {score}."
    await query.answer("Ответ принят.")
    await message.answer(result, parse_mode="HTML")
    return True


def _enabled(settings: Settings, telegram_id: int) -> bool:
    mode = settings.feature_games
    return mode == "ALL" or (mode == "TESTERS" and telegram_id in settings.feature_tester_ids)


async def _allowed(settings: Settings, message: Message, telegram_id: int) -> bool:
    if not _enabled(settings, telegram_id) or not settings.general_chat_id:
        return False
    if message.chat.id != settings.general_chat_id:
        return False
    thread_id = await ensure_topic(message.bot, settings, "games")
    return bool(thread_id and message.message_thread_id == thread_id)


def _key(chat_id: int, thread_id: int, room_id: str) -> str:
    return f"era_game:{chat_id}:{thread_id}:{room_id}"


async def _save(session: AsyncSession, key: str, data: dict) -> None:
    row = await session.scalar(select(AppSetting).where(AppSetting.key == key))
    if row is None:
        session.add(AppSetting(key=key, value=json.dumps(data)))
    else:
        row.value = json.dumps(data)
    await session.flush()


async def _lock(session: AsyncSession, key: str) -> None:
    if session.bind.dialect.name == "postgresql":
        digest = hashlib.sha256(key.encode()).digest()
        lock_id = int.from_bytes(digest[:8], "big", signed=True)
        await session.execute(sql_text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})


def _data(row: AppSetting | None) -> dict:
    if not row:
        return {}
    return json.loads(row.value) if isinstance(row.value, str) else row.value


async def _reserve_questions(
    session: AsyncSession,
    now: datetime,
    count: int,
    *,
    user_ids: tuple[int, ...] | list[int] = (),
    mode: str = "solo_quiz",
) -> list[int]:
    """Reserve a question pack without repeating it for any participant.

    History is scoped to both user and format. For a team, the selected pack
    must be available to every member, then the same reservation is written to
    each member's history. The legacy global key is read only by old call sites
    and migration-era tests that do not identify a player.
    """
    usage_keys = (
        [f"era_game:question_usage:{mode}:{user_id}" for user_id in sorted(set(user_ids))]
        if user_ids
        else ["era_game:question_usage"]
    )
    for used_key in usage_keys:
        await _lock(session, used_key)
    rows = await session.scalars(
        select(AppSetting).where(AppSetting.key.in_(usage_keys)).with_for_update()
    )
    usage_by_key = {key: {} for key in usage_keys}
    usage_by_key.update({row.key: _data(row) for row in rows})
    cutoff = now - timedelta(days=180)
    active_by_key: dict[str, dict[str, str]] = {}
    for used_key, used in usage_by_key.items():
        active: dict[str, str] = {}
        for question_id, timestamp in used.items():
            try:
                when = datetime.fromisoformat(timestamp)
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
                if when > cutoff:
                    active[str(int(question_id))] = when.isoformat()
            except (TypeError, ValueError):
                logger.warning("Invalid game reservation entry %s", question_id)
        active_by_key[used_key] = active
    unavailable = {
        int(question_id)
        for active in active_by_key.values()
        for question_id in active
    }
    available = [i for i in range(len(QUESTIONS)) if i not in unavailable]
    if len(available) < count:
        return []
    chosen = available[:count]
    for used_key, used in active_by_key.items():
        for index in chosen:
            used[str(index)] = now.isoformat()
        await _save(session, used_key, used)
    return chosen


async def _reserve_question(
    session: AsyncSession, now: datetime, *, user_id: int | None = None, mode: str = "solo_quiz"
) -> int | None:
    questions = await _reserve_questions(
        session, now, 1, user_ids=() if user_id is None else (user_id,), mode=mode
    )
    return questions[0] if questions else None


async def _new_room(session: AsyncSession, *, chat_id: int, thread_id: int,
                    user_id: int, kind: str, questions_per_game: int = 1) -> dict | None:
    if not 1 <= questions_per_game <= 10:
        raise ValueError("questions_per_game must be between 1 and 10")
    # One public lobby per topic; solo rounds have a per-user key.
    room_id = "team" if kind == "team" else "duel" if kind == "duel" else f"solo-{user_id}"
    key = _key(chat_id, thread_id, room_id)
    await _lock(session, key)
    row = await session.scalar(select(AppSetting).where(AppSetting.key == key).with_for_update())
    current = _data(row)
    now = datetime.now(timezone.utc)
    if current.get("status") in {"waiting", "ready_check", "playing"}:
        if current.get("expires_at") and datetime.fromisoformat(current["expires_at"]) > now:
            return None
    questions = (
        await _reserve_questions(
            session, now, questions_per_game, user_ids=(user_id,), mode="solo_quiz"
        )
        if kind == "solo"
        else []
    )
    if kind == "solo" and not questions:
        return {"status": "exhausted"}
    token = secrets.token_hex(6)
    data = {
        "token": token, "session_token": token,
        "questions": questions, "question_count": questions_per_game,
        "position": 0, "scores": {}, "ready": [],
        "lobby_deadline": (now + timedelta(seconds=WAIT_SECONDS)).isoformat(),
        "id": room_id, "kind": kind, "status": "waiting" if kind in {"team", "duel"} else "playing",
        "participants": [user_id], "teams": {str(user_id): "A"} if kind == "duel" else {},
        "team_scores": {"A": 0, "B": 0} if kind == "duel" else {},
        "answers": {}, "question": questions[0] if questions else None,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=WAIT_SECONDS if kind == "team" else 120)).isoformat(),
    }
    await _save(session, key, data)
    return data


@router.message(Command("games", "game"))
async def game_menu(message: Message, settings: Settings):
    if not message.from_user or not await _allowed(settings, message, message.from_user.id):
        return
    await message.answer("🎮 <b>ЭРА | Интерактив</b>\n\nВыбирай игру. Можно начать одному или собрать небольшую команду.", reply_markup=menu_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("era_game:"))
async def game_callback(query: CallbackQuery, settings: Settings, session: AsyncSession):
    if not isinstance(query.message, Message) or not query.from_user or query.from_user.is_bot:
        await query.answer()
        return
    message = query.message
    if not await _allowed(settings, message, query.from_user.id):
        await query.answer("Игры доступны только в теме «Интерактив».", show_alert=True)
        return
    action = (query.data or "").split(":")
    if len(action) < 2:
        await query.answer()
        return
    if action[1] == "play" and len(action) == 3:
        await _start_format(query, settings, session, message, action[2])
        return
    if action[1] == "duel" and len(action) == 2:
        room = await _new_room(
            session, chat_id=message.chat.id, thread_id=message.message_thread_id,
            user_id=query.from_user.id, kind="duel", questions_per_game=5,
        )
        await session.commit()
        if room is None:
            await query.answer("Командная дуэль уже собирается.", show_alert=True)
            return
        await message.answer(
            "🏆 <b>Командная дуэль</b>\nСоберите две команды. В каждой — от 1 до 4 игроков. "
            "Обе команды выбирают сторону и подтверждают готовность.",
            parse_mode="HTML", reply_markup=duel_markup("duel~" + room["token"]),
        )
        await query.answer()
        return
    if await _format_action(query, settings, session, message, action):
        return
    if action[1] == "rules":
        rewards = "3 балла за 60% верных ответов; +2 единственному победителю команды. Лимиты: 20/день, 100/неделю, 300/месяц." if settings.games_rewards_enabled else "В тестовом режиме начисление баллов выключено."
        await query.answer("Квиз: 5 вопросов. За ожидание и незавершённую игру баллы не начисляются. " + rewards, show_alert=True)
        return
    if action[1] == "resume":
        for room_id in (f"solo-{query.from_user.id}", "team", "duel"):
            key = _key(message.chat.id, message.message_thread_id, room_id)
            row = await session.scalar(select(AppSetting).where(AppSetting.key == key))
            room = _data(row)
            if query.from_user.id not in room.get("participants", []):
                continue
            if room.get("status") not in {"waiting", "ready_check", "playing"}:
                continue
            if datetime.fromisoformat(room["expires_at"]) <= datetime.now(timezone.utc):
                continue
            reference = room_id + "~" + room["token"]
            if room["status"] == "playing":
                question, options, _ = QUESTIONS[room["question"]]
                await message.answer(f"🎯 Вопрос {room.get('position', 0)+1}/{len(room.get('questions', [room['question']]))}\n\n{question}",
                                     reply_markup=quiz_markup(reference, options))
            elif room.get("kind") == "duel":
                await message.answer("🏆 Твоя командная дуэль", reply_markup=duel_markup(
                    reference, ready=room["status"] == "ready_check"))
            else:
                markup = ready_markup(reference) if room["status"] == "ready_check" else lobby_markup(reference)
                await message.answer("🤝 Твоя командная игра", reply_markup=markup)
            await query.answer("Игра открыта.")
            return
        prefix = f"era_game:{message.chat.id}:{message.message_thread_id}:f%"
        rows = await session.scalars(select(AppSetting).where(AppSetting.key.like(prefix)))
        for row in rows:
            room = _data(row)
            if query.from_user.id not in room.get("participants", []) or room.get("status") != "playing":
                continue
            if datetime.fromisoformat(room["expires_at"]) <= datetime.now(timezone.utc):
                continue
            item = _format_item(room)
            if item is not None and item.challenge.mode == GameMode.MEMORY and not room.get("memory_revealed"):
                ready_at = datetime.fromisoformat(room.get("memory_ready_at", datetime.now(timezone.utc).isoformat()))
                remaining = max(0.0, (ready_at - datetime.now(timezone.utc)).total_seconds())
                if remaining:
                    sent = await message.answer(
                        f"{item.challenge.prompt}\n\n<i>Запомни последовательность: она будет показана 5 секунд.</i>",
                        parse_mode="HTML",
                    )
                    await query.answer("Запоминай последовательность.")
                    await asyncio.sleep(remaining)
                    await _reveal_memory(session, key=row.key, token=room["token"], message=message, sent=sent)
                else:
                    await _reveal_memory(session, key=row.key, token=room["token"], message=message)
                    await query.answer("Игра открыта.")
                return
            rendered = _format_prompt(room)
            if rendered is None:
                continue
            await message.answer(*rendered, parse_mode="HTML")
            await query.answer("Игра открыта.")
            return
        await query.answer("Открытой игры нет. Выбери новый формат.", show_alert=True)
        return
    if action[1] in {"solo", "team"}:
        kind = action[1]
        room = await _new_room(session, chat_id=message.chat.id, thread_id=message.message_thread_id,
                               user_id=query.from_user.id, kind=kind, questions_per_game=5)
        await session.commit()
        if room is None:
            await query.answer("Игра уже открыта. Присоединяйся к существующей комнате.", show_alert=True)
            return
        if room["status"] == "exhausted":
            await query.answer("Новые вопросы готовятся. Выбери игру позже.", show_alert=True)
            return
        if kind == "team":
            await message.answer(
                "🤝 <b>Командный квиз ЭРА</b>\nКомната открыта. Нажми «Присоединиться». "
                "Нужно минимум два игрока; готовность подтверждают все участники. Если группа не соберётся, игра просто закроется.",
                parse_mode="HTML", reply_markup=lobby_markup(room["id"] + "~" + room["token"]))
        else:
            question, options, _ = QUESTIONS[room["question"]]
            await message.answer(f"⚡ <b>Быстрый квиз</b>\n\n{question}",
                                 parse_mode="HTML", reply_markup=quiz_markup(room["id"] + "~" + room["token"], options))
        await query.answer()
        return
    if len(action) < 3:
        await query.answer()
        return
    operation, reference = action[1], action[2]
    room_id, separator, token = reference.partition("~")
    if not separator or not token:
        await query.answer("Эта кнопка устарела. Открой новую игру.")
        return
    key = _key(message.chat.id, message.message_thread_id, room_id)
    await _lock(session, key)
    row = await session.scalar(select(AppSetting).where(AppSetting.key == key).with_for_update())
    room = _data(row)
    if not room or room.get("token") != token or room.get("status") not in {"waiting", "ready_check", "playing"}:
        await query.answer("Раунд завершён.")
        return
    if datetime.fromisoformat(room["expires_at"]) <= datetime.now(timezone.utc):
        room["status"] = "expired"
        await _save(session, key, room)
        await session.commit()
        await query.answer("Время раунда истекло.")
        return
    uid = query.from_user.id
    if operation == "duel_join" and room.get("kind") == "duel" and room["status"] in {"waiting", "ready_check"}:
        if len(action) != 4 or action[3] not in {"A", "B"}:
            await query.answer("Выбери одну из двух команд.", show_alert=True)
            return
        team = action[3]
        teams = room.setdefault("teams", {})
        previous_team = teams.get(str(uid))
        if uid not in room["participants"] and len(room["participants"]) >= MAX_PLAYERS:
            await query.answer("В дуэли уже восемь игроков.", show_alert=True)
            return
        if sum(value == team for value in teams.values()) >= MAX_PLAYERS // 2 and previous_team != team:
            await query.answer("Эта команда уже заполнена.", show_alert=True)
            return
        if uid not in room["participants"]:
            room["participants"].append(uid)
        teams[str(uid)] = team
        room["ready"] = []
        teams_present = set(teams.values())
        if teams_present == {"A", "B"}:
            room["status"] = "ready_check"
            room["expires_at"] = min(
                datetime.now(timezone.utc) + timedelta(seconds=READY_SECONDS),
                datetime.fromisoformat(room["lobby_deadline"]),
            ).isoformat()
        else:
            room["status"] = "waiting"
            room["expires_at"] = room["lobby_deadline"]
        await _save(session, key, room)
        await session.commit()
        markup = duel_markup(room_id + "~" + room["token"], ready=room["status"] == "ready_check")
        await message.answer("Состав команд обновлён. Подтвердите готовность." if room["status"] == "ready_check" else "Игрок добавлен в команду.", reply_markup=markup)
        await query.answer("Ты в команде " + team + ".")
        return
    if operation == "join" and room["status"] in {"waiting", "ready_check"}:
        if uid in room["participants"]:
            await query.answer("Ты уже в команде.")
            return
        if uid not in room["participants"] and len(room["participants"]) >= MAX_PLAYERS:
            await query.answer("Команда уже заполнена.", show_alert=True)
            return
        if uid not in room["participants"]:
            room["participants"].append(uid)
        if len(room["participants"]) >= MIN_PLAYERS:
            if room["status"] != "ready_check":
                room["status"] = "ready_check"
                room["ready"] = []
                room["expires_at"] = min(
                    datetime.now(timezone.utc) + timedelta(seconds=READY_SECONDS),
                    datetime.fromisoformat(room["lobby_deadline"]),
                ).isoformat()
            await _save(session, key, room)
            await session.commit()
            await message.answer("✅ Подтвердите готовность. Стартуем, когда все участники подтвердят готовность.",
                                 reply_markup=ready_markup(room_id + "~" + room["token"]))
            await query.answer("Ты в команде. Подтверди готовность.")
            return
        await _save(session, key, room)
        await session.commit()
        await query.answer("Ты в команде. Ожидаем остальных.")
        return
    if operation == "ready" and room["status"] == "ready_check":
        if uid not in room["participants"]:
            await query.answer("Сначала присоединись к команде.")
            return
        ready = room.setdefault("ready", [])
        if uid in ready:
            await query.answer("Готовность уже подтверждена.")
            return
        ready.append(uid)
        enough_players = (
            len(ready) >= MIN_PLAYERS and len(ready) == len(room["participants"])
            if room.get("kind") != "duel"
            else len(ready) == len(room["participants"])
            and {room.get("teams", {}).get(str(player)) for player in ready} == {"A", "B"}
        )
        if enough_players:
            room["questions"] = await _reserve_questions(
                session,
                datetime.now(timezone.utc),
                room.get("question_count", 1),
                user_ids=room["participants"],
                mode="team_duel" if room.get("kind") == "duel" else "team_quiz",
            )
            if not room["questions"]:
                room["status"] = "exhausted"
                await _save(session, key, room)
                await session.commit()
                await query.answer("Новые вопросы готовятся. Выбери игру позже.", show_alert=True)
                return
            room["participants"] = list(ready)
            room["question"] = room["questions"][0]
            room["status"] = "playing"
            room["expires_at"] = (datetime.now(timezone.utc) + timedelta(seconds=120)).isoformat()
        await _save(session, key, room)
        await session.commit()
        await query.answer("Готовность принята.")
        if room["status"] == "playing":
            question, options, _ = QUESTIONS[room["question"]]
            title = "🏆 Дуэль началась" if room.get("kind") == "duel" else "🤝 Команда готова"
            await message.answer(f"{title}. Вопрос 1/{len(room['questions'])}\n\n{question}",
                                 reply_markup=quiz_markup(room_id + "~" + room["token"], options))
        return
    if operation == "leave" and room["status"] in {"waiting", "ready_check"}:
        if uid not in room["participants"]:
            await query.answer("Ты не участвуешь в этой комнате.")
            return
        room["participants"] = [p for p in room["participants"] if p != uid]
        room.get("teams", {}).pop(str(uid), None)
        # Reconfirm after the roster changes; otherwise remaining ready players
        # could be stuck with no callback able to start the room.
        room["ready"] = []
        if not room["participants"]:
            room["status"] = "cancelled"
        elif room.get("kind") == "duel" and set(room.get("teams", {}).values()) != {"A", "B"}:
            room["status"] = "waiting"
            room["expires_at"] = room["lobby_deadline"]
        elif len(room["participants"]) < MIN_PLAYERS:
            room["status"] = "waiting"
            room["expires_at"] = room["lobby_deadline"]
        await _save(session, key, room)
        await session.commit()
        await query.answer("Ты вышел из комнаты.")
        if room["status"] == "ready_check":
            await message.answer("Состав изменился. Подтвердите готовность ещё раз.",
                                 reply_markup=ready_markup(room_id + "~" + room["token"]))
        return
    if operation == "answer" and room["status"] == "playing" and len(action) == 4:
        if uid not in room["participants"]:
            await query.answer("Сначала присоединись к игре.")
            return
        if str(uid) in room["answers"]:
            await query.answer("Ответ уже принят.")
            return
        try:
            choice = int(action[3])
        except ValueError:
            await query.answer()
            return
        if choice not in range(len(QUESTIONS[room["question"]][1])):
            await query.answer()
            return
        room["answers"][str(uid)] = choice
        scores = room.setdefault("scores", {})
        if choice == QUESTIONS[room["question"]][2]:
            scores[str(uid)] = scores.get(str(uid), 0) + 1
            if room.get("kind") == "duel":
                team = room.get("teams", {}).get(str(uid))
                if team in {"A", "B"}:
                    room.setdefault("team_scores", {"A": 0, "B": 0})[team] += 1
        complete = len(room["answers"]) >= len(room["participants"])
        questions = room.get("questions", [room["question"]])
        finished = complete and room.get("position", 0) + 1 >= len(questions)
        if finished:
            room["status"] = "finished"
            if settings.games_rewards_enabled:
                # Sort locks by user ID to avoid cross-room reward deadlocks.
                best = max(scores.values(), default=0)
                winners = [player for player in room["participants"] if scores.get(str(player), 0) == best]
                duel_team_winner = None
                if room.get("kind") == "duel":
                    team_scores = room.get("team_scores", {"A": 0, "B": 0})
                    if team_scores.get("A", 0) != team_scores.get("B", 0):
                        duel_team_winner = "A" if team_scores["A"] > team_scores["B"] else "B"
                for player in sorted(room["participants"]):
                    score = scores.get(str(player), 0)
                    if score * 5 < len(questions) * 3:
                        continue
                    if room.get("kind") == "duel" and room.get("teams", {}).get(str(player)) != duel_team_winner:
                        continue
                    bonus = 2 if room.get("kind") != "duel" and len(room["participants"]) >= 2 and winners == [player] else 0
                    await award_game_points(session, telegram_id=player,
                                            round_id=room.get("session_token", room["token"]), amount=3 + bonus)
        elif complete:
            room["position"] = room.get("position", 0) + 1
            room["question"] = questions[room["position"]]
            room["answers"] = {}
            room["token"] = secrets.token_hex(6)
            room["expires_at"] = (datetime.now(timezone.utc) + timedelta(seconds=120)).isoformat()
        await _save(session, key, room)
        await session.commit()
        await query.answer("Ответ принят!")
        if finished:
            if len(room["participants"]) == 1:
                summary = f"Твой результат: {scores.get(str(uid), 0)} из {len(questions)}."
            elif room.get("kind") == "duel":
                team_scores = room.get("team_scores", {"A": 0, "B": 0})
                winner = "Ничья" if team_scores["A"] == team_scores["B"] else (
                    "Команда А" if team_scores["A"] > team_scores["B"] else "Команда Б"
                )
                summary = f"Команда А: {team_scores['A']} · Команда Б: {team_scores['B']}. Победитель: {winner}."
            else:
                summary = f"Вопросов: {len(questions)}. Верных ответов команды: {sum(scores.values())}."
            await message.answer("🏁 Квиз завершён. " + summary)
        elif complete:
            question, options, _ = QUESTIONS[room["question"]]
            await message.answer(f"🎯 Вопрос {room['position'] + 1}/{len(questions)}\n\n{question}",
                                 reply_markup=quiz_markup(room_id + "~" + room["token"], options))
        return
    await query.answer("Сейчас это действие недоступно.")
