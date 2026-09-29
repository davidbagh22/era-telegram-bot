import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg
from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ChatMemberStatus, ChatType, ParseMode
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, ChatMemberUpdated, InlineKeyboardButton, InlineKeyboardMarkup, Message

log = logging.getLogger(__name__)

COUNTRIES = [
    ("AM", "🇦🇲 Армения"), ("RU", "🇷🇺 Россия"), ("BY", "🇧🇾 Беларусь"),
    ("KZ", "🇰🇿 Казахстан"), ("KG", "🇰🇬 Кыргызстан"), ("UZ", "🇺🇿 Узбекистан"),
    ("TJ", "🇹🇯 Таджикистан"), ("AZ", "🇦🇿 Азербайджан"), ("GE", "🇬🇪 Грузия"),
    ("MD", "🇲🇩 Молдова"), ("OTHER", "🌍 Другая страна"),
]
COUNTRY_MAP = dict(COUNTRIES)
CONTENT_TYPES = [
    ("event", "📅 Мероприятие"), ("online", "💻 Онлайн-встреча"),
    ("opportunity", "🚀 Возможность"), ("contest", "🏆 Конкурс"),
    ("announcement", "📢 Объявление"),
]
TYPE_MAP = dict(CONTENT_TYPES)
REMINDERS = [(10080, "7 дней"), (4320, "3 дня"), (1440, "24 часа"), (180, "3 часа"), (60, "1 час")]

DDL = r'''
CREATE TABLE IF NOT EXISTS users (
  telegram_id BIGINT PRIMARY KEY,
  username TEXT,
  first_name TEXT,
  last_name TEXT,
  country_code TEXT,
  country_name TEXT,
  role TEXT NOT NULL DEFAULT 'viewer' CHECK (role IN ('viewer','editor','admin','owner')),
  onboarding_complete BOOLEAN NOT NULL DEFAULT FALSE,
  telegram_opt_in BOOLEAN NOT NULL DEFAULT TRUE,
  whatsapp_phone TEXT,
  whatsapp_opt_in BOOLEAN NOT NULL DEFAULT FALSE,
  consent_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS states (
  telegram_id BIGINT PRIMARY KEY REFERENCES users(telegram_id) ON DELETE CASCADE,
  state TEXT NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS targets (
  chat_id BIGINT PRIMARY KEY,
  title TEXT NOT NULL,
  username TEXT,
  target_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  network TEXT NOT NULL DEFAULT 'commission',
  country_code TEXT,
  bot_can_post BOOLEAN NOT NULL DEFAULT FALSE,
  added_by BIGINT,
  approved_by BIGINT,
  approved_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS broadcasts (
  id BIGSERIAL PRIMARY KEY,
  content_type TEXT NOT NULL DEFAULT 'event',
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  media_file_id TEXT,
  event_at TIMESTAMPTZ,
  registration_mode TEXT NOT NULL DEFAULT 'none',
  registration_url TEXT,
  registration_deadline TIMESTAMPTZ,
  capacity INTEGER,
  audience JSONB NOT NULL DEFAULT '{}'::jsonb,
  reminder_offsets JSONB NOT NULL DEFAULT '[]'::jsonb,
  status TEXT NOT NULL DEFAULT 'draft',
  created_by BIGINT NOT NULL REFERENCES users(telegram_id),
  reviewed_by BIGINT REFERENCES users(telegram_id),
  review_note TEXT,
  submitted_at TIMESTAMPTZ,
  reviewed_at TIMESTAMPTZ,
  published_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS registrations (
  id BIGSERIAL PRIMARY KEY,
  broadcast_id BIGINT NOT NULL REFERENCES broadcasts(id) ON DELETE CASCADE,
  telegram_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'registered',
  source TEXT NOT NULL DEFAULT 'telegram',
  registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (broadcast_id, telegram_id)
);
CREATE TABLE IF NOT EXISTS reminders (
  id BIGSERIAL PRIMARY KEY,
  broadcast_id BIGINT NOT NULL REFERENCES broadcasts(id) ON DELETE CASCADE,
  remind_at TIMESTAMPTZ NOT NULL,
  offset_minutes INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'scheduled',
  started_at TIMESTAMPTZ,
  sent_at TIMESTAMPTZ,
  UNIQUE (broadcast_id, offset_minutes)
);
CREATE TABLE IF NOT EXISTS deliveries (
  id BIGSERIAL PRIMARY KEY,
  broadcast_id BIGINT NOT NULL REFERENCES broadcasts(id) ON DELETE CASCADE,
  reminder_id BIGINT REFERENCES reminders(id) ON DELETE CASCADE,
  channel TEXT NOT NULL,
  recipient_key TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  error TEXT,
  dedupe_key TEXT NOT NULL UNIQUE,
  sent_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS audit_log (
  id BIGSERIAL PRIMARY KEY,
  actor_telegram_id BIGINT,
  action TEXT NOT NULL,
  entity_type TEXT,
  entity_id TEXT,
  details JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_users_country ON users(country_code) WHERE onboarding_complete = TRUE;
CREATE INDEX IF NOT EXISTS idx_targets_status ON targets(status, network, country_code);
CREATE INDEX IF NOT EXISTS idx_broadcasts_status ON broadcasts(status, event_at);
CREATE INDEX IF NOT EXISTS idx_regs_event ON registrations(broadcast_id, status);
CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(status, remind_at);
'''


def _db_url(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _kb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, callback_data=d) for t, d in row] for row in rows
    ])


def _main_menu(role: str) -> InlineKeyboardMarkup:
    rows: list[list[tuple[str, str]]] = [
        [("📅 Ближайшие", "events:list"), ("🎟 Мои регистрации", "regs:mine")],
        [("👤 Профиль", "profile:view"), ("🔔 Уведомления", "notify:view")],
    ]
    if role in {"editor", "admin", "owner"}:
        rows = [[("➕ Создать публикацию", "b:new")], [("📝 Мои публикации", "b:mine")]] + rows
    if role in {"admin", "owner"}:
        rows += [[("✅ На согласовании", "review:list")], [("📣 Чаты и каналы", "targets:list")], [("📊 Аналитика", "analytics")]]
    return _kb(rows)


def _country_kb(prefix: str) -> InlineKeyboardMarkup:
    rows=[]
    for i in range(0,len(COUNTRIES),2):
        rows.append([(label,f"{prefix}:{code}") for code,label in COUNTRIES[i:i+2]])
    return _kb(rows)


def _fmt_dt(dt: datetime | None) -> str:
    if not dt:
        return ""
    return dt.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")


def _parse_dt(text: str) -> datetime | None:
    try:
        return datetime.strptime(text.strip(), "%d.%m.%Y %H:%M").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


class CommissionBot:
    def __init__(self, database_url: str, token: str, bootstrap_code: str):
        self.database_url = _db_url(database_url)
        self.token = token
        self.bootstrap_code = bootstrap_code
        self.pool: asyncpg.Pool | None = None
        self.bot = Bot(token=token, parse_mode=ParseMode.HTML)
        self.dp = Dispatcher()
        self.router = Router()
        self.dp.include_router(self.router)
        self._register_handlers()

    async def init_db(self) -> None:
        conn = await asyncpg.connect(self.database_url)
        try:
            await conn.execute("CREATE SCHEMA IF NOT EXISTS commission")
        finally:
            await conn.close()
        self.pool = await asyncpg.create_pool(self.database_url, min_size=1, max_size=3, server_settings={"search_path": "commission,public"})
        async with self.pool.acquire() as c:
            await c.execute(DDL)

    async def fetchrow(self, sql: str, *args):
        assert self.pool
        async with self.pool.acquire() as c:
            return await c.fetchrow(sql, *args)

    async def fetch(self, sql: str, *args):
        assert self.pool
        async with self.pool.acquire() as c:
            return await c.fetch(sql, *args)

    async def execute(self, sql: str, *args):
        assert self.pool
        async with self.pool.acquire() as c:
            return await c.execute(sql, *args)

    async def ensure_user(self, u) -> asyncpg.Record:
        return await self.fetchrow(
            """INSERT INTO users(telegram_id,username,first_name,last_name,updated_at)
            VALUES($1,$2,$3,$4,NOW())
            ON CONFLICT(telegram_id) DO UPDATE SET username=EXCLUDED.username,first_name=EXCLUDED.first_name,last_name=EXCLUDED.last_name,updated_at=NOW()
            RETURNING *""",
            u.id, u.username, u.first_name, u.last_name,
        )

    async def state_set(self, uid: int, state: str, payload: dict[str, Any]) -> None:
        await self.execute(
            """INSERT INTO states(telegram_id,state,payload,updated_at) VALUES($1,$2,$3::jsonb,NOW())
            ON CONFLICT(telegram_id) DO UPDATE SET state=EXCLUDED.state,payload=EXCLUDED.payload,updated_at=NOW()""",
            uid, state, json.dumps(payload, ensure_ascii=False),
        )

    async def state_get(self, uid: int):
        return await self.fetchrow("SELECT * FROM states WHERE telegram_id=$1", uid)

    async def state_clear(self, uid: int):
        await self.execute("DELETE FROM states WHERE telegram_id=$1", uid)

    async def audit(self, uid: int | None, action: str, et: str | None = None, eid: Any = None, details: dict | None = None):
        await self.execute(
            "INSERT INTO audit_log(actor_telegram_id,action,entity_type,entity_id,details) VALUES($1,$2,$3,$4,$5::jsonb)",
            uid, action, et, str(eid) if eid is not None else None, json.dumps(details or {}, ensure_ascii=False),
        )

    async def send_menu(self, chat_id: int, user: asyncpg.Record, text="Выберите действие:"):
        await self.bot.send_message(chat_id, text, reply_markup=_main_menu(user["role"]))

    async def start_onboarding(self, chat_id: int, user: asyncpg.Record, pending: dict | None = None):
        await self.state_set(user["telegram_id"], "onboard:country", {"pending": pending})
        await self.bot.send_message(chat_id, "Чтобы получать только релевантные рассылки, выберите страну. Имя и Telegram ID бот получает автоматически.", reply_markup=_country_kb("onb"))

    async def broadcast_text(self, b: asyncpg.Record, reminder=False) -> str:
        prefix = "🔔 <b>Напоминание</b>\n\n" if reminder else ""
        s = f"{prefix}<b>{b['title']}</b>\n\n{b['description']}"
        if b["event_at"]:
            s += f"\n\n📅 {_fmt_dt(b['event_at'])}"
        if b["registration_deadline"]:
            s += f"\n⏳ Регистрация до {_fmt_dt(b['registration_deadline'])}"
        if b["capacity"]:
            s += f"\n👥 Мест: {b['capacity']}"
        return s

    async def send_broadcast(self, chat_id: int, b: asyncpg.Record, direct=False, reminder=False):
        markup=None
        if b["registration_mode"] == "internal":
            if direct:
                markup=_kb([[('✅ Зарегистрироваться',f"reg:{b['id']}")]])
            else:
                me=await self.bot.get_me()
                markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='✅ Зарегистрироваться',url=f"https://t.me/{me.username}?start=reg_{b['id']}")]])
        elif b["registration_mode"] == "external" and b["registration_url"]:
            markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='🔗 Регистрация',url=b['registration_url'])]])
        if b["media_file_id"]:
            await self.bot.send_photo(chat_id,b["media_file_id"],caption=f"<b>{b['title']}</b>")
        return await self.bot.send_message(chat_id,await self.broadcast_text(b,reminder),reply_markup=markup,disable_web_page_preview=True)

    async def register(self, chat_id: int, user: asyncpg.Record, bid: int):
        b=await self.fetchrow("SELECT * FROM broadcasts WHERE id=$1",bid)
        if not b or b["status"] not in {"approved","published"}:
            return await self.bot.send_message(chat_id,"Регистрация сейчас недоступна.")
        if not user["onboarding_complete"]:
            return await self.start_onboarding(chat_id,user,{"type":"register","broadcast_id":bid})
        if b["registration_deadline"] and b["registration_deadline"] < datetime.now(timezone.utc):
            return await self.bot.send_message(chat_id,"Срок регистрации завершён.")
        assert self.pool
        async with self.pool.acquire() as c:
            async with c.transaction():
                br=await c.fetchrow("SELECT * FROM broadcasts WHERE id=$1 FOR UPDATE",bid)
                status="registered"
                if br["capacity"]:
                    count=await c.fetchval("SELECT COUNT(*) FROM registrations WHERE broadcast_id=$1 AND status IN ('registered','attended')",bid)
                    if count >= br["capacity"]:
                        status="waitlist"
                await c.execute("""INSERT INTO registrations(broadcast_id,telegram_id,status,source,updated_at)
                    VALUES($1,$2,$3,'telegram',NOW())
                    ON CONFLICT(broadcast_id,telegram_id) DO UPDATE SET status=EXCLUDED.status,updated_at=NOW()""",bid,user["telegram_id"],status)
        await self.audit(user["telegram_id"],"registration_created","broadcast",bid,{"status":status})
        text="Вы зарегистрированы ✅" if status=="registered" else "Свободных мест пока нет. Вы в листе ожидания ⏳"
        await self.bot.send_message(chat_id,f"{text}\n\n<b>{b['title']}</b>",reply_markup=_kb([[('❌ Отменить регистрацию',f"regcancel:{bid}")]]))

    async def cancel_registration(self, chat_id: int, uid: int, bid: int):
        assert self.pool
        promoted=None
        async with self.pool.acquire() as c:
            async with c.transaction():
                reg=await c.fetchrow("SELECT * FROM registrations WHERE broadcast_id=$1 AND telegram_id=$2 FOR UPDATE",bid,uid)
                if not reg:
                    return await self.bot.send_message(chat_id,"Регистрация не найдена.")
                await c.execute("UPDATE registrations SET status='cancelled',updated_at=NOW() WHERE id=$1",reg["id"])
                if reg["status"]=="registered":
                    promoted=await c.fetchrow("SELECT * FROM registrations WHERE broadcast_id=$1 AND status='waitlist' ORDER BY registered_at LIMIT 1 FOR UPDATE",bid)
                    if promoted:
                        await c.execute("UPDATE registrations SET status='registered',updated_at=NOW() WHERE id=$1",promoted["id"])
        await self.bot.send_message(chat_id,"Регистрация отменена.")
        if promoted:
            b=await self.fetchrow("SELECT title FROM broadcasts WHERE id=$1",bid)
            await self.bot.send_message(promoted["telegram_id"],f"Освободилось место ✅\nВы теперь в основном списке: <b>{b['title']}</b>")

    async def deliver(self, bid: int, reminder_id: int | None = None, reminder=False):
        b=await self.fetchrow("SELECT * FROM broadcasts WHERE id=$1",bid)
        if not b: return
        aud=b["audience"] if isinstance(b["audience"],dict) else json.loads(b["audience"] or '{}')
        countries=aud.get("countries",["ALL"])
        networks=aud.get("networks",["commission"])
        channels=aud.get("channels",{"targets":True,"dm":False})
        suffix=f"r{reminder_id}" if reminder_id else "initial"

        if channels.get("targets"):
            rows=await self.fetch("SELECT * FROM targets WHERE status='approved' AND bot_can_post=TRUE AND network=ANY($1::text[])",networks)
            for t in rows:
                if "ALL" not in countries and t["country_code"] and t["country_code"] not in countries:
                    continue
                key=f"b{bid}:{suffix}:target:{t['chat_id']}"
                if await self.fetchrow("SELECT 1 FROM deliveries WHERE dedupe_key=$1 AND status='sent'",key):
                    continue
                try:
                    await self.send_broadcast(t["chat_id"],b,False,reminder)
                    await self.execute("INSERT INTO deliveries(broadcast_id,reminder_id,channel,recipient_key,status,dedupe_key,sent_at) VALUES($1,$2,'telegram_target',$3,'sent',$4,NOW()) ON CONFLICT DO NOTHING",bid,reminder_id,str(t["chat_id"]),key)
                except Exception as e:
                    await self.execute("INSERT INTO deliveries(broadcast_id,reminder_id,channel,recipient_key,status,error,dedupe_key) VALUES($1,$2,'telegram_target',$3,'failed',$4,$5) ON CONFLICT DO NOTHING",bid,reminder_id,str(t["chat_id"]),str(e)[:500],key)
                await asyncio.sleep(0.05)

        if channels.get("dm"):
            users=await self.fetch("SELECT * FROM users WHERE onboarding_complete=TRUE AND telegram_opt_in=TRUE")
            for u in users:
                if "ALL" not in countries and u["country_code"] not in countries:
                    continue
                key=f"b{bid}:{suffix}:dm:{u['telegram_id']}"
                if await self.fetchrow("SELECT 1 FROM deliveries WHERE dedupe_key=$1 AND status='sent'",key):
                    continue
                try:
                    await self.send_broadcast(u["telegram_id"],b,True,reminder)
                    await self.execute("INSERT INTO deliveries(broadcast_id,reminder_id,channel,recipient_key,status,dedupe_key,sent_at) VALUES($1,$2,'telegram_dm',$3,'sent',$4,NOW()) ON CONFLICT DO NOTHING",bid,reminder_id,str(u["telegram_id"]),key)
                except Exception as e:
                    await self.execute("INSERT INTO deliveries(broadcast_id,reminder_id,channel,recipient_key,status,error,dedupe_key) VALUES($1,$2,'telegram_dm',$3,'failed',$4,$5) ON CONFLICT DO NOTHING",bid,reminder_id,str(u["telegram_id"]),str(e)[:500],key)
                await asyncio.sleep(0.05)

        if reminder and b["registration_mode"]=="internal":
            regs=await self.fetch("SELECT u.* FROM registrations r JOIN users u ON u.telegram_id=r.telegram_id WHERE r.broadcast_id=$1 AND r.status='registered'",bid)
            for u in regs:
                key=f"b{bid}:{suffix}:reg:{u['telegram_id']}"
                if await self.fetchrow("SELECT 1 FROM deliveries WHERE dedupe_key=$1 AND status='sent'",key): continue
                try:
                    await self.send_broadcast(u["telegram_id"],b,True,True)
                    await self.execute("INSERT INTO deliveries(broadcast_id,reminder_id,channel,recipient_key,status,dedupe_key,sent_at) VALUES($1,$2,'telegram_dm',$3,'sent',$4,NOW()) ON CONFLICT DO NOTHING",bid,reminder_id,str(u["telegram_id"]),key)
                except Exception: pass
        if not reminder:
            await self.execute("UPDATE broadcasts SET status='published',published_at=COALESCE(published_at,NOW()),updated_at=NOW() WHERE id=$1",bid)

    async def reminders_loop(self):
        while True:
            try:
                await self.execute("UPDATE reminders SET status='scheduled',started_at=NULL WHERE status='processing' AND started_at < NOW()-INTERVAL '15 minutes'")
                due=await self.fetch("SELECT * FROM reminders WHERE status='scheduled' AND remind_at<=NOW() ORDER BY remind_at LIMIT 10")
                for r in due:
                    changed=await self.fetchrow("UPDATE reminders SET status='processing',started_at=NOW() WHERE id=$1 AND status='scheduled' RETURNING *",r["id"])
                    if not changed: continue
                    try:
                        await self.deliver(r["broadcast_id"],r["id"],True)
                        await self.execute("UPDATE reminders SET status='sent',sent_at=NOW() WHERE id=$1",r["id"])
                    except Exception:
                        log.exception("commission reminder failed")
                        await self.execute("UPDATE reminders SET status='failed' WHERE id=$1",r["id"])
            except Exception:
                log.exception("commission reminder loop")
            await asyncio.sleep(60)

    async def create_reminders(self,b:asyncpg.Record):
        if not b["event_at"]: return
        offsets=b["reminder_offsets"] if isinstance(b["reminder_offsets"],list) else json.loads(b["reminder_offsets"] or '[]')
        for off in offsets:
            at=b["event_at"]-timedelta(minutes=int(off))
            if at>datetime.now(timezone.utc):
                await self.execute("INSERT INTO reminders(broadcast_id,remind_at,offset_minutes,status) VALUES($1,$2,$3,'scheduled') ON CONFLICT DO NOTHING",b["id"],at,int(off))

    def _register_handlers(self):
        r=self.router

        @r.message(CommandStart())
        async def start(m:Message,command:CommandObject):
            u=await self.ensure_user(m.from_user)
            arg=command.args or ""
            if arg.startswith("reg_"):
                bid=int(arg[4:])
                if not u["onboarding_complete"]:
                    return await self.start_onboarding(m.chat.id,u,{"type":"register","broadcast_id":bid})
                return await self.register(m.chat.id,u,bid)
            if not u["onboarding_complete"]:
                return await self.start_onboarding(m.chat.id,u)
            await self.send_menu(m.chat.id,u,"Добро пожаловать в информационный бот Комиссии по взаимодействию с молодёжью.")

        @r.message(Command("claim"))
        async def claim(m:Message,command:CommandObject):
            u=await self.ensure_user(m.from_user)
            if not self.bootstrap_code or (command.args or "").strip()!=self.bootstrap_code:
                return await m.answer("Неверный код.")
            exists=await self.fetchrow("SELECT 1 FROM users WHERE role='owner' LIMIT 1")
            if exists: return await m.answer("Владелец уже назначен.")
            await self.execute("UPDATE users SET role='owner',onboarding_complete=TRUE,telegram_opt_in=TRUE,consent_at=COALESCE(consent_at,NOW()) WHERE telegram_id=$1",u["telegram_id"])
            u=await self.fetchrow("SELECT * FROM users WHERE telegram_id=$1",u["telegram_id"])
            await self.send_menu(m.chat.id,u,"Права владельца активированы ✅")

        @r.message(Command("grant"))
        async def grant(m:Message,command:CommandObject):
            u=await self.ensure_user(m.from_user)
            if u["role"]!="owner": return
            parts=(command.args or "").split()
            if len(parts)!=2 or parts[1] not in {"viewer","editor","admin"}:
                return await m.answer("Формат: /grant TELEGRAM_ID editor|admin|viewer")
            try: uid=int(parts[0])
            except: return await m.answer("Некорректный Telegram ID")
            changed=await self.fetchrow("UPDATE users SET role=$2,updated_at=NOW() WHERE telegram_id=$1 RETURNING *",uid,parts[1])
            if not changed: return await m.answer("Пользователь сначала должен открыть бота и нажать Start.")
            await m.answer("Готово ✅")
            try: await self.bot.send_message(uid,f"Ваша роль изменена: {parts[1]}")
            except: pass

        @r.message(Command("cancel"))
        async def cancel(m:Message):
            u=await self.ensure_user(m.from_user); await self.state_clear(u["telegram_id"]); await self.send_menu(m.chat.id,u,"Действие отменено.")

        @r.callback_query(F.data.startswith("onb:"))
        async def onb_country(c:CallbackQuery):
            await c.answer(); u=await self.ensure_user(c.from_user); code=c.data.split(':',1)[1]
            st=await self.state_get(u["telegram_id"]); payload=dict(st["payload"] or {}) if st else {}
            await self.execute("UPDATE users SET country_code=$2,country_name=$3,updated_at=NOW() WHERE telegram_id=$1",u["telegram_id"],code,COUNTRY_MAP.get(code,code))
            await self.state_set(u["telegram_id"],"onboard:notify",payload)
            await c.message.answer("Хотите получать общие личные рассылки по вашей стране? Напоминания по мероприятиям, на которые вы зарегистрировались, приходят отдельно.",reply_markup=_kb([[('✅ Да','onbnotify:1'),('Нет','onbnotify:0')]]))

        @r.callback_query(F.data.startswith("onbnotify:"))
        async def onb_notify(c:CallbackQuery):
            await c.answer(); uid=c.from_user.id; opt=c.data.endswith(':1'); st=await self.state_get(uid); payload=dict(st["payload"] or {}) if st else {}
            await self.execute("UPDATE users SET onboarding_complete=TRUE,telegram_opt_in=$2,consent_at=COALESCE(consent_at,NOW()),updated_at=NOW() WHERE telegram_id=$1",uid,opt)
            await self.state_clear(uid); u=await self.fetchrow("SELECT * FROM users WHERE telegram_id=$1",uid)
            await c.message.answer(f"Готово ✅\nСтрана: {u['country_name']}\nОбщие рассылки: {'включены' if opt else 'выключены'}")
            pending=payload.get("pending")
            if pending and pending.get("type")=="register": return await self.register(c.message.chat.id,u,int(pending["broadcast_id"]))
            await self.send_menu(c.message.chat.id,u)

        @r.callback_query(F.data=="profile:view")
        async def profile(c:CallbackQuery):
            await c.answer(); u=await self.ensure_user(c.from_user)
            text=f"<b>Профиль</b>\n\n{u['first_name'] or ''} {u['last_name'] or ''}\nСтрана: {u['country_name'] or 'не выбрана'}\nTelegram ID: <code>{u['telegram_id']}</code>\nОбщие рассылки: {'✅' if u['telegram_opt_in'] else '❌'}\nРоль: {u['role']}"
            await c.message.answer(text,reply_markup=_kb([[('🌍 Изменить страну','profile:country')],[('⬅️ Меню','menu')]]))

        @r.callback_query(F.data=="profile:country")
        async def pc(c:CallbackQuery): await c.answer(); await c.message.answer("Выберите страну:",reply_markup=_country_kb("pc"))

        @r.callback_query(F.data.startswith("pc:"))
        async def pcs(c:CallbackQuery):
            await c.answer(); code=c.data.split(':',1)[1]; await self.execute("UPDATE users SET country_code=$2,country_name=$3,updated_at=NOW() WHERE telegram_id=$1",c.from_user.id,code,COUNTRY_MAP.get(code,code)); await c.message.answer("Страна обновлена ✅")

        @r.callback_query(F.data=="notify:view")
        async def nv(c:CallbackQuery):
            await c.answer(); u=await self.ensure_user(c.from_user); await c.message.answer(f"Общие личные Telegram-рассылки: {'✅ включены' if u['telegram_opt_in'] else '❌ выключены'}",reply_markup=_kb([[('Выключить' if u['telegram_opt_in'] else 'Включить','notify:toggle')]]))

        @r.callback_query(F.data=="notify:toggle")
        async def nt(c:CallbackQuery):
            await c.answer(); await self.execute("UPDATE users SET telegram_opt_in=NOT telegram_opt_in,updated_at=NOW() WHERE telegram_id=$1",c.from_user.id); u=await self.fetchrow("SELECT * FROM users WHERE telegram_id=$1",c.from_user.id); await c.message.answer(f"Общие личные рассылки: {'✅ включены' if u['telegram_opt_in'] else '❌ выключены'}")

        @r.callback_query(F.data=="menu")
        async def menu(c:CallbackQuery): await c.answer(); u=await self.ensure_user(c.from_user); await self.send_menu(c.message.chat.id,u)

        @r.callback_query(F.data=="events:list")
        async def events(c:CallbackQuery):
            await c.answer(); rows=await self.fetch("SELECT * FROM broadcasts WHERE status='published' AND event_at IS NOT NULL AND event_at>NOW() ORDER BY event_at LIMIT 10")
            if not rows: return await c.message.answer("Ближайших мероприятий пока нет.")
            await c.message.answer("<b>Ближайшие мероприятия</b>",reply_markup=_kb([[(f"{_fmt_dt(b['event_at'])} · {b['title']}"[:60],f"event:{b['id']}")] for b in rows]))

        @r.callback_query(F.data.startswith("event:"))
        async def ev(c:CallbackQuery): await c.answer(); b=await self.fetchrow("SELECT * FROM broadcasts WHERE id=$1",int(c.data.split(':')[1])); await self.send_broadcast(c.message.chat.id,b,True) if b else None

        @r.callback_query(F.data=="regs:mine")
        async def regs(c:CallbackQuery):
            await c.answer(); rows=await self.fetch("SELECT r.status,b.* FROM registrations r JOIN broadcasts b ON b.id=r.broadcast_id WHERE r.telegram_id=$1 AND r.status<>'cancelled' ORDER BY b.event_at NULLS LAST,b.id DESC LIMIT 20",c.from_user.id)
            if not rows: return await c.message.answer("У вас пока нет активных регистраций.")
            await c.message.answer("<b>Мои регистрации</b>",reply_markup=_kb([[(f"{'⏳' if b['status']=='waitlist' else '✅'} {b['title']}"[:60],f"event:{b['id']}")] for b in rows]))

        @r.callback_query(F.data.startswith("reg:"))
        async def reg(c:CallbackQuery): await c.answer(); u=await self.ensure_user(c.from_user); await self.register(c.message.chat.id,u,int(c.data.split(':')[1]))

        @r.callback_query(F.data.startswith("regcancel:"))
        async def regc(c:CallbackQuery): await c.answer(); await self.cancel_registration(c.message.chat.id,c.from_user.id,int(c.data.split(':')[1]))

        @r.callback_query(F.data=="b:new")
        async def bnew(c:CallbackQuery):
            await c.answer(); u=await self.ensure_user(c.from_user)
            if u["role"] not in {"editor","admin","owner"}: return
            await self.state_set(u["telegram_id"],"b:type",{})
            await c.message.answer("Создание публикации · шаг 1\nВыберите тип:",reply_markup=_kb([[(label,f"b:type:{code}")] for code,label in CONTENT_TYPES]))

        @r.callback_query(F.data.startswith("b:type:"))
        async def btype(c:CallbackQuery): await c.answer(); await self.state_set(c.from_user.id,"b:title",{"content_type":c.data.split(':')[2]}); await c.message.answer("Шаг 2. Отправьте название.")

        @r.message(F.chat.type==ChatType.PRIVATE)
        async def text_state(m:Message):
            u=await self.ensure_user(m.from_user); st=await self.state_get(u["telegram_id"])
            if not st: return
            state=st["state"]; p=dict(st["payload"] or {}); text=(m.text or '').strip()
            if state=="b:title" and text:
                p['title']=text[:180]; await self.state_set(u['telegram_id'],'b:description',p); return await m.answer("Шаг 3. Отправьте описание.")
            if state=="b:description" and text:
                p['description']=text[:3500]; await self.state_set(u['telegram_id'],'b:media',p); return await m.answer("Шаг 4. Пришлите афишу как фото или /skip.")
            if state=="b:media":
                if m.photo: p['media_file_id']=m.photo[-1].file_id
                elif text!='/skip': return await m.answer("Пришлите фото или /skip.")
                await self.state_set(u['telegram_id'],'b:event_at',p); return await m.answer("Шаг 5. Дата и время мероприятия в UTC: <code>15.10.2026 15:00</code> или /skip.")
            if state=="b:event_at":
                if text=='/skip': p['event_at']=None
                else:
                    d=_parse_dt(text)
                    if not d: return await m.answer("Формат: 15.10.2026 15:00")
                    p['event_at']=d.isoformat()
                await self.state_set(u['telegram_id'],'b:regmode',p)
                return await m.answer("Шаг 6. Регистрация:",reply_markup=_kb([[('✅ Внутри бота','b:reg:internal')],[('🔗 Внешняя ссылка','b:reg:external')],[('Без регистрации','b:reg:none')]]))
            if state=="b:regurl":
                if not text.startswith(('http://','https://')): return await m.answer("Нужна ссылка https://...")
                p['registration_url']=text; await self.state_set(u['telegram_id'],'b:deadline',p); return await m.answer("Дедлайн регистрации UTC: 14.10.2026 20:59 или /skip.")
            if state=="b:capacity":
                if text=='/skip': p['capacity']=None
                else:
                    try: p['capacity']=int(text)
                    except: return await m.answer("Введите число или /skip.")
                await self.state_set(u['telegram_id'],'b:deadline',p); return await m.answer("Дедлайн регистрации UTC или /skip.")
            if state=="b:deadline":
                if text=='/skip': p['registration_deadline']=None
                else:
                    d=_parse_dt(text)
                    if not d: return await m.answer("Формат: 14.10.2026 20:59")
                    p['registration_deadline']=d.isoformat()
                p['countries']=['ALL']; await self.state_set(u['telegram_id'],'b:countries',p); return await m.answer("Шаг 7. Выберите страны:",reply_markup=self._countries_multi(p))

        @r.callback_query(F.data.startswith("b:reg:"))
        async def breg(c:CallbackQuery):
            await c.answer(); st=await self.state_get(c.from_user.id); p=dict(st['payload'] or {}) if st else {}; mode=c.data.split(':')[2]; p['registration_mode']=mode
            if mode=='external': await self.state_set(c.from_user.id,'b:regurl',p); return await c.message.answer("Отправьте ссылку регистрации.")
            if mode=='internal': await self.state_set(c.from_user.id,'b:capacity',p); return await c.message.answer("Количество мест? Число или /skip.")
            p['countries']=['ALL']; await self.state_set(c.from_user.id,'b:countries',p); await c.message.answer("Шаг 7. Выберите страны:",reply_markup=self._countries_multi(p))

        @r.callback_query(F.data.startswith("b:country:"))
        async def bcountry(c:CallbackQuery):
            await c.answer(); st=await self.state_get(c.from_user.id); p=dict(st['payload'] or {}); code=c.data.split(':')[2]; s=p.get('countries',[])
            if code=='ALL': s=['ALL']
            else:
                s=[x for x in s if x!='ALL']; s=[x for x in s if x!=code] if code in s else s+[code]
            p['countries']=s; await self.state_set(c.from_user.id,'b:countries',p); await c.message.edit_reply_markup(reply_markup=self._countries_multi(p))

        @r.callback_query(F.data=="b:countries:done")
        async def bcd(c:CallbackQuery):
            await c.answer(); st=await self.state_get(c.from_user.id); p=dict(st['payload'] or {}); p['networks']=['commission']; await self.state_set(c.from_user.id,'b:networks',p); await c.message.answer("Шаг 8. Сети:",reply_markup=self._networks(p))

        @r.callback_query(F.data.startswith("b:network:"))
        async def bn(c:CallbackQuery):
            await c.answer(); st=await self.state_get(c.from_user.id); p=dict(st['payload'] or {}); n=c.data.split(':')[2]; s=p.get('networks',[]); p['networks']=[x for x in s if x!=n] if n in s else s+[n]; await self.state_set(c.from_user.id,'b:networks',p); await c.message.edit_reply_markup(reply_markup=self._networks(p))

        @r.callback_query(F.data=="b:networks:done")
        async def bnd(c:CallbackQuery):
            await c.answer(); st=await self.state_get(c.from_user.id); p=dict(st['payload'] or {}); p['channels']={'targets':True,'dm':False,'whatsapp':False}; await self.state_set(c.from_user.id,'b:channels',p); await c.message.answer("Шаг 9. Каналы доставки:",reply_markup=self._channels(p))

        @r.callback_query(F.data.startswith("b:channel:"))
        async def bch(c:CallbackQuery):
            await c.answer(); st=await self.state_get(c.from_user.id); p=dict(st['payload'] or {}); ch=c.data.split(':')[2]; p.setdefault('channels',{})[ch]=not p.get('channels',{}).get(ch,False); await self.state_set(c.from_user.id,'b:channels',p); await c.message.edit_reply_markup(reply_markup=self._channels(p))

        @r.callback_query(F.data=="b:channels:done")
        async def bchd(c:CallbackQuery):
            await c.answer(); st=await self.state_get(c.from_user.id); p=dict(st['payload'] or {}); p['reminders']=[4320,1440,180,60] if p.get('event_at') else []; await self.state_set(c.from_user.id,'b:reminders',p); await c.message.answer("Шаг 10. Напоминания:",reply_markup=self._reminders(p))

        @r.callback_query(F.data.startswith("b:rem:"))
        async def brm(c:CallbackQuery):
            await c.answer(); st=await self.state_get(c.from_user.id); p=dict(st['payload'] or {}); x=c.data.split(':')[2]
            if x=='none': p['reminders']=[]
            else:
                n=int(x); s=p.get('reminders',[]); p['reminders']=[v for v in s if v!=n] if n in s else s+[n]
            await self.state_set(c.from_user.id,'b:reminders',p); await c.message.edit_reply_markup(reply_markup=self._reminders(p))

        @r.callback_query(F.data=="b:rem:done")
        async def brd(c:CallbackQuery):
            await c.answer(); st=await self.state_get(c.from_user.id); p=dict(st['payload'] or {}); await self.state_set(c.from_user.id,'b:preview',p); await c.message.answer(self._preview(p),reply_markup=_kb([[('✅ Отправить на согласование','b:submit')],[('❌ Отменить','b:abort')]]))

        @r.callback_query(F.data=="b:abort")
        async def ba(c:CallbackQuery): await c.answer(); await self.state_clear(c.from_user.id); u=await self.ensure_user(c.from_user); await self.send_menu(c.message.chat.id,u,"Создание отменено.")

        @r.callback_query(F.data=="b:submit")
        async def bs(c:CallbackQuery):
            await c.answer(); st=await self.state_get(c.from_user.id)
            if not st or st['state']!='b:preview': return
            p=dict(st['payload'] or {}); aud={'countries':p.get('countries',['ALL']),'networks':p.get('networks',['commission']),'channels':p.get('channels',{'targets':True,'dm':False})}
            b=await self.fetchrow("""INSERT INTO broadcasts(content_type,title,description,media_file_id,event_at,registration_mode,registration_url,registration_deadline,capacity,audience,reminder_offsets,status,created_by,submitted_at)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,$11::jsonb,'pending',$12,NOW()) RETURNING *""",
                p.get('content_type','event'),p['title'],p['description'],p.get('media_file_id'),datetime.fromisoformat(p['event_at']) if p.get('event_at') else None,p.get('registration_mode','none'),p.get('registration_url'),datetime.fromisoformat(p['registration_deadline']) if p.get('registration_deadline') else None,p.get('capacity'),json.dumps(aud,ensure_ascii=False),json.dumps(p.get('reminders',[])),c.from_user.id)
            await self.state_clear(c.from_user.id); await self.audit(c.from_user.id,'broadcast_submitted','broadcast',b['id'],aud)
            admins=await self.fetch("SELECT telegram_id FROM users WHERE role IN ('admin','owner')")
            for a in admins:
                try: await self.bot.send_message(a['telegram_id'],f"Новая публикация на согласовании:\n<b>{b['title']}</b>",reply_markup=_kb([[('Проверить',f"review:{b['id']}")]]))
                except: pass
            await c.message.answer(f"Отправлено на согласование ✅\nПубликация #{b['id']}")

        @r.callback_query(F.data=="b:mine")
        async def bm(c:CallbackQuery):
            await c.answer(); rows=await self.fetch("SELECT * FROM broadcasts WHERE created_by=$1 ORDER BY id DESC LIMIT 15",c.from_user.id)
            if not rows: return await c.message.answer("Публикаций пока нет.")
            await c.message.answer("Ваши публикации:",reply_markup=_kb([[(f"#{b['id']} · {b['status']} · {b['title']}"[:60],f"event:{b['id']}")] for b in rows]))

        @r.callback_query(F.data=="review:list")
        async def rl(c:CallbackQuery):
            await c.answer(); u=await self.ensure_user(c.from_user)
            if u['role'] not in {'admin','owner'}: return
            rows=await self.fetch("SELECT * FROM broadcasts WHERE status='pending' ORDER BY submitted_at LIMIT 15")
            if not rows: return await c.message.answer("На согласовании ничего нет.")
            await c.message.answer("На согласовании:",reply_markup=_kb([[(f"#{b['id']} · {b['title']}"[:60],f"review:{b['id']}")] for b in rows]))

        @r.callback_query(F.data.startswith("review:"))
        async def review(c:CallbackQuery):
            if c.data.startswith(('review:approve:','review:return:','review:reject:')): return
            await c.answer(); u=await self.ensure_user(c.from_user)
            if u['role'] not in {'admin','owner'}: return
            bid=int(c.data.split(':')[1]); b=await self.fetchrow("SELECT * FROM broadcasts WHERE id=$1",bid)
            if not b:return
            aud=b['audience'] if isinstance(b['audience'],dict) else json.loads(b['audience'] or '{}')
            text=await self.broadcast_text(b)+f"\n\n<b>Аудитория</b>\nСтраны: {', '.join(aud.get('countries',['ALL']))}\nСети: {', '.join(aud.get('networks',['commission']))}\nКаналы: {', '.join(k for k,v in aud.get('channels',{}).items() if v)}"
            await c.message.answer(text,reply_markup=_kb([[('✅ Одобрить и запустить',f"review:approve:{bid}")],[('↩️ Вернуть',f"review:return:{bid}"),('❌ Отклонить',f"review:reject:{bid}")]]))

        @r.callback_query(F.data.startswith("review:approve:"))
        async def approve(c:CallbackQuery):
            await c.answer(); u=await self.ensure_user(c.from_user)
            if u['role'] not in {'admin','owner'}: return
            bid=int(c.data.split(':')[2]); b=await self.fetchrow("UPDATE broadcasts SET status='approved',reviewed_by=$2,reviewed_at=NOW(),updated_at=NOW() WHERE id=$1 AND status='pending' RETURNING *",bid,u['telegram_id'])
            if not b:return await c.message.answer("Уже обработано.")
            await self.create_reminders(b); await self.audit(u['telegram_id'],'broadcast_approved','broadcast',bid); await c.message.answer("Одобрено ✅ Рассылка запущена."); asyncio.create_task(self.deliver(bid))

        @r.callback_query(F.data.startswith("review:return:"))
        async def ret(c:CallbackQuery):
            await c.answer(); bid=int(c.data.split(':')[2]); u=await self.ensure_user(c.from_user)
            if u['role'] not in {'admin','owner'}: return
            b=await self.fetchrow("UPDATE broadcasts SET status='returned',reviewed_by=$2,reviewed_at=NOW() WHERE id=$1 AND status='pending' RETURNING *",bid,u['telegram_id']); await c.message.answer("Возвращено редактору.")
            if b:
                try: await self.bot.send_message(b['created_by'],f"Публикация #{bid} «{b['title']}» возвращена на доработку.")
                except: pass

        @r.callback_query(F.data.startswith("review:reject:"))
        async def rej(c:CallbackQuery):
            await c.answer(); bid=int(c.data.split(':')[2]); u=await self.ensure_user(c.from_user)
            if u['role'] not in {'admin','owner'}: return
            await self.execute("UPDATE broadcasts SET status='rejected',reviewed_by=$2,reviewed_at=NOW() WHERE id=$1 AND status='pending'",bid,u['telegram_id']); await c.message.answer("Отклонено.")

        @r.my_chat_member()
        async def member(up:ChatMemberUpdated):
            if up.chat.type not in {ChatType.GROUP,ChatType.SUPERGROUP,ChatType.CHANNEL}: return
            s=up.new_chat_member.status
            if s in {ChatMemberStatus.ADMINISTRATOR,ChatMemberStatus.MEMBER}:
                can_post = bool(getattr(up.new_chat_member,'can_post_messages',False)) if up.chat.type==ChatType.CHANNEL else s==ChatMemberStatus.ADMINISTRATOR
                await self.execute("""INSERT INTO targets(chat_id,title,username,target_type,status,bot_can_post,added_by,updated_at)
                    VALUES($1,$2,$3,$4,'pending',$5,$6,NOW()) ON CONFLICT(chat_id) DO UPDATE SET title=EXCLUDED.title,username=EXCLUDED.username,target_type=EXCLUDED.target_type,bot_can_post=EXCLUDED.bot_can_post,status=CASE WHEN targets.status='disabled' THEN 'pending' ELSE targets.status END,updated_at=NOW()""",up.chat.id,up.chat.title or str(up.chat.id),up.chat.username,up.chat.type.value,can_post,up.from_user.id if up.from_user else None)
                admins=await self.fetch("SELECT telegram_id FROM users WHERE role IN ('admin','owner')")
                for a in admins:
                    try: await self.bot.send_message(a['telegram_id'],f"Новый {'канал' if up.chat.type==ChatType.CHANNEL else 'чат'} ожидает подтверждения:\n<b>{up.chat.title}</b>",reply_markup=_kb([[('Открыть',f"target:{up.chat.id}")]]))
                    except: pass
            elif s in {ChatMemberStatus.LEFT,ChatMemberStatus.KICKED}:
                await self.execute("UPDATE targets SET status='disabled',bot_can_post=FALSE WHERE chat_id=$1",up.chat.id)

        @r.callback_query(F.data=="targets:list")
        async def tl(c:CallbackQuery):
            await c.answer(); u=await self.ensure_user(c.from_user)
            if u['role'] not in {'admin','owner'}: return
            rows=await self.fetch("SELECT * FROM targets ORDER BY CASE status WHEN 'pending' THEN 0 WHEN 'approved' THEN 1 ELSE 2 END,updated_at DESC LIMIT 30")
            if not rows:return await c.message.answer("Чаты и каналы ещё не подключены.")
            await c.message.answer("Чаты и каналы:",reply_markup=_kb([[(f"{'🟡' if t['status']=='pending' else '🟢' if t['status']=='approved' else '⚫'} {t['title']}"[:60],f"target:{t['chat_id']}")] for t in rows]))

        @r.callback_query(F.data.startswith("target:"))
        async def target(c:CallbackQuery):
            if c.data.startswith(('target:approve:','target:net:','target:country:')): return
            await c.answer(); u=await self.ensure_user(c.from_user)
            if u['role'] not in {'admin','owner'}: return
            tid=int(c.data.split(':')[1]); t=await self.fetchrow("SELECT * FROM targets WHERE chat_id=$1",tid)
            if not t:return
            await c.message.answer(f"<b>{t['title']}</b>\nТип: {t['target_type']}\nСтатус: {t['status']}\nСеть: {t['network']}\nСтрана: {t['country_code'] or 'международный'}\nПрава публикации: {'✅' if t['bot_can_post'] else '❌'}",reply_markup=_kb([[('Комиссия',f"target:net:{tid}:commission"),('МДС',f"target:net:{tid}:mds")],[('Партнёр',f"target:net:{tid}:partner")],[('🌍 Международный',f"target:country:{tid}:ALL"),('🇦🇲 AM',f"target:country:{tid}:AM"),('🇷🇺 RU',f"target:country:{tid}:RU")],[('✅ Подтвердить',f"target:approve:{tid}")]]))

        @r.callback_query(F.data.startswith("target:net:"))
        async def tn(c:CallbackQuery): await c.answer(); p=c.data.split(':'); await self.execute("UPDATE targets SET network=$2,updated_at=NOW() WHERE chat_id=$1",int(p[2]),p[3]); await c.message.answer("Сеть обновлена.")

        @r.callback_query(F.data.startswith("target:country:"))
        async def tc(c:CallbackQuery): await c.answer(); p=c.data.split(':'); await self.execute("UPDATE targets SET country_code=$2,updated_at=NOW() WHERE chat_id=$1",int(p[2]),None if p[3]=='ALL' else p[3]); await c.message.answer("Страна обновлена.")

        @r.callback_query(F.data.startswith("target:approve:"))
        async def ta(c:CallbackQuery):
            await c.answer(); u=await self.ensure_user(c.from_user)
            if u['role'] not in {'admin','owner'}:return
            tid=int(c.data.split(':')[2]); t=await self.fetchrow("UPDATE targets SET status='approved',approved_by=$2,approved_at=NOW(),updated_at=NOW() WHERE chat_id=$1 RETURNING *",tid,u['telegram_id']); await c.message.answer(f"Подключено ✅\n{t['title'] if t else ''}")

        @r.callback_query(F.data=="analytics")
        async def an(c:CallbackQuery):
            await c.answer(); u=await self.ensure_user(c.from_user)
            if u['role'] not in {'admin','owner'}:return
            s=await self.fetchrow("SELECT (SELECT COUNT(*) FROM users WHERE onboarding_complete) users,(SELECT COUNT(*) FROM targets WHERE status='approved') targets,(SELECT COUNT(*) FROM broadcasts WHERE status='published') published,(SELECT COUNT(*) FROM registrations WHERE status='registered') regs,(SELECT COUNT(*) FROM deliveries WHERE status='sent') sent,(SELECT COUNT(*) FROM deliveries WHERE status='failed') failed")
            countries=await self.fetch("SELECT country_name,COUNT(*) c FROM users WHERE onboarding_complete GROUP BY country_name ORDER BY c DESC LIMIT 10")
            await c.message.answer(f"<b>Аналитика</b>\n\nПользователи: {s['users']}\nЧаты/каналы: {s['targets']}\nОпубликовано: {s['published']}\nАктивные регистрации: {s['regs']}\nДоставлено: {s['sent']}\nОшибки: {s['failed']}\n\n<b>По странам</b>\n"+'\n'.join(f"{x['country_name'] or '—'}: {x['c']}" for x in countries))

    def _countries_multi(self,p):
        sel=p.get('countries',[]); rows=[[('✅ ' if 'ALL' in sel else '')+'🌍 Все страны','b:country:ALL']]
        opts=[((('✅ ' if c in sel else '')+l),f"b:country:{c}") for c,l in COUNTRIES]
        for i in range(0,len(opts),2): rows.append(opts[i:i+2])
        rows.append([('Готово →','b:countries:done')]); return _kb(rows)

    def _networks(self,p):
        s=p.get('networks',[]); return _kb([[((('✅ ' if 'commission' in s else '')+'Комиссия'),'b:network:commission'),((('✅ ' if 'mds' in s else '')+'МДС'),'b:network:mds')],[((('✅ ' if 'partner' in s else '')+'Партнёры'),'b:network:partner')],[('Готово →','b:networks:done')]])

    def _channels(self,p):
        c=p.get('channels',{}); return _kb([[(('✅ ' if c.get('targets') else '⬜ ')+'Чаты и каналы Telegram','b:channel:targets')],[(('✅ ' if c.get('dm') else '⬜ ')+'Личные Telegram','b:channel:dm')],[(('✅ ' if c.get('whatsapp') else '⬜ ')+'WhatsApp (после API)','b:channel:whatsapp')],[('Готово →','b:channels:done')]])

    def _reminders(self,p):
        s=p.get('reminders',[]); rows=[]
        for i in range(0,len(REMINDERS),2): rows.append([((('✅ ' if m in s else '⬜ ')+l),f"b:rem:{m}") for m,l in REMINDERS[i:i+2]])
        rows += [[('Без напоминаний','b:rem:none')],[('Предпросмотр →','b:rem:done')]]; return _kb(rows)

    def _preview(self,p):
        return f"<b>Предпросмотр</b>\n\n<b>{p.get('title','')}</b>\n\n{p.get('description','')}\n\nТип: {TYPE_MAP.get(p.get('content_type'),p.get('content_type'))}\nДата: {p.get('event_at') or 'без даты'}\nРегистрация: {p.get('registration_mode','none')}\nСтраны: {', '.join(p.get('countries',['ALL']))}\nСети: {', '.join(p.get('networks',['commission']))}\nКаналы: {', '.join(k for k,v in p.get('channels',{}).items() if v)}"

    async def run(self):
        await self.init_db()
        await self.bot.set_my_description("Единый информационный бот Комиссии по взаимодействию с молодёжью: мероприятия, регистрации, уведомления и возможности.")
        await self.bot.set_my_short_description("Мероприятия, регистрации и уведомления Комиссии")
        await self.bot.delete_webhook(drop_pending_updates=False)
        reminder_task=asyncio.create_task(self.reminders_loop())
        try:
            await self.dp.start_polling(self.bot,allowed_updates=self.dp.resolve_used_update_types())
        finally:
            reminder_task.cancel()
            if self.pool: await self.pool.close()
            await self.bot.session.close()


async def run_commission_bot(database_url: str) -> None:
    token=os.getenv("COMMISSION_BOT_TOKEN","").strip()
    if not token:
        log.info("COMMISSION_BOT_TOKEN not set; commission bot disabled")
        return
    bootstrap=os.getenv("COMMISSION_BOOTSTRAP_CODE","").strip()
    app=CommissionBot(database_url,token,bootstrap)
    await app.run()
