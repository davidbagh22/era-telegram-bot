"""Telegram-only game-room pilot: no public empty-room counters or fake players.

All gameplay is restricted to the configured general-chat forum topic.
Feature is OFF by default until end-to-end validation and content expansion.
"""
from __future__ import annotations

import hashlib
import json
import logging
import secrets
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select, text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import AppSetting
from app.services.general_topics_service import ensure_topic
from app.services.game_rewards_service import award_game_points

logger = logging.getLogger(__name__)
router = Router(name="era_game_room")
MIN_PLAYERS = 2
MAX_PLAYERS = 8
WAIT_SECONDS = 180
READY_SECONDS = 20

# Curated general-knowledge examples, supplemented by generated arithmetic.
QUESTIONS = (
    ("Какой город является столицей Армении?", ("Ереван", "Гюмри", "Ванадзор"), 0),
    ("Сколько минут в одном часе?", ("50", "60", "100"), 1),
    ("Как называется самый большой океан Земли?", ("Атлантический", "Индийский", "Тихий"), 2),
    ("Какая планета ближе всего к Солнцу?", ("Венера", "Меркурий", "Марс"), 1),
    ("Какой язык используется в официальных документах Республики Армения?", ("Армянский", "Латинский", "Немецкий"), 0),
    ("Сколько континентов обычно выделяют в семиконтинентной модели?", ("5", "6", "7"), 2),
    ("Что измеряют термометром?", ("Давление", "Температуру", "Скорость"), 1),
    ("Что означает QR в QR-коде?", ("Quick Response", "Quality Read", "Query Route"), 0),
)


def _arithmetic_questions() -> tuple[tuple[str, tuple[str, ...], int], ...]:
    """180 distinct, deterministic arithmetic questions with validated distractors.

    This is supplementary content, not a substitute for 11 distinct game formats.
    """
    questions = []
    for index in range(180):
        a = 12 + index
        b = 3 + index % 17
        if index % 3 == 0:
            prompt, answer = f"Сколько будет {a} + {b}?", a + b
        elif index % 3 == 1:
            prompt, answer = f"Сколько будет {a + b} − {b}?", a
        else:
            prompt, answer = f"Сколько будет {a} × {b}?", a * b
        correct = index % 3
        options = [str(answer + 1), str(answer + 2), str(answer + 3)]
        options[correct] = str(answer)
        questions.append((prompt, tuple(options), correct))
    return tuple(questions)


QUESTIONS += _arithmetic_questions()


def menu_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡ Быстрый квиз", callback_data="era_game:solo")],
        [InlineKeyboardButton(text="🤝 Собрать команду", callback_data="era_game:team")],
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


def quiz_markup(room_id: str, options: tuple[str, ...]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=option, callback_data=f"era_game:answer:{room_id}:{index}")]
        for index, option in enumerate(options)
    ])


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


async def _reserve_questions(session: AsyncSession, now: datetime, count: int) -> list[int]:
    # Global question reservation prevents repeat questions, even across users.
    used_key = "era_game:question_usage"
    await _lock(session, used_key)
    usage_row = await session.scalar(select(AppSetting).where(AppSetting.key == used_key).with_for_update())
    used = _data(usage_row)
    cutoff = now - timedelta(days=180)
    active = {}
    for key, timestamp in used.items():
        try:
            when = datetime.fromisoformat(timestamp)
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            if when > cutoff:
                active[str(int(key))] = when.isoformat()
        except (TypeError, ValueError):
            logger.warning('Invalid game reservation entry %s', key)
    used = active
    unavailable = {int(key) for key in used}
    available = [i for i in range(len(QUESTIONS)) if i not in unavailable]
    if len(available) < count:
        return []
    chosen = available[:count]
    for index in chosen:
        used[str(index)] = now.isoformat()
    await _save(session, used_key, used)
    return chosen


async def _reserve_question(session: AsyncSession, now: datetime) -> int | None:
    questions = await _reserve_questions(session, now, 1)
    return questions[0] if questions else None


async def _new_room(session: AsyncSession, *, chat_id: int, thread_id: int,
                    user_id: int, kind: str, questions_per_game: int = 1) -> dict | None:
    if not 1 <= questions_per_game <= 10:
        raise ValueError("questions_per_game must be between 1 and 10")
    # One public lobby per topic; solo rounds have a per-user key.
    room_id = "team" if kind == "team" else f"solo-{user_id}"
    key = _key(chat_id, thread_id, room_id)
    await _lock(session, key)
    row = await session.scalar(select(AppSetting).where(AppSetting.key == key).with_for_update())
    current = _data(row)
    now = datetime.now(timezone.utc)
    if current.get("status") in {"waiting", "ready_check", "playing"}:
        if current.get("expires_at") and datetime.fromisoformat(current["expires_at"]) > now:
            return None
    questions = await _reserve_questions(session, now, questions_per_game) if kind == "solo" else []
    if kind == "solo" and not questions:
        return {"status": "exhausted"}
    token = secrets.token_hex(6)
    data = {
        "token": token, "session_token": token,
        "questions": questions, "question_count": questions_per_game,
        "position": 0, "scores": {}, "ready": [],
        "lobby_deadline": (now + timedelta(seconds=WAIT_SECONDS)).isoformat(),
        "id": room_id, "kind": kind, "status": "waiting" if kind == "team" else "playing",
        "participants": [user_id], "answers": {}, "question": questions[0] if questions else None,
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
    if action[1] == "rules":
        rewards = "3 балла за 60% верных ответов; +2 единственному победителю команды. Лимиты: 20/день, 100/неделю, 300/месяц." if settings.games_rewards_enabled else "В тестовом режиме начисление баллов выключено."
        await query.answer("Квиз: 5 вопросов. За ожидание и незавершённую игру баллы не начисляются. " + rewards, show_alert=True)
        return
    if action[1] == "resume":
        for room_id in (f"solo-{query.from_user.id}", "team"):
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
            else:
                markup = ready_markup(reference) if room["status"] == "ready_check" else lobby_markup(reference)
                await message.answer("🤝 Твоя командная игра", reply_markup=markup)
            await query.answer("Игра открыта.")
            return
        await query.answer("Открытой игры нет. Выбери новый квиз.", show_alert=True)
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
        if len(ready) >= MIN_PLAYERS and len(ready) == len(room["participants"]):
            room["questions"] = await _reserve_questions(session, datetime.now(timezone.utc), room.get("question_count", 1))
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
            await message.answer(f"🎯 Команда готова. Вопрос 1/{len(room['questions'])}\n\n{question}",
                                 reply_markup=quiz_markup(room_id + "~" + room["token"], options))
        return
    if operation == "leave" and room["status"] in {"waiting", "ready_check"}:
        if uid not in room["participants"]:
            await query.answer("Ты не участвуешь в этой комнате.")
            return
        room["participants"] = [p for p in room["participants"] if p != uid]
        # Reconfirm after the roster changes; otherwise remaining ready players
        # could be stuck with no callback able to start the room.
        room["ready"] = []
        if not room["participants"]:
            room["status"] = "cancelled"
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
        complete = len(room["answers"]) >= len(room["participants"])
        questions = room.get("questions", [room["question"]])
        finished = complete and room.get("position", 0) + 1 >= len(questions)
        if finished:
            room["status"] = "finished"
            if settings.games_rewards_enabled:
                # Sort locks by user ID to avoid cross-room reward deadlocks.
                best = max(scores.values(), default=0)
                winners = [player for player in room["participants"] if scores.get(str(player), 0) == best]
                for player in sorted(room["participants"]):
                    score = scores.get(str(player), 0)
                    if score * 5 < len(questions) * 3:
                        continue
                    bonus = 2 if len(room["participants"]) >= 2 and winners == [player] else 0
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
            else:
                summary = f"Вопросов: {len(questions)}. Верных ответов команды: {sum(scores.values())}."
            await message.answer("🏁 Квиз завершён. " + summary)
        elif complete:
            question, options, _ = QUESTIONS[room["question"]]
            await message.answer(f"🎯 Вопрос {room['position'] + 1}/{len(questions)}\n\n{question}",
                                 reply_markup=quiz_markup(room_id + "~" + room["token"], options))
        return
    await query.answer("Сейчас это действие недоступно.")
