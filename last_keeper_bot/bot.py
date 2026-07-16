import asyncio
import csv
import io
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import aiosqlite
from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BufferedInputFile, CallbackQuery, KeyboardButton, Message, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from pydantic_settings import BaseSettings, SettingsConfigDict

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("last_keeper")


class Settings(BaseSettings):
    bot_token: str
    admin_ids: str = ""
    database_path: str = "last_keeper.db"
    event_dates: str = "2026-11-16,2026-11-17"
    team_capacity: int = 30
    location_code_culture: str = "CULT26"
    location_code_science: str = "SCI26"
    location_code_history: str = "HIST26"
    location_code_memory: str = "MEM26"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def admins(self) -> set[int]:
        return {int(x.strip()) for x in self.admin_ids.split(",") if x.strip().isdigit()}

    @property
    def dates(self) -> list[str]:
        return [x.strip() for x in self.event_dates.split(",") if x.strip()]


settings = Settings()
DB = settings.database_path
router = Router()

TEAM_COLORS = ["Красные", "Белые", "Оранжевые", "Зелёные", "Синие"]
LOCATIONS = {
    "culture": {
        "title": "Код культуры",
        "place": "Библиотека, 3 этаж",
        "code": settings.location_code_culture,
        "question": "Что должна сохранить команда?",
        "choices": [
            ("culture_form", "Сохранить исходную форму", {"memory": 2, "truth": 1, "progress": -1}, "Символ сохранён без изменений. Архив стал точнее, но его язык оказался понятен не каждому."),
            ("culture_new", "Передать смысл новым языком", {"unity": 2, "progress": 1, "truth": -1}, "Символ заговорил с новым поколением. Но часть первоначальных деталей растворилась в переводе."),
        ],
    },
    "science": {
        "title": "Цена открытия",
        "place": "Лофт №1, 2 этаж",
        "code": settings.location_code_science,
        "question": "Как поступит команда?",
        "choices": [
            ("science_now", "Открыть доступ сейчас", {"progress": 2, "unity": 1, "responsibility": -1}, "Открытие вышло за стены лаборатории. Мир получил новую возможность раньше, чем успел понять её цену."),
            ("science_check", "Остановиться и проверить", {"responsibility": 2, "truth": 1, "progress": -1}, "Открытие осталось под защитой Архива. Риск уменьшился, но часть времени была потеряна."),
        ],
    },
    "history": {
        "title": "Выбор эпохи",
        "place": "Выставочный зал, 1 этаж",
        "code": settings.location_code_history,
        "question": "Что выберет команда?",
        "choices": [
            ("history_old", "Сохранить прежнюю версию", {"memory": 2, "unity": 1, "truth": -1}, "История сохранила знакомый облик. Но одна страница Архива осталась закрытой."),
            ("history_open", "Открыть найденное свидетельство", {"truth": 2, "responsibility": 1, "unity": -1}, "Свидетельство возвращено в Архив. История стала полнее, но спокойствие оказалось нарушено."),
        ],
    },
    "memory": {
        "title": "Голоса памяти",
        "place": "Лофт №2, 2 этаж",
        "code": settings.location_code_memory,
        "question": "Что должно остаться для будущих поколений?",
        "choices": [
            ("memory_fact", "Сохранить подтверждённый рассказ", {"truth": 2, "memory": 1, "unity": -1}, "Архив сохранил точность. Но один человеческий голос исчез между строками."),
            ("memory_both", "Сохранить оба голоса с пояснением", {"responsibility": 2, "unity": 1, "memory": 1}, "Архив сохранил не только факт, но и переживание. Теперь будущим Хранителям придётся самим различать документ и память человека."),
        ],
    },
}

ROUTES = {
    "Красные": ["culture", "science", "history", "memory", "open"],
    "Белые": ["science", "history", "memory", "open", "culture"],
    "Оранжевые": ["history", "memory", "open", "culture", "science"],
    "Зелёные": ["memory", "open", "culture", "science", "history"],
    "Синие": ["open", "culture", "science", "history", "memory"],
}

TIME_SLOTS = ["11:00–11:40", "11:40–12:20", "12:20–13:00", "13:00–13:40", "13:40–14:15"]


class Reg(StatesGroup):
    consent = State()
    name = State()
    age = State()
    org = State()
    date = State()


class CaptainFlow(StatesGroup):
    code = State()
    confirm = State()


class SupportFlow(StatesGroup):
    text = State()


async def db_exec(query: str, params: tuple = ()):
    Path(DB).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB) as db:
        await db.execute(query, params)
        await db.commit()


async def db_one(query: str, params: tuple = ()):
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(query, params)
        return await cur.fetchone()


async def db_all(query: str, params: tuple = ()):
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(query, params)
        return await cur.fetchall()


async def init_db():
    await db_exec("""
    CREATE TABLE IF NOT EXISTS users(
      telegram_id INTEGER PRIMARY KEY,
      username TEXT,
      full_name TEXT,
      age INTEGER,
      organization TEXT,
      event_date TEXT,
      team TEXT,
      role TEXT DEFAULT 'participant',
      checked_in INTEGER DEFAULT 0,
      created_at TEXT NOT NULL
    )""")
    await db_exec("""
    CREATE TABLE IF NOT EXISTS team_choices(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      event_date TEXT NOT NULL,
      team TEXT NOT NULL,
      location_key TEXT NOT NULL,
      choice_code TEXT NOT NULL,
      selected_by INTEGER NOT NULL,
      effects_json TEXT NOT NULL,
      created_at TEXT NOT NULL,
      UNIQUE(event_date, team, location_key)
    )""")
    await db_exec("""
    CREATE TABLE IF NOT EXISTS support_requests(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      category TEXT,
      message TEXT,
      status TEXT DEFAULT 'open',
      created_at TEXT NOT NULL
    )""")
    await db_exec("""
    CREATE TABLE IF NOT EXISTS settings(
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL
    )""")
    await db_exec("INSERT OR IGNORE INTO settings(key,value) VALUES('final_open','0')")


def main_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="Следующая точка"), KeyboardButton(text="Мой маршрут")],
        [KeyboardButton(text="Состояние Архива"), KeyboardButton(text="Мои фрагменты")],
        [KeyboardButton(text="Позвать Архивариуса"), KeyboardButton(text="Правила")],
    ], resize_keyboard=True)


def inline_buttons(items: list[tuple[str, str]]):
    b = InlineKeyboardBuilder()
    for text, data in items:
        b.button(text=text, callback_data=data)
    b.adjust(1)
    return b.as_markup()


async def get_user(tg_id: int):
    return await db_one("SELECT * FROM users WHERE telegram_id=?", (tg_id,))


async def assign_team(event_date: str) -> str:
    counts = {c: 0 for c in TEAM_COLORS}
    rows = await db_all("SELECT team, COUNT(*) c FROM users WHERE event_date=? AND team IS NOT NULL GROUP BY team", (event_date,))
    for r in rows:
        counts[r["team"]] = r["c"]
    available = [c for c in TEAM_COLORS if counts[c] < settings.team_capacity]
    return min(available or TEAM_COLORS, key=lambda c: counts[c])


async def team_choices(user) -> list:
    return await db_all("SELECT * FROM team_choices WHERE event_date=? AND team=? ORDER BY id", (user["event_date"], user["team"]))


async def parameters(user) -> dict:
    p = {"memory": 0, "truth": 0, "unity": 0, "progress": 0, "responsibility": 0}
    for row in await team_choices(user):
        for k, v in json.loads(row["effects_json"]).items():
            p[k] += v
    return p


def final_archetype(p: dict) -> tuple[str, str]:
    vals = list(p.values())
    if max(vals) - min(vals) <= 2 and p["responsibility"] >= sum(vals) / len(vals):
        return "Общее наследие", "Вы не пытались сохранить прошлое неподвижным и не позволили ему раствориться в переменах. Ваш Архив стал общим наследием — живым, открытым и требующим ответственности от каждого нового Хранителя."
    if p["responsibility"] == max(vals):
        return "Архив ответственности", "Вы не искали простых ответов. Ваш Архив хранит не только события, но и цену решений."
    if p["unity"] >= 3 and p["progress"] >= 2 and p["truth"] < max(p["unity"], p["progress"]):
        return "Живой архив", "Вы сделали память понятной и близкой людям. Архив заговорил живым языком, но часть деталей изменилась при передаче."
    if p["memory"] >= 3 and p["truth"] >= 3 and p["unity"] <= 1:
        return "Закрытый архив", "Вы сохранили точность документов и силу свидетельств. Архив уцелел, но стал закрытым."
    return "Холодный прогресс", "Вы открыли Архив будущему. Он стал быстрым и технологичным, но в нём осталось меньше человеческого голоса и осторожности."


@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    if user:
        await message.answer(f"Архив узнал тебя, {user['full_name']}. Команда: <b>{user['team']}</b>.", reply_markup=main_menu(), parse_mode=ParseMode.HTML)
        return
    await state.set_state(Reg.consent)
    await message.answer("<b>Архив открылся. Но часть его страниц исчезла.</b>\nСегодня тебе предстоит стать Хранителем.\n\nЧтобы сохранить маршрут, Архиву потребуется имя, возраст и Telegram ID.", reply_markup=inline_buttons([("Согласен", "consent:yes"), ("Не согласен", "consent:no")]), parse_mode=ParseMode.HTML)


@router.callback_query(Reg.consent, F.data.startswith("consent:"))
async def consent(callback: CallbackQuery, state: FSMContext):
    if callback.data.endswith("no"):
        await callback.message.edit_text("Без согласия Архив не сможет сохранить твой маршрут.")
        await state.clear()
        return
    await state.set_state(Reg.name)
    await callback.message.edit_text("<b>Как записать тебя в Книгу Хранителей?</b>\nУкажи имя и фамилию.", parse_mode=ParseMode.HTML)


@router.message(Reg.name)
async def reg_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name.split()) < 2:
        await message.answer("Укажи имя и фамилию двумя словами.")
        return
    await state.update_data(full_name=name)
    await state.set_state(Reg.age)
    await message.answer("<b>Сколько тебе лет?</b>\nОсновной маршрут создан для участников от 16 до 26 лет.", parse_mode=ParseMode.HTML)


@router.message(Reg.age)
async def reg_age(message: Message, state: FSMContext):
    if not message.text.isdigit() or not 10 <= int(message.text) <= 99:
        await message.answer("Введи возраст числом.")
        return
    await state.update_data(age=int(message.text))
    await state.set_state(Reg.org)
    await message.answer("<b>Откуда ты пришёл в Архив?</b>\nУкажи университет, организацию или напиши «Пропустить».", parse_mode=ParseMode.HTML)


@router.message(Reg.org)
async def reg_org(message: Message, state: FSMContext):
    await state.update_data(organization="" if message.text.lower() == "пропустить" else message.text.strip())
    await state.set_state(Reg.date)
    await message.answer("<b>Выбери день, когда начнётся твой путь.</b>", reply_markup=inline_buttons([(datetime.fromisoformat(d).strftime("%d ноября"), f"date:{d}") for d in settings.dates]), parse_mode=ParseMode.HTML)


@router.callback_query(Reg.date, F.data.startswith("date:"))
async def reg_date(callback: CallbackQuery, state: FSMContext):
    event_date = callback.data.split(":", 1)[1]
    data = await state.get_data()
    team = await assign_team(event_date)
    role = "admin" if callback.from_user.id in settings.admins else "participant"
    await db_exec("INSERT INTO users(telegram_id,username,full_name,age,organization,event_date,team,role,created_at) VALUES(?,?,?,?,?,?,?,?,?)", (
        callback.from_user.id, callback.from_user.username or "", data["full_name"], data["age"], data["organization"], event_date, team, role, datetime.utcnow().isoformat()
    ))
    await state.clear()
    await callback.message.edit_text(f"<b>Запись сохранена.</b>\nХранитель: {data['full_name']}\nДень: {datetime.fromisoformat(event_date).strftime('%d.%m.%Y')}\nКоманда: <b>{team}</b>", parse_mode=ParseMode.HTML)
    await callback.message.answer("Архив определил твой контур. Не меняй команду самостоятельно.", reply_markup=main_menu())


@router.message(F.text == "Мой маршрут")
async def route(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        return await message.answer("Сначала отправь /start.")
    lines = [f"<b>Маршрут команды «{user['team']}»</b>"]
    for i, key in enumerate(ROUTES[user["team"]]):
        if key == "open":
            title, place = "Открытые пространства", "VR, выставка и фотозона"
        else:
            title, place = LOCATIONS[key]["title"], LOCATIONS[key]["place"]
        lines.append(f"{i+1}. {TIME_SLOTS[i]} — <b>{title}</b>\n   {place}")
    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML)


@router.message(F.text == "Следующая точка")
async def next_point(message: Message):
    user = await get_user(message.from_user.id)
    choices = await team_choices(user)
    done = {r["location_key"] for r in choices}
    for i, key in enumerate(ROUTES[user["team"]]):
        if key == "open":
            continue
        if key not in done:
            loc = LOCATIONS[key]
            kb = inline_buttons([("Ввести код локации", f"open:{key}"), ("Нужна помощь", "support:location")])
            return await message.answer(f"<b>Архив вызывает вашу команду.</b>\nСледующая точка: <b>{loc['title']}</b>\nМесто: {loc['place']}\nВремя: {TIME_SLOTS[i]}", reply_markup=kb, parse_mode=ParseMode.HTML)
    await message.answer("Основной маршрут завершён. Ожидайте открытия общего финала.")


@router.callback_query(F.data.startswith("open:"))
async def open_location(callback: CallbackQuery, state: FSMContext):
    user = await get_user(callback.from_user.id)
    if user["role"] not in ("captain", "admin"):
        return await callback.answer("Код вводит капитан команды.", show_alert=True)
    key = callback.data.split(":", 1)[1]
    await state.update_data(location_key=key)
    await state.set_state(CaptainFlow.code)
    await callback.message.answer("<b>Архив услышал ваш шаг.</b>\nВведите знак, который передал Хранитель локации.", parse_mode=ParseMode.HTML)


@router.message(CaptainFlow.code)
async def location_code(message: Message, state: FSMContext):
    data = await state.get_data()
    key = data["location_key"]
    user = await get_user(message.from_user.id)
    exists = await db_one("SELECT 1 FROM team_choices WHERE event_date=? AND team=? AND location_key=?", (user["event_date"], user["team"], key))
    if exists:
        await state.clear()
        return await message.answer("Эта страница уже восстановлена вашей командой.")
    if message.text.strip().upper() != LOCATIONS[key]["code"].upper():
        return await message.answer("Архив не узнаёт этот знак. Проверь код у Хранителя локации.")
    b = InlineKeyboardBuilder()
    for code, text, _, _ in LOCATIONS[key]["choices"]:
        b.button(text=text, callback_data=f"choice:{key}:{code}")
    b.adjust(1)
    await state.set_state(CaptainFlow.confirm)
    await message.answer(f"Фрагмент найден.\n\n<b>{LOCATIONS[key]['question']}</b>", reply_markup=b.as_markup(), parse_mode=ParseMode.HTML)


@router.callback_query(CaptainFlow.confirm, F.data.startswith("choice:"))
async def choose(callback: CallbackQuery, state: FSMContext):
    _, key, choice_code = callback.data.split(":", 2)
    choice = next(c for c in LOCATIONS[key]["choices"] if c[0] == choice_code)
    await state.update_data(location_key=key, choice_code=choice_code)
    await callback.message.edit_text(f"Вы выбрали: <b>{choice[1]}</b>\n\nПодтвердить решение команды?", reply_markup=inline_buttons([("Подтвердить", f"confirm:{key}:{choice_code}"), ("Изменить", f"redo:{key}")]), parse_mode=ParseMode.HTML)


@router.callback_query(CaptainFlow.confirm, F.data.startswith("redo:"))
async def redo(callback: CallbackQuery, state: FSMContext):
    key = callback.data.split(":", 1)[1]
    b = InlineKeyboardBuilder()
    for code, text, _, _ in LOCATIONS[key]["choices"]:
        b.button(text=text, callback_data=f"choice:{key}:{code}")
    b.adjust(1)
    await callback.message.edit_text(f"<b>{LOCATIONS[key]['question']}</b>", reply_markup=b.as_markup(), parse_mode=ParseMode.HTML)


@router.callback_query(CaptainFlow.confirm, F.data.startswith("confirm:"))
async def confirm_choice(callback: CallbackQuery, state: FSMContext, bot: Bot):
    _, key, choice_code = callback.data.split(":", 2)
    user = await get_user(callback.from_user.id)
    choice = next(c for c in LOCATIONS[key]["choices"] if c[0] == choice_code)
    try:
        await db_exec("INSERT INTO team_choices(event_date,team,location_key,choice_code,selected_by,effects_json,created_at) VALUES(?,?,?,?,?,?,?)", (
            user["event_date"], user["team"], key, choice_code, user["telegram_id"], json.dumps(choice[2]), datetime.utcnow().isoformat()
        ))
    except Exception:
        await state.clear()
        return await callback.message.edit_text("Эта страница уже восстановлена вашей командой.")
    await state.clear()
    await callback.message.edit_text(choice[3])
    members = await db_all("SELECT telegram_id FROM users WHERE event_date=? AND team=? AND telegram_id<>?", (user["event_date"], user["team"], user["telegram_id"]))
    for member in members:
        try:
            await bot.send_message(member["telegram_id"], f"Команда приняла решение в локации «{LOCATIONS[key]['title']}».\n\n{choice[3]}")
        except Exception:
            pass


@router.message(F.text == "Состояние Архива")
async def archive_state(message: Message):
    user = await get_user(message.from_user.id)
    p = await parameters(user)
    labels = {"memory": "Память", "truth": "Истина", "unity": "Связь голосов", "progress": "Прогресс", "responsibility": "Ответственность"}
    phrases = []
    for k, title in labels.items():
        v = p[k]
        phrases.append(f"{title}: {'укрепляется' if v >= 3 else 'остаётся хрупкой' if v <= 0 else 'обретает форму'}.")
    await message.answer("<b>Состояние Архива</b>\n" + "\n".join(phrases), parse_mode=ParseMode.HTML)


@router.message(F.text == "Мои фрагменты")
async def fragments(message: Message):
    user = await get_user(message.from_user.id)
    done = {r["location_key"] for r in await team_choices(user)}
    names = [("culture", "Символ культуры"), ("science", "Печать открытия"), ("history", "Фрагмент времени"), ("memory", "Голос памяти")]
    await message.answer("<b>Мешочек памяти</b>\n" + "\n".join(("✓" if k in done else "○") + " " + n for k, n in names), parse_mode=ParseMode.HTML)


@router.message(F.text == "Правила")
async def rules(message: Message):
    await message.answer("1. Двигайся только со своей командой.\n2. Основные задания выполняются офлайн.\n3. Решение после локации фиксирует капитан.\n4. Ошибка не означает поражение: она меняет последствия.")


@router.message(F.text == "Позвать Архивариуса")
async def support(message: Message):
    await message.answer("Что произошло?", reply_markup=inline_buttons([
        ("Не могу найти локацию", "support:location"), ("Код не работает", "support:code"),
        ("Отстал от команды", "support:lost"), ("Плохо себя чувствую", "support:health"), ("Другой вопрос", "support:other")
    ]))


@router.callback_query(F.data.startswith("support:"))
async def support_category(callback: CallbackQuery, state: FSMContext):
    await state.update_data(category=callback.data.split(":", 1)[1])
    await state.set_state(SupportFlow.text)
    await callback.message.answer("Коротко опиши ситуацию. Сообщение уйдёт организаторам.")


@router.message(SupportFlow.text)
async def support_text(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    user = await get_user(message.from_user.id)
    await db_exec("INSERT INTO support_requests(user_id,category,message,created_at) VALUES(?,?,?,?)", (message.from_user.id, data["category"], message.text, datetime.utcnow().isoformat()))
    text = f"<b>Новое обращение</b>\nУчастник: {user['full_name']}\nTelegram: @{user['username']}\nДень: {user['event_date']}\nКоманда: {user['team']}\nКатегория: {data['category']}\nСообщение: {message.text}"
    for admin in settings.admins:
        try:
            await bot.send_message(admin, text, parse_mode=ParseMode.HTML)
        except Exception:
            pass
    await state.clear()
    await message.answer("Обращение передано Архивариусу.", reply_markup=main_menu())


@router.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id not in settings.admins:
        return
    users = await db_one("SELECT COUNT(*) c FROM users")
    requests = await db_one("SELECT COUNT(*) c FROM support_requests WHERE status='open'")
    teams_done = await db_one("SELECT COUNT(*) c FROM (SELECT event_date,team,COUNT(*) n FROM team_choices GROUP BY event_date,team HAVING n=4)")
    await message.answer(f"<b>Последний хранитель</b>\nЗарегистрировано: {users['c']}\nОбращений без ответа: {requests['c']}\nКоманд завершили маршрут: {teams_done['c']}", reply_markup=inline_buttons([
        ("Назначить капитана", "admin:captain"), ("Открыть финал", "admin:final"), ("Экспорт CSV", "admin:export")
    ]), parse_mode=ParseMode.HTML)


@router.callback_query(F.data == "admin:final")
async def admin_final(callback: CallbackQuery, bot: Bot):
    if callback.from_user.id not in settings.admins:
        return
    await db_exec("UPDATE settings SET value='1' WHERE key='final_open'")
    users = await db_all("SELECT * FROM users")
    for user in users:
        try:
            choices = await team_choices(user)
            if len(choices) < 4:
                continue
            p = await parameters(user)
            title, text = final_archetype(p)
            await bot.send_message(user["telegram_id"], f"<b>Архив собрал все ваши решения.</b>\n\nВаш итог: <b>{title}</b>\n{text}", parse_mode=ParseMode.HTML)
        except Exception:
            pass
    await callback.answer("Финал открыт", show_alert=True)


@router.callback_query(F.data == "admin:export")
async def admin_export(callback: CallbackQuery):
    if callback.from_user.id not in settings.admins:
        return
    rows = await db_all("SELECT * FROM users ORDER BY event_date,team,full_name")
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["telegram_id", "username", "full_name", "age", "organization", "event_date", "team", "role", "checked_in"])
    for r in rows:
        writer.writerow([r[k] for k in ["telegram_id", "username", "full_name", "age", "organization", "event_date", "team", "role", "checked_in"]])
    data = stream.getvalue().encode("utf-8-sig")
    await callback.message.answer_document(BufferedInputFile(data, filename="last_keeper_users.csv"))


@router.callback_query(F.data == "admin:captain")
async def admin_captain_help(callback: CallbackQuery):
    if callback.from_user.id not in settings.admins:
        return
    await callback.message.answer("Назначение капитана: /captain TELEGRAM_ID\nПример: /captain 123456789")


@router.message(Command("captain"))
async def captain(message: Message):
    if message.from_user.id not in settings.admins:
        return
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        return await message.answer("Формат: /captain TELEGRAM_ID")
    await db_exec("UPDATE users SET role='captain' WHERE telegram_id=?", (int(parts[1]),))
    await message.answer("Капитан назначен.")


async def main():
    await init_db()
    bot = Bot(settings.bot_token)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    log.info("Last Keeper bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
