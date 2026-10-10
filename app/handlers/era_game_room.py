"""Telegram-only game-room pilot: no public empty-room counters or fake players.

All gameplay is restricted to the configured general-chat forum topic.
Feature is OFF by default until end-to-end validation and content expansion.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select, text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import AppSetting
from app.services.general_topics_service import ensure_topic

logger = logging.getLogger(__name__)
router = Router(name="era_game_room")
MIN_PLAYERS = 2
MAX_PLAYERS = 8
WAIT_SECONDS = 180

# Curated examples only. Not a six-month content bank.
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


def menu_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡ Быстрый квиз", callback_data="era_game:solo")],
        [InlineKeyboardButton(text="🤝 Собрать команду", callback_data="era_game:team")],
        [InlineKeyboardButton(text="📚 Правила", callback_data="era_game:rules")],
    ])


def lobby_markup(room_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🙋 Присоединиться", callback_data=f"era_game:join:{room_id}")],
        [InlineKeyboardButton(text="🚪 Выйти", callback_data=f"era_game:leave:{room_id}")],
    ])


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


async def _new_room(session: AsyncSession, *, chat_id: int, thread_id: int,
                    user_id: int, kind: str) -> dict | None:
    # One public lobby per topic; solo rounds have a per-user key.
    room_id = "team" if kind == "team" else f"solo-{user_id}"
    key = _key(chat_id, thread_id, room_id)
    await _lock(session, key)
    row = await session.scalar(select(AppSetting).where(AppSetting.key == key).with_for_update())
    current = _data(row)
    now = datetime.now(timezone.utc)
    if current.get("status") in {"waiting", "playing"}:
        if current.get("expires_at") and datetime.fromisoformat(current["expires_at"]) > now:
            return None
    # Global question reservation prevents repeat questions, even across users.
    used_key = "era_game:question_usage"
    await _lock(session, used_key)
    usage_row = await session.scalar(select(AppSetting).where(AppSetting.key == used_key).with_for_update())
    used = _data(usage_row)
    available = [i for i in range(len(QUESTIONS))
                 if i not in {int(k) for k, v in used.items()
                              if datetime.fromisoformat(v) > now - timedelta(days=180)}]
    if not available:
        return {"status": "exhausted"}
    index = available[0]
    used[str(index)] = now.isoformat()
    await _save(session, used_key, used)
    data = {
        "id": room_id, "kind": kind, "status": "waiting" if kind == "team" else "playing",
        "participants": [user_id], "answers": {}, "question": index,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=WAIT_SECONDS if kind == "team" else 120)).isoformat(),
    }
    await _save(session, key, data)
    return data


@router.message(F.text.in_({"/games", "/game"}))
async def game_menu(message: Message, settings: Settings):
    if not message.from_user or not await _allowed(settings, message, message.from_user.id):
        return
    await message.answer("🎮 <b>ЭРА | Интерактив</b>\n\nВыбирай игру. Можно начать одному или собрать небольшую команду.", reply_markup=menu_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("era_game:"))
async def game_callback(query: CallbackQuery, settings: Settings, session: AsyncSession):
    if not isinstance(query.message, Message) or not query.from_user:
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
        await query.answer("Играй честно. За ожидание баллы не начисляются. В пилоте — короткие квизы.", show_alert=True)
        return
    if action[1] in {"solo", "team"}:
        kind = action[1]
        room = await _new_room(session, chat_id=message.chat.id, thread_id=message.message_thread_id,
                               user_id=query.from_user.id, kind=kind)
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
                "Старт после набора минимум двух игроков. Если группа не соберётся, игра просто закроется.",
                parse_mode="HTML", reply_markup=lobby_markup(room["id"]))
        else:
            question, options, _ = QUESTIONS[room["question"]]
            await message.answer(f"⚡ <b>Быстрый квиз</b>\n\n{question}",
                                 parse_mode="HTML", reply_markup=quiz_markup(room["id"], options))
        await query.answer()
        return
    if len(action) < 3:
        await query.answer()
        return
    operation, room_id = action[1], action[2]
    key = _key(message.chat.id, message.message_thread_id, room_id)
    await _lock(session, key)
    row = await session.scalar(select(AppSetting).where(AppSetting.key == key).with_for_update())
    room = _data(row)
    if not room or room.get("status") not in {"waiting", "playing"}:
        await query.answer("Раунд завершён.")
        return
    if datetime.fromisoformat(room["expires_at"]) <= datetime.now(timezone.utc):
        room["status"] = "expired"
        await _save(session, key, room)
        await session.commit()
        await query.answer("Время раунда истекло.")
        return
    uid = query.from_user.id
    if operation == "join" and room["status"] == "waiting":
        if uid not in room["participants"] and len(room["participants"]) < MAX_PLAYERS:
            room["participants"].append(uid)
        if len(room["participants"]) >= MIN_PLAYERS:
            room["status"] = "playing"
            room["expires_at"] = (datetime.now(timezone.utc) + timedelta(seconds=120)).isoformat()
            await _save(session, key, room)
            await session.commit()
            question, options, _ = QUESTIONS[room["question"]]
            await message.answer(f"🎯 <b>Команда собралась! Вопрос:</b>\n\n{question}",
                                 parse_mode="HTML", reply_markup=quiz_markup(room_id, options))
            await query.answer("Игра началась!")
            return
        await _save(session, key, room)
        await session.commit()
        await query.answer("Ты в команде. Ожидаем остальных.")
        return
    if operation == "leave" and room["status"] == "waiting":
        room["participants"] = [p for p in room["participants"] if p != uid]
        if not room["participants"]:
            room["status"] = "cancelled"
        await _save(session, key, room)
        await session.commit()
        await query.answer("Ты вышел из комнаты.")
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
        complete = len(room["answers"]) >= len(room["participants"])
        if complete:
            room["status"] = "finished"
        await _save(session, key, room)
        await session.commit()
        await query.answer("Ответ принят!")
        if complete:
            correct = QUESTIONS[room["question"]][2]
            count = sum(value == correct for value in room["answers"].values())
            await message.answer(f"🏁 Раунд завершён. Правильных ответов: {count} из {len(room['participants'])}.")
        return
    await query.answer("Сейчас это действие недоступно.")
