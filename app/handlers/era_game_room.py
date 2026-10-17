"""Telegram-only game-room pilot: no public empty-room counters or fake players.

Solo games run privately; shared games use the configured forum topic.
Feature is OFF by default until end-to-end validation and content expansion.
"""
from __future__ import annotations

import hashlib
import json
import logging
import secrets
import asyncio
from html import escape
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramNetworkError, TelegramServerError
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select, text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import AppSetting, User
from app.services.game_content import GameItem, QUIZ_QUESTIONS, choose_quiz_pack, items_for_mode
from app.services.game_formats import GameMode, check_answer, score_answer
from app.services.general_topics_service import ensure_topic
from app.services.game_rewards_service import award_game_points
from app.services.game_room_presenter import deadline, player_label, remember_player, result_summary, room_heading, roster
from app.keyboards.common import registration_keyboard
from app.utils.constants import ApplicationStatus

logger = logging.getLogger(__name__)
router = Router(name="era_game_room")
MIN_PLAYERS = 2
MAX_PLAYERS = 8
WAIT_SECONDS = 180
READY_SECONDS = 90

QUESTIONS = QUIZ_QUESTIONS
PUBLIC_MENU_TEXT = (
        "🎮 <b>ЭРА | Интерактив</b>\n\n"
        "👥 Командные игры — здесь. Бот распределит игроков по командам, покажет имена и результаты.\n"
        "👤 Одиночные игры — в личном боте.\n\n"
        "Для участия нужна одобренная регистрация в ЭРА. "
        "При вступлении в команду имя из Telegram и Telegram ID видны участникам."
)



def menu_markup(*, public: bool = False, bot_username: str = "ERA_1bot") -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
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
    if public:
        for row in keyboard.inline_keyboard:
            button = row[0]
            data = button.callback_data
            if data == "era_game:solo" or data.startswith("era_game:play:"):
                mode = "solo" if data == "era_game:solo" else data.split(":")[-1]
                button.callback_data = None
                button.url = f"https://t.me/{bot_username}?start=game_{mode}"
        keyboard.inline_keyboard.insert(0, [InlineKeyboardButton(
            text="👤 Мои игры · регистрация", url=f"https://t.me/{bot_username}?start=games"
        )])
    # Keep the existing eleven agreed formats, with compact pairs of solo buttons.
    rows = keyboard.inline_keyboard
    compact = []
    for row in rows:
        if compact and len(compact[-1]) == 1 and row[0].url and compact[-1][0].url and "game_" in row[0].url and "game_" in compact[-1][0].url:
            compact[-1].extend(row)
        else:
            compact.append(row)
    keyboard.inline_keyboard = compact
    return keyboard


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
    # The server chooses the smaller team; old side-selection callbacks remain supported.
    return ready_markup(reference) if ready else lobby_markup(reference)


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
    available = [candidate for candidate in items if candidate.id not in active]
    item = secrets.choice(available) if available else None
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
    heading = room_heading(room) + "\n" + roster(room) + "\n\n"
    text = f"<b>{escape(challenge.prompt)}</b>\n\n<i>Тема: {escape(item.category)}</i>"
    if challenge.hints:
        shown = challenge.hints[:room.get('hints_used', 0)]
        text += '\n\n' + '\n'.join(f'💡 {escape(hint)}' for hint in shown)
        text += '\n\nПервая подсказка бесплатная; дополнительные уменьшают очки.'
    if challenge.mode == GameMode.MEMORY:
        if not room.get("memory_revealed"):
            return (
                heading + f"{escape(challenge.prompt)}\n\n<i>Запомни последовательность: она будет показана 5 секунд.</i>",
                None,
            )
        instruction = challenge.prompt.split(":", 1)[0].rstrip()
        text = f"🧩 <b>Память</b>\n{escape(instruction)}\n\nПоследовательность скрыта. Какой она была?"
    reference = f"{room['id']}~{room['token']}"
    return heading + text + "\n\n" + deadline(room), format_markup(reference, item, hints_used=room.get("hints_used", 0))


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
    await _publish_room(session, key, message)
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
        "participants": [uid], "answers": {}, "scores": {},
        "hints_used": 1 if item.challenge.hints else 0, "first_hint_free": True,
        "created_at": now.isoformat(), "expires_at": (now + timedelta(minutes=5)).isoformat(),
    }
    remember_player(room, query.from_user)
    if mode == GameMode.MEMORY:
        room["memory_revealed"] = False
        room["memory_ready_at"] = (now + timedelta(seconds=5)).isoformat()
    await _save(session, key, room)
    await session.commit()
    rendered = _format_prompt(room)
    if rendered is None:
        await query.answer("Материал игры недоступен.", show_alert=True)
        return
    await query.answer("Запоминай последовательность." if mode == GameMode.MEMORY else None)
    if not await _publish_room(session, key, message):
        return
    if mode == GameMode.MEMORY:
        await asyncio.sleep(5)
        await _reveal_memory(session, key=key, token=token, message=message)



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
        await _publish_room(session, key, message)
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
        await _publish_room(session, key, message)
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
    hints_used = max(0, room.get("hints_used", 0) - int(room.get('first_hint_free', False)))
    score = score_answer(item.challenge, selected, hints_used=hints_used,
                         previous_word=item.previous_word)
    room.setdefault("answers", {})[str(uid)] = choice
    room.setdefault("scores", {})[str(uid)] = score
    room["status"] = "finished"
    room["finished_at"] = now.isoformat()
    awarded = 0
    if correct and settings.games_rewards_enabled:
        awarded = await award_game_points(session, telegram_id=uid, round_id=room["session_token"], amount=score)
    room["rewards"] = {str(uid): awarded}
    result = "✅ Верно!" if correct else f"❌ Пока неверно. Ответ: <b>{escape(item.challenge.answer)}</b>."
    if item.challenge.explanation:
        result += f"\n\nℹ️ {escape(item.challenge.explanation)}"
    result += f"\n\nОчки за раунд: {score}. Баллы ЭРА: +{awarded}."
    room["result_text"] = result
    await _store_game_result(session, room)
    await _save(session, key, room)
    await session.commit()
    await query.answer("Ответ принят.")
    await _publish_room(session, key, message)
    return True


def _enabled(settings: Settings, telegram_id: int) -> bool:
    mode = settings.feature_games
    return mode == "ALL" or (mode == "TESTERS" and telegram_id in settings.feature_tester_ids)


async def _allowed(settings: Settings, message: Message, telegram_id: int) -> bool:
    if not _enabled(settings, telegram_id) or not settings.general_chat_id:
        return False
    if message.chat.type == "private":
        return True
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
    """Shared quiz history prevents solo/team/duel repeats for every player.

    Prefer unseen questions for 180 days. Only after bank exhaustion recycle
    the oldest questions with a strict 30-day floor, so daily five-question
    games remain playable through 180 days. Legacy per-mode history is read.
    """
    quiz_modes = ('solo_quiz', 'team_quiz', 'team_duel')
    shared = bool(user_ids and mode in quiz_modes)
    usage_keys = (
        [f"era_game:question_usage:{mode}:{user_id}" for user_id in sorted(set(user_ids))]
        if user_ids
        else ["era_game:question_usage"]
    )
    write_keys = set(usage_keys)
    if shared:
        usage_keys = sorted({f'era_game:question_usage:{kind}:{uid}'
                             for uid in set(user_ids) for kind in (*quiz_modes, 'quiz')})
        write_keys.update(f'era_game:question_usage:quiz:{uid}' for uid in set(user_ids))
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
    chosen = (choose_quiz_pack(available, min(count, len(available))) if user_ids else available[:count])
    if len(available) < count:
        if not shared:
            return []
        last_seen: dict[int, datetime] = {}
        for used in active_by_key.values():
            for index, when in used.items():
                index, when = int(index), datetime.fromisoformat(when)
                last_seen[index] = max(last_seen.get(index, when), when)
        recycled = sorted((i for i, when in last_seen.items()
                           if 0 <= i < len(QUESTIONS) and when <= now-timedelta(days=30)),
                          key=lambda i: (last_seen[i], i))
        chosen.extend(recycled[:count-len(chosen)])
        if len(chosen) < count:
            return []
    for used_key, used in active_by_key.items():
        if used_key not in write_keys:
            continue
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
        "expires_at": (now + timedelta(seconds=WAIT_SECONDS if kind in {"team", "duel"} else 120)).isoformat(),
    }
    await _save(session, key, data)
    return data


def _registered(user: User | None, telegram_id: int) -> bool:
    return bool(user and user.telegram_id == telegram_id
                and user.application_status == ApplicationStatus.APPROVED
                and not user.is_blocked and not user.is_archived)


def _bot_link(settings: Settings, payload: str = "games") -> str:
    return f"https://t.me/{settings.bot_username or 'ERA_1bot'}?start={payload}"


def _room_view(room: dict) -> tuple[str, InlineKeyboardMarkup | None]:
    header = room_heading(room) + "\n\n"
    status = room.get("status")
    if status in {"expired", "cancelled", "exhausted"}:
        title = {"expired": "⏱ Время игры истекло. Баллы не начислены.",
                 "cancelled": "Комната закрыта: все игроки вышли.",
                 "exhausted": "Новые задания готовятся. Комната закрыта."}[status]
        return header + title + "\n\n" + roster(room, result=True), None
    if status == "finished":
        summary = room.get("result_text") or result_summary(room)
        rewards = room.get("rewards", {})
        reward_line = ""
        if not room.get("mode"):
            reward_line = "\n\n<b>Баллы ЭРА</b>\n" + "\n".join(
                f"{player_label(room, uid)}: +{rewards.get(str(uid), 0)}"
                for uid in room.get("participants", [])
            )
        markup = None
        if room.get('mode') or room.get('kind') == 'solo':
            callback = f"era_game:play:{room['mode']}" if room.get('mode') else 'era_game:solo'
            markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text='🎯 Ещё раунд', callback_data=callback),
                 InlineKeyboardButton(text='🎮 Мои игры', callback_data='era_game:cabinet')],
            ])
        return header + "🏁 Игра завершена\n\n" + summary + "\n\n" + roster(room, result=True) + reward_line, markup
    if room.get("mode"):
        return _format_prompt(room) or (header + "Материал недоступен.", None)
    reference = room["id"] + "~" + room["token"]
    if status in {"waiting", "ready_check"}:
        info = ("Набор игроков · до 8 участников. Минимум двое.\n"
                "Нажмите «Присоединиться», затем подтвердите готовность.\n"
                "Имена и Telegram ID участников будут видны в этой карточке.")
        if room.get("kind") == "duel":
            info += "\nБот автоматически распределяет игроков поровну в команды А и Б."
        if status == "ready_check":
            info += "\n\n✅ Все присоединившиеся должны нажать «Готов играть»."
        return (header + info + "\n\n" + roster(room) + "\n\n" + deadline(room),
                ready_markup(reference) if status == "ready_check" else lobby_markup(reference))
    question, options, _ = QUESTIONS[room["question"]]
    position = room.get("position", 0) + 1
    count = len(room.get("questions", [room["question"]]))
    topic = items_for_mode(GameMode.SOLO_QUIZ)[room['question']].category
    progress = '●' * position + '○' * (count-position)
    return (header + f"<b>Вопрос {position}/{count}</b> · {progress}\n<i>{escape(topic)}</i>\n\n<b>{escape(question)}</b>\n\n"
            + roster(room) + "\n\nВсе отвечают одновременно. Следующий вопрос — после ответов всех игроков.\n"
            + deadline(room), quiz_markup(reference, options))


async def _publish_room(session: AsyncSession, key: str, message: Message) -> bool:
    """Refresh one canonical card from the latest locked state, including after a restart.

    A send with an unknown outcome is never automatically replayed. Existing
    cards can always be edited again. The row lock serializes concurrent edits.
    """
    await _lock(session, key)
    row = await session.scalar(select(AppSetting).where(AppSetting.key == key)
                               .with_for_update().execution_options(populate_existing=True))
    room = _data(row)
    if not room:
        return False
    text, markup = _room_view(room)
    message_id = room.get("message_id")
    if message_id:
        try:
            await message.bot.edit_message_text(text=text, chat_id=message.chat.id,
                                               message_id=message_id, reply_markup=markup,
                                               parse_mode="HTML")
        except TelegramBadRequest as exc:
            if "not modified" not in str(exc).lower():
                if "message to edit not found" in str(exc).lower():
                    room.pop("message_id", None)
                    room["card_delivery"] = "missing"
                    await _save(session, key, room)
                    await session.commit()
                    return await _publish_room(session, key, message)
                logger.warning("Game card edit rejected type=%s", type(exc).__name__)
                await session.commit()
                return False
        except TelegramAPIError as exc:
            logger.warning("Game card edit postponed type=%s", type(exc).__name__)
            await session.commit()
            return False
        room["card_delivery"] = "sent"
        room["card_status"] = room.get("status")
        await _save(session, key, room)
        await session.commit()
        return True
    if room.get("card_delivery") in {"pending", "uncertain"}:
        await session.commit()
        return False
    room["card_delivery"] = "pending"
    incarnation = room["session_token"]
    await _save(session, key, room)
    await session.commit()
    try:
        sent = await message.answer(text, reply_markup=markup, parse_mode="HTML")
    except TelegramAPIError as exc:
        await _lock(session, key)
        row = await session.scalar(select(AppSetting).where(AppSetting.key == key).with_for_update()
                                   .execution_options(populate_existing=True))
        current = _data(row)
        if current.get("session_token") == incarnation:
            current["card_delivery"] = ("uncertain" if isinstance(exc, (TelegramNetworkError, TelegramServerError)) else "failed")
            await _save(session, key, current)
        await session.commit()
        logger.warning("Game card publication postponed type=%s", type(exc).__name__)
        return False
    await _lock(session, key)
    row = await session.scalar(select(AppSetting).where(AppSetting.key == key).with_for_update()
                               .execution_options(populate_existing=True))
    current = _data(row)
    if current.get("session_token") != incarnation:
        await session.commit()
        return False
    current["message_id"] = sent.message_id
    current["card_delivery"] = "sent"
    current["card_status"] = room.get("status")
    await _save(session, key, current)
    await session.commit()
    if _room_view(current) != (text, markup):
        return await _publish_room(session, key, message)
    return True


async def _store_game_result(session: AsyncSession, room: dict) -> None:
    token = room.get('session_token')
    if room.get('status') != 'finished' or not token:
        return
    key = f'game-result:{token}'
    if await session.scalar(select(AppSetting.key).where(AppSetting.key == key)) is not None:
        return
    await _save(session, key, {'finished_at': room['finished_at'], 'participants': room['participants'],
                              'mode': room.get('mode', room.get('kind')), 'scores': room.get('scores', {}),
                              'rewards': room.get('rewards', {})})


async def _join_lobby(session: AsyncSession, key: str, room: dict, telegram_user) -> bool:
    uid = telegram_user.id
    if uid in room["participants"] or len(room["participants"]) >= MAX_PLAYERS:
        return False
    room["participants"].append(uid)
    remember_player(room, telegram_user)
    if room.get("kind") == "duel":
        teams = room.setdefault("teams", {})
        team = min(("A", "B"), key=lambda side: sum(value == side for value in teams.values()))
        teams[str(uid)] = team
    room["ready"] = []
    room["status"] = "ready_check" if len(room["participants"]) >= MIN_PLAYERS else "waiting"
    room["expires_at"] = min(
        datetime.now(timezone.utc) + timedelta(seconds=READY_SECONDS if room["status"] == "ready_check" else WAIT_SECONDS),
        datetime.fromisoformat(room["lobby_deadline"]),
    ).isoformat()
    await _save(session, key, room)
    return True


async def show_game_cabinet(message: Message, settings: Settings, session: AsyncSession,
                            user: User | None, *, mode: str | None = None) -> None:
    uid = message.chat.id
    if not _enabled(settings, uid):
        await message.answer("Игры пока недоступны для этого профиля.")
        return
    if not _registered(user, uid):
        await message.answer("Для игры зарегистрируйтесь в ЭРА и дождитесь одобрения заявки.",
                             reply_markup=registration_keyboard() if user is None else None)
        return
    if mode:
        # Deep links use the same server-side callback logic, permissions and ledger.
        from types import SimpleNamespace
        async def answer_private(text=None, show_alert=False, **kwargs):
            if text and show_alert:
                await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="↩️ Продолжить игру", callback_data="era_game:resume"),
                    InlineKeyboardButton(text="👤 Мои игры", callback_data="era_game:cabinet"),
                ]]))
        query = SimpleNamespace(message=message, from_user=message.from_user,
                                data="era_game:solo" if mode == "solo" else f"era_game:play:{mode}",
                                answer=answer_private)
        await game_callback(query, settings, session, user=user)
        return
    thread_id = await ensure_topic(message.bot, settings, "games") if settings.general_chat_id else None
    text = "🎮 <b>Мои игры · ЭРА</b>\n\nОдиночные игры проходят здесь, командные — в теме «Интерактив».\n"
    personal_rooms = (await session.scalars(select(AppSetting).where(
        AppSetting.key.like(f"era_game:{uid}:None:%")))).all()
    recent = sorted((_data(row) for row in personal_rooms), key=lambda room: room.get("created_at", ""), reverse=True)[:3]
    if recent:
        text += "\n<b>Последние игры</b>\n"
        for room in recent:
            status = {"playing": "в процессе", "finished": "завершена", "expired": "время истекло"}.get(room.get("status"), "закрыта")
            score = room.get("scores", {}).get(str(uid), 0)
            text += f"{room_heading(room)} · {status} · {score} очк.\n"
    links = []
    if thread_id:
        for kind in ("team", "duel"):
            room = _data(await session.scalar(select(AppSetting).where(
                AppSetting.key == _key(settings.general_chat_id, thread_id, kind))))
            if uid in room.get("participants", []):
                text += "\n" + room_heading(room) + "\n" + roster(room, result=room.get("status") == "finished") + "\n"
                if room.get("message_id"):
                    links.append([InlineKeyboardButton(text="👥 Открыть мою команду", url=_topic_link(settings, thread_id, room["message_id"]))])
        links.append([InlineKeyboardButton(text="👥 Командные игры в чате", url=_topic_link(settings, thread_id))])
    keyboard = menu_markup()
    # A private menu never creates a separate team lobby.
    keyboard.inline_keyboard = [row for row in keyboard.inline_keyboard if all(
        b.callback_data not in {"era_game:team", "era_game:duel"} for b in row)]
    keyboard.inline_keyboard.extend(links)
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="🔄 Обновить мои игры", callback_data="era_game:cabinet")])
    await message.answer(text + "\nВыберите игру ниже. /games возвращает в этот раздел.",
                         reply_markup=keyboard, parse_mode="HTML")


def _topic_link(settings: Settings, thread_id: int, message_id: int | None = None) -> str:
    return f"https://t.me/c/{str(settings.general_chat_id)[4:]}/{thread_id}" + (f"/{message_id}" if message_id else "")


@router.message(Command("games", "game"))
async def game_menu(message: Message, settings: Settings, session: AsyncSession, user: User | None = None):
    if not message.from_user:
        return
    if message.chat.type == "private":
        await show_game_cabinet(message, settings, session, user)
        return
    if user and (user.is_blocked or user.is_archived):
        return
    if not await _allowed(settings, message, message.from_user.id):
        return
    await message.answer(
        PUBLIC_MENU_TEXT,
        reply_markup=menu_markup(public=True, bot_username=settings.bot_username or "ERA_1bot"), parse_mode="HTML")


@router.callback_query(F.data.startswith("era_game:"))
async def game_callback(query: CallbackQuery, settings: Settings, session: AsyncSession, user: User | None = None):
    if user and (user.is_blocked or user.is_archived):
        await query.answer("Доступ к играм для этого профиля приостановлен.", show_alert=True)
        return
    if not isinstance(query.message, Message) or not query.from_user or query.from_user.is_bot:
        await query.answer()
        return
    message = query.message
    if not await _allowed(settings, message, query.from_user.id):
        await query.answer("Командные игры доступны только в теме «Интерактив».", show_alert=True)
        return
    action = (query.data or "").split(":")
    if len(action) < 2:
        await query.answer()
        return
    if user is None:
        user = await session.scalar(select(User).where(User.telegram_id == query.from_user.id))
    if not _registered(user, query.from_user.id):
        if message.chat.type != "private":
            await query.answer(url=_bot_link(settings))
        else:
            await query.answer("Для игры нужна одобренная регистрация в ЭРА.", show_alert=True)
        return
    if action[1] == "cabinet" and message.chat.type == "private":
        await query.answer()
        await show_game_cabinet(message, settings, session, user)
        return
    if message.chat.type != "private" and (action[1] == "solo" or action[1] == "play"):
        mode = "solo" if action[1] == "solo" else action[2] if len(action) == 3 else "solo"
        await query.answer(url=_bot_link(settings, "game_" + mode))
        return
    if message.chat.type == "private" and action[1] in {"team", "duel", "join", "duel_join", "ready", "leave"}:
        await query.answer("Откройте командные игры из раздела «Мои игры».", show_alert=True)
        return
    if action[1] == "play" and len(action) == 3:
        await _start_format(query, settings, session, message, action[2])
        return
    if await _format_action(query, settings, session, message, action):
        return
    if action[1] == "rules":
        rewards = "3 балла за 60% верных ответов; +2 единственному победителю команды. Лимиты: 20/день, 100/неделю, 300/месяц." if settings.games_rewards_enabled else "В тестовом режиме начисление баллов выключено."
        await query.answer("Квиз: 5 вопросов. За ожидание и незавершённую игру баллы не начисляются. " + rewards, show_alert=True)
        return
    if action[1] == "resume":
        keys = [_key(message.chat.id, message.message_thread_id, rid)
                for rid in (f"solo-{query.from_user.id}", "team", "duel")]
        prefix = f"era_game:{message.chat.id}:{message.message_thread_id}:f%"
        rows = (await session.scalars(select(AppSetting).where(
            AppSetting.key.in_(keys) | AppSetting.key.like(prefix)))).all()
        for row in rows:
            room = _data(row)
            if query.from_user.id not in room.get("participants", []):
                continue
            if room.get("status") not in {"waiting", "ready_check", "playing"}:
                continue
            if datetime.fromisoformat(room["expires_at"]) <= datetime.now(timezone.utc):
                continue
            if room.get("mode") == "memory" and not room.get("memory_revealed"):
                ready_at = datetime.fromisoformat(room["memory_ready_at"])
                remaining = max(0.0, (ready_at - datetime.now(timezone.utc)).total_seconds())
                await query.answer("Игра восстановлена.")
                if remaining:
                    await asyncio.sleep(min(remaining, 5))
                await _reveal_memory(session, key=row.key, token=room["token"], message=message)
            else:
                await query.answer("Игра восстановлена в её карточке.")
                await _publish_room(session, row.key, message)
            return
        await query.answer("Открытой игры нет. Выберите новый формат.", show_alert=True)
        return
    if action[1] in {"solo", "team", "duel"} and len(action) == 2:
        kind = action[1]
        room = await _new_room(session, chat_id=message.chat.id, thread_id=message.message_thread_id,
                               user_id=query.from_user.id, kind=kind, questions_per_game=5)
        room_id = kind if kind in {"team", "duel"} else f"solo-{query.from_user.id}"
        key = _key(message.chat.id, message.message_thread_id, room_id)
        if room is None:
            room = _data(await session.scalar(select(AppSetting).where(AppSetting.key == key)))
            if kind in {"team", "duel"} and room.get("status") in {"waiting", "ready_check"}:
                joined = await _join_lobby(session, key, room, query.from_user)
                await session.commit()
                await query.answer("Вы в команде. Состав — в карточке игры." if joined else "Вы уже участвуете или комната заполнена.")
                await _publish_room(session, key, message)
            else:
                await query.answer("Игра уже открыта. Нажмите «Продолжить игру».", show_alert=True)
            return
        if room["status"] == "exhausted":
            await session.commit()
            await query.answer("Новые вопросы готовятся. Выберите игру позже.", show_alert=True)
            return
        remember_player(room, query.from_user)
        await _save(session, key, room)
        await session.commit()
        await query.answer()
        await _publish_room(session, key, message)
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
        await _publish_room(session, key, message)
        await query.answer("Время раунда истекло.")
        return
    uid = query.from_user.id
    remember_player(room, query.from_user)
    if operation in {"join", "duel_join"} and room["status"] in {"waiting", "ready_check"}:
        if uid in room["participants"]:
            await query.answer("Вы уже в команде.")
            return
        if len(room["participants"]) >= MAX_PLAYERS:
            await query.answer("Комната уже заполнена.", show_alert=True)
            return
        await _join_lobby(session, key, room, query.from_user)
        await session.commit()
        team = room.get("teams", {}).get(str(uid))
        await query.answer("Вы в команде " + ("А" if team == "A" else "Б") + "." if team else "Вы в команде. Подтвердите готовность.")
        await _publish_room(session, key, message)
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
            eligible = set((await session.scalars(select(User.telegram_id).where(
                User.telegram_id.in_(room["participants"]), User.application_status == ApplicationStatus.APPROVED,
                User.is_blocked.is_(False), User.is_archived.is_(False)))).all())
            if eligible != set(room["participants"]):
                await query.answer("Один из игроков больше не имеет доступа. Обновите состав комнаты.", show_alert=True)
                return
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
        await _publish_room(session, key, message)
        return
    if operation == "leave" and room["status"] in {"waiting", "ready_check"}:
        if uid not in room["participants"]:
            await query.answer("Ты не участвуешь в этой комнате.")
            return
        room["participants"] = [p for p in room["participants"] if p != uid]
        room.get("teams", {}).pop(str(uid), None)
        if room.get("kind") == "duel":
            room["teams"] = {str(player): "A" if index % 2 == 0 else "B"
                             for index, player in enumerate(room["participants"])}
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
        await _publish_room(session, key, message)
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
            room["finished_at"] = datetime.now(timezone.utc).isoformat()
            room["rewards"] = {}
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
                    room["rewards"][str(player)] = await award_game_points(
                        session, telegram_id=player, round_id=room.get("session_token", room["token"]), amount=3 + bonus)
        elif complete:
            room["position"] = room.get("position", 0) + 1
            room["question"] = questions[room["position"]]
            room["answers"] = {}
            room["token"] = secrets.token_hex(6)
            room["expires_at"] = (datetime.now(timezone.utc) + timedelta(seconds=120)).isoformat()
        await _store_game_result(session, room)
        await _save(session, key, room)
        await session.commit()
        await query.answer("Ответ принят!")
        await _publish_room(session, key, message)
        return
    await query.answer("Сейчас это действие недоступно.")
