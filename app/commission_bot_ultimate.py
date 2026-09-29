from __future__ import annotations

import asyncio
import html
import io
import json
import logging
import os
import secrets
from datetime import datetime, timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo

import qrcode
from aiogram import F
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter, TelegramServerError
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.commission_bot import COUNTRY_MAP, _kb
from app.commission_bot_plus import CommissionBotPlus, _role_label

log = logging.getLogger(__name__)

DEFAULT_TZ = "Asia/Yerevan"
TZ_OPTIONS = [
    ("Asia/Yerevan", "🇦🇲 Ереван"),
    ("Europe/Moscow", "🇷🇺 Москва"),
    ("Europe/Minsk", "🇧🇾 Минск"),
    ("Asia/Almaty", "🇰🇿 Алматы"),
    ("Asia/Bishkek", "🇰🇬 Бишкек"),
    ("Asia/Tashkent", "🇺🇿 Ташкент"),
    ("Asia/Dushanbe", "🇹🇯 Душанбе"),
    ("Asia/Tbilisi", "🇬🇪 Тбилиси"),
]
TZ_LABELS = dict(TZ_OPTIONS)

ULTIMATE_DDL = r"""
ALTER TABLE users ADD COLUMN IF NOT EXISTS timezone_name TEXT NOT NULL DEFAULT 'Asia/Yerevan';
ALTER TABLE users ADD COLUMN IF NOT EXISTS registration_consent_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS privacy_policy_version TEXT;
ALTER TABLE broadcasts ADD COLUMN IF NOT EXISTS event_timezone TEXT NOT NULL DEFAULT 'Asia/Yerevan';
ALTER TABLE broadcasts ADD COLUMN IF NOT EXISTS event_format TEXT;
ALTER TABLE broadcasts ADD COLUMN IF NOT EXISTS event_location TEXT;
ALTER TABLE broadcasts ADD COLUMN IF NOT EXISTS publish_at TIMESTAMPTZ;
ALTER TABLE broadcasts ADD COLUMN IF NOT EXISTS checkin_token TEXT;
ALTER TABLE broadcasts ADD COLUMN IF NOT EXISTS custom_questions JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE deliveries ADD COLUMN IF NOT EXISTS message_id BIGINT;
ALTER TABLE deliveries ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0;
CREATE TABLE IF NOT EXISTS registration_drafts (
  broadcast_id BIGINT NOT NULL REFERENCES broadcasts(id) ON DELETE CASCADE,
  telegram_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
  answers JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (broadcast_id, telegram_id)
);
CREATE INDEX IF NOT EXISTS idx_broadcasts_publish_due ON broadcasts(status, publish_at) WHERE status='scheduled';
"""

def _safe(v) -> str:
    return html.escape(str(v or ""))

def _localize(dt: datetime | None, tz_name: str | None) -> str:
    if not dt:
        return ""
    try:
        z = ZoneInfo(tz_name or DEFAULT_TZ)
    except Exception:
        z = ZoneInfo(DEFAULT_TZ)
    label = TZ_LABELS.get(tz_name or DEFAULT_TZ, tz_name or DEFAULT_TZ)
    return dt.astimezone(z).strftime("%d.%m.%Y %H:%M") + f" · {label}"

def _parse_local(text: str, tz_name: str) -> datetime | None:
    try:
        naive = datetime.strptime(text.strip(), "%d.%m.%Y %H:%M")
        return naive.replace(tzinfo=ZoneInfo(tz_name)).astimezone(timezone.utc)
    except Exception:
        return None

class CommissionBotUltimate(CommissionBotPlus):
    async def init_db(self) -> None:
        await super().init_db()
        await self.execute(ULTIMATE_DDL)

    def _channels(self, p):
        c = p.get("channels", {})
        return _kb([
            [(("✅ " if c.get("targets") else "⬜ ") + "Чаты и каналы Telegram", "b:channel:targets")],
            [(("✅ " if c.get("dm") else "⬜ ") + "Личные Telegram", "b:channel:dm")],
            [("Готово →", "b:channels:done")],
        ])

    def _preview(self, p):
        tz_name = p.get("event_timezone", DEFAULT_TZ)
        event_at = datetime.fromisoformat(p["event_at"]) if p.get("event_at") else None
        deadline = datetime.fromisoformat(p["registration_deadline"]) if p.get("registration_deadline") else None
        fmt = {"offline": "Очно", "online": "Онлайн", "hybrid": "Гибрид"}.get(p.get("event_format"), "—")
        questions = p.get("custom_questions", [])
        return (
            f"<b>Предпросмотр</b>\n\n<b>{_safe(p.get('title',''))}</b>\n\n{_safe(p.get('description',''))}"
            f"\n\n📅 {_localize(event_at, tz_name) if event_at else 'без даты'}"
            f"\n📍 {fmt}" + (f" · {_safe(p.get('event_location'))}" if p.get("event_location") else "") +
            f"\n🎟 Регистрация: {p.get('registration_mode','none')}"
            + (f"\n⏳ До: {_localize(deadline, tz_name)}" if deadline else "")
            + (f"\n❓ Доп. вопросов: {len(questions)}" if questions else "")
            + f"\n🌍 Страны: {', '.join(p.get('countries',['ALL']))}"
            + f"\n📡 Сети: {', '.join(p.get('networks',['commission']))}"
        )

    async def send_menu(self, chat_id: int, user, text: str = "Выберите действие:"):
        role = user["role"]
        if text.startswith("Добро пожаловать") or text == "Выберите действие:":
            text = (
                "<b>МОЛОДЁЖЬ ВКСРС</b>\n\n"
                "Единый цифровой центр Комиссии по взаимодействию с молодёжью: "
                "мероприятия, возможности, регистрации, напоминания и работа команды — в одном месте.\n\n"
                "Выберите раздел:"
            )
        rows = [
            [("📅 Мероприятия", "events:list"), ("🎟 Мои регистрации", "regs:mine")],
            [("👤 Профиль", "profile:view"), ("🔔 Уведомления", "notify:view")],
        ]
        if role in {"editor", "admin", "owner"}:
            rows = [[("➕ Создать публикацию", "b:new")], [("📝 Мои публикации", "b:mine"), ("📋 Регистрации", "regadmin:list")]] + rows
        if role in {"admin", "owner"}:
            rows += [[("✅ Согласование", "review:list"), ("📣 Каналы", "targets:list")], [("📊 Аналитика", "analytics")]]
        if role == "owner":
            rows += [[("👥 Команда", "team:menu")]]
        await self.bot.send_message(chat_id, text, reply_markup=_kb(rows))

    async def broadcast_text(self, b, reminder=False) -> str:
        prefix = "🔔 <b>Напоминание</b>\n\n" if reminder else ""
        s = f"{prefix}<b>{_safe(b['title'])}</b>\n\n{_safe(b['description'])}"
        if b["event_at"]:
            s += f"\n\n📅 {_localize(b['event_at'], b['event_timezone'])}"
        if b["event_format"]:
            labels = {"offline": "Очно", "online": "Онлайн", "hybrid": "Гибрид"}
            s += f"\n📍 Формат: {labels.get(b['event_format'], _safe(b['event_format']))}"
        if b["event_location"]:
            s += f"\n📌 {_safe(b['event_location'])}"
        if b["registration_deadline"]:
            s += f"\n⏳ Регистрация до {_localize(b['registration_deadline'], b['event_timezone'])}"
        if b["capacity"]:
            s += f"\n👥 Мест: {b['capacity']}"
        return s

    async def send_broadcast(self, chat_id: int, b, direct=False, reminder=False):
        markup = None
        if b["registration_mode"] == "internal":
            if direct:
                markup = _kb([[("✅ Зарегистрироваться", f"reg:{b['id']}")]])
            else:
                me = await self.bot.get_me()
                markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Зарегистрироваться", url=f"https://t.me/{me.username}?start=reg_{b['id']}")]])
        elif b["registration_mode"] == "external" and b["registration_url"]:
            markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔗 Регистрация", url=b["registration_url"])]] )
        if b["media_file_id"]:
            await self.bot.send_photo(chat_id, b["media_file_id"], caption=f"<b>{_safe(b['title'])}</b>")
        return await self.bot.send_message(chat_id, await self.broadcast_text(b, reminder), reply_markup=markup, disable_web_page_preview=True)

    async def _send_with_retry(self, chat_id: int, b, direct=False, reminder=False):
        last = None
        for attempt in range(1, 4):
            try:
                msg = await self.send_broadcast(chat_id, b, direct, reminder)
                return msg, attempt, None
            except TelegramRetryAfter as e:
                last = e
                await asyncio.sleep(min(float(e.retry_after) + 0.25, 30))
            except (TelegramNetworkError, TelegramServerError) as e:
                last = e
                await asyncio.sleep(attempt * 1.5)
            except Exception as e:
                last = e
                break
        return None, 3, last

    async def deliver(self, bid: int, reminder_id: int | None = None, reminder=False):
        b = await self.fetchrow("SELECT * FROM broadcasts WHERE id=$1", bid)
        if not b:
            return
        aud = b["audience"] if isinstance(b["audience"], dict) else json.loads(b["audience"] or "{}")
        countries = aud.get("countries", ["ALL"])
        networks = aud.get("networks", ["commission"])
        channels = aud.get("channels", {"targets": True, "dm": False})
        suffix = f"r{reminder_id}" if reminder_id else "initial"
        async def one(channel, recipient, direct):
            key = f"b{bid}:{suffix}:{channel}:{recipient}"
            if await self.fetchrow("SELECT 1 FROM deliveries WHERE dedupe_key=$1 AND status='sent'", key):
                return
            msg, attempts, error = await self._send_with_retry(int(recipient), b, direct, reminder)
            if msg:
                await self.execute("""INSERT INTO deliveries(broadcast_id,reminder_id,channel,recipient_key,status,dedupe_key,sent_at,message_id,attempts)
                    VALUES($1,$2,$3,$4,'sent',$5,NOW(),$6,$7)
                    ON CONFLICT(dedupe_key) DO UPDATE SET status='sent',error=NULL,sent_at=NOW(),message_id=EXCLUDED.message_id,attempts=EXCLUDED.attempts""",
                    bid, reminder_id, channel, str(recipient), key, msg.message_id, attempts)
            else:
                await self.execute("""INSERT INTO deliveries(broadcast_id,reminder_id,channel,recipient_key,status,error,dedupe_key,attempts)
                    VALUES($1,$2,$3,$4,'failed',$5,$6,$7)
                    ON CONFLICT(dedupe_key) DO UPDATE SET status='failed',error=EXCLUDED.error,attempts=EXCLUDED.attempts""",
                    bid, reminder_id, channel, str(recipient), str(error)[:500] if error else "unknown", key, attempts)
        if channels.get("targets"):
            rows = await self.fetch("SELECT * FROM targets WHERE status='approved' AND bot_can_post=TRUE AND network=ANY($1::text[])", networks)
            for t in rows:
                if "ALL" not in countries and (not t["country_code"] or t["country_code"] not in countries):
                    continue
                await one("telegram_target", t["chat_id"], False)
                await asyncio.sleep(0.05)
        if channels.get("dm"):
            users = await self.fetch("SELECT * FROM users WHERE onboarding_complete=TRUE AND telegram_opt_in=TRUE")
            for u in users:
                if "ALL" not in countries and u["country_code"] not in countries:
                    continue
                await one("telegram_dm", u["telegram_id"], True)
                await asyncio.sleep(0.05)
        if reminder and b["registration_mode"] == "internal":
            regs = await self.fetch("SELECT u.* FROM registrations r JOIN users u ON u.telegram_id=r.telegram_id WHERE r.broadcast_id=$1 AND r.status IN ('registered','attended')", bid)
            for u in regs:
                await one("telegram_reg", u["telegram_id"], True)
        if not reminder:
            await self.execute("UPDATE broadcasts SET status='published',published_at=COALESCE(published_at,NOW()),updated_at=NOW() WHERE id=$1", bid)

    async def reminders_loop(self):
        while True:
            try:
                due_publications = await self.fetch("SELECT id FROM broadcasts WHERE status='scheduled' AND publish_at<=NOW() ORDER BY publish_at LIMIT 10")
                for row in due_publications:
                    changed = await self.fetchrow("UPDATE broadcasts SET status='approved',updated_at=NOW() WHERE id=$1 AND status='scheduled' RETURNING id", row["id"])
                    if changed:
                        b = await self.fetchrow("SELECT * FROM broadcasts WHERE id=$1", row["id"])
                        if b:
                            await self.create_reminders(b)
                        asyncio.create_task(self.deliver(row["id"]))
                await self.execute("UPDATE reminders SET status='scheduled',started_at=NULL WHERE status='processing' AND started_at < NOW()-INTERVAL '15 minutes'")
                due = await self.fetch("SELECT * FROM reminders WHERE status IN ('scheduled','failed') AND remind_at<=NOW() ORDER BY remind_at LIMIT 10")
                for rr in due:
                    changed = await self.fetchrow("UPDATE reminders SET status='processing',started_at=NOW() WHERE id=$1 AND status IN ('scheduled','failed') RETURNING *", rr["id"])
                    if not changed:
                        continue
                    try:
                        await self.deliver(rr["broadcast_id"], rr["id"], True)
                        await self.execute("UPDATE reminders SET status='sent',sent_at=NOW() WHERE id=$1", rr["id"])
                    except Exception:
                        log.exception("commission reminder failed")
                        await self.execute("UPDATE reminders SET status='failed' WHERE id=$1", rr["id"])
            except Exception:
                log.exception("commission scheduler loop")
            await asyncio.sleep(30)

    async def register(self, chat_id: int, user, bid: int):
        b = await self.fetchrow("SELECT * FROM broadcasts WHERE id=$1", bid)
        if not b:
            return await self.bot.send_message(chat_id, "Регистрация сейчас недоступна.")
        if not user["registration_consent_at"]:
            await self.state_set(user["telegram_id"], "privacy:register", {"broadcast_id": bid})
            return await self.bot.send_message(chat_id,
                "<b>Регистрация и персональные данные</b>\n\nДля регистрации бот сохранит ваш Telegram ID и данные анкеты, если они потребуются организатору. Они используются только для организации мероприятий и коммуникации по ним.\n\nВы сможете удалить сохранённые данные из профиля.",
                reply_markup=_kb([[("✅ Согласен и продолжить", f"privacy:accept:{bid}")], [("Отмена", "menu")]]))
        questions = b["custom_questions"] if isinstance(b["custom_questions"], list) else json.loads(b["custom_questions"] or "[]")
        if questions:
            draft = await self.fetchrow("SELECT answers FROM registration_drafts WHERE broadcast_id=$1 AND telegram_id=$2", bid, user["telegram_id"])
            if not draft:
                await self.state_set(user["telegram_id"], "regcustom:0", {"broadcast_id": bid, "answers": {}})
                return await self.bot.send_message(chat_id, f"1/{len(questions)}. {_safe(questions[0])}")
        result = await super().register(chat_id, user, bid)
        draft = await self.fetchrow("SELECT answers FROM registration_drafts WHERE broadcast_id=$1 AND telegram_id=$2", bid, user["telegram_id"])
        reg = await self.fetchrow("SELECT id,answers FROM registrations WHERE broadcast_id=$1 AND telegram_id=$2", bid, user["telegram_id"])
        if draft and reg:
            base = dict(reg["answers"] or {})
            base["custom"] = dict(draft["answers"] or {})
            await self.execute("UPDATE registrations SET answers=$2::jsonb,updated_at=NOW() WHERE id=$1", reg["id"], json.dumps(base, ensure_ascii=False))
            await self.execute("DELETE FROM registration_drafts WHERE broadcast_id=$1 AND telegram_id=$2", bid, user["telegram_id"])
        return result

    async def _resend_update(self, bid: int):
        b = await self.fetchrow("SELECT * FROM broadcasts WHERE id=$1", bid)
        if not b or b["status"] != "published":
            return
        rows = await self.fetch("""SELECT DISTINCT ON (recipient_key,channel) recipient_key,channel,message_id FROM deliveries
            WHERE broadcast_id=$1 AND status='sent' AND reminder_id IS NULL AND message_id IS NOT NULL
            ORDER BY recipient_key,channel,id DESC""", bid)
        text = await self.broadcast_text(b)
        for d in rows:
            try:
                await self.bot.edit_message_text(text, chat_id=int(d["recipient_key"]), message_id=d["message_id"], disable_web_page_preview=True)
            except Exception:
                try:
                    await self.bot.send_message(int(d["recipient_key"]), "✏️ <b>Обновление мероприятия</b>\n\n" + text, disable_web_page_preview=True)
                except Exception:
                    pass

    def _register_handlers(self):
        r = self.router

        @r.message(F.text.startswith("/start checkin_"))
        async def checkin_start(m: Message):
            user = await self.ensure_user(m.from_user)
            payload = (m.text or "").split("checkin_", 1)[1].strip().split()[0]
            try:
                bid_s, token = payload.split("_", 1); bid = int(bid_s)
            except Exception:
                return await m.answer("Некорректный QR-код.")
            b = await self.fetchrow("SELECT id,title,checkin_token FROM broadcasts WHERE id=$1", bid)
            if not b or not b["checkin_token"] or not secrets.compare_digest(b["checkin_token"], token):
                return await m.answer("QR-код недействителен.")
            reg = await self.fetchrow("SELECT * FROM registrations WHERE broadcast_id=$1 AND telegram_id=$2", bid, user["telegram_id"])
            if not reg: return await m.answer("Вы не зарегистрированы на это мероприятие.")
            if reg["status"] == "waitlist": return await m.answer("Вы пока в листе ожидания — check-in недоступен.")
            if reg["status"] == "cancelled": return await m.answer("Регистрация отменена.")
            await self.execute("UPDATE registrations SET status='attended',updated_at=NOW() WHERE id=$1", reg["id"])
            await m.answer(f"Check-in подтверждён ✅\n\n<b>{_safe(b['title'])}</b>")

        @r.callback_query(F.data.startswith("privacy:accept:"))
        async def privacy_accept(c: CallbackQuery):
            await c.answer(); bid = int(c.data.split(":")[2])
            await self.execute("UPDATE users SET registration_consent_at=NOW(),privacy_policy_version='2026-09',updated_at=NOW() WHERE telegram_id=$1", c.from_user.id)
            await self.state_clear(c.from_user.id)
            u = await self.fetchrow("SELECT * FROM users WHERE telegram_id=$1", c.from_user.id)
            await self.register(c.message.chat.id, u, bid)

        @r.callback_query(F.data == "privacy:delete")
        async def privacy_delete(c: CallbackQuery):
            await c.answer()
            await c.message.answer("<b>Удалить данные анкеты?</b>\n\nБудут удалены ваши регистрации и данные участника. Роль сотрудника, если она есть, сохранится.", reply_markup=_kb([[('🗑 Да, удалить','privacy:delete:confirm')],[('Отмена','profile:view')]]))

        @r.callback_query(F.data == "privacy:delete:confirm")
        async def privacy_delete_confirm(c: CallbackQuery):
            await c.answer(); assert self.pool
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute("DELETE FROM registrations WHERE telegram_id=$1", c.from_user.id)
                    await conn.execute("DELETE FROM registration_drafts WHERE telegram_id=$1", c.from_user.id)
                    await conn.execute("""UPDATE users SET registration_name=NULL,organization=NULL,phone=NULL,email=NULL,
                        participant_profile_complete=FALSE,registration_consent_at=NULL,privacy_policy_version=NULL,
                        telegram_opt_in=FALSE,updated_at=NOW() WHERE telegram_id=$1""", c.from_user.id)
            await c.message.answer("Данные анкеты и регистрации удалены ✅")

        @r.callback_query(F.data == "profile:view")
        async def profile(c: CallbackQuery):
            await c.answer(); u = await self.ensure_user(c.from_user)
            name = " ".join(v for v in [u["first_name"],u["last_name"]] if v).strip()
            text = (f"<b>Профиль</b>\n\n{_safe(name)}\nСтрана: {_safe(u['country_name'] or 'не выбрана')}\n"
                f"Часовой пояс: {_safe(TZ_LABELS.get(u['timezone_name'],u['timezone_name']))}\nРоль: <b>{_role_label(u['role'])}</b>\n"
                f"Общие рассылки: {'✅' if u['telegram_opt_in'] else '❌'}\nАнкета участника: {'✅' if u['participant_profile_complete'] else '—'}")
            await c.message.answer(text, reply_markup=_kb([[('🌍 Изменить страну','profile:country'),('🕒 Часовой пояс','profile:tz')],[('🗑 Удалить мои данные','privacy:delete')],[('⬅️ Меню','menu')]]))

        @r.callback_query(F.data == "profile:tz")
        async def profile_tz(c: CallbackQuery):
            await c.answer(); rows=[]
            for i in range(0,len(TZ_OPTIONS),2): rows.append([(label,f"profile:tzset:{tz}") for tz,label in TZ_OPTIONS[i:i+2]])
            await c.message.answer("Выберите часовой пояс:",reply_markup=_kb(rows))

        @r.callback_query(F.data.startswith("profile:tzset:"))
        async def profile_tzset(c: CallbackQuery):
            await c.answer(); tz=c.data.split(":",2)[2]
            if tz not in TZ_LABELS: return
            await self.execute("UPDATE users SET timezone_name=$2,updated_at=NOW() WHERE telegram_id=$1",c.from_user.id,tz)
            await c.message.answer(f"Часовой пояс обновлён: {TZ_LABELS[tz]} ✅")

        @r.message(F.chat.type == ChatType.PRIVATE)
        async def ultimate_state(m: Message):
            u=await self.ensure_user(m.from_user); st=await self.state_get(u["telegram_id"])
            if not st: raise SkipHandler
            state=str(st["state"]); p=dict(st["payload"] or {}); text=(m.text or "").strip(); tz_name=u["timezone_name"] or DEFAULT_TZ
            if state=="b:media":
                if m.photo: p["media_file_id"]=m.photo[-1].file_id
                elif text!="/skip": return await m.answer("Пришлите фото или /skip.")
                p["event_timezone"]=tz_name; await self.state_set(u["telegram_id"],"b:event_at",p)
                return await m.answer(f"Дата и время мероприятия по часовому поясу <b>{TZ_LABELS.get(tz_name,tz_name)}</b>:\n<code>15.10.2026 19:00</code>\n\nИли /skip.")
            if state=="b:event_at":
                if text=="/skip":
                    p["event_at"]=None; p["event_format"]=None; p["event_location"]=None; await self.state_set(u["telegram_id"],"b:regmode",p)
                    return await m.answer("Регистрация:",reply_markup=_kb([[('✅ Внутри бота','b:reg:internal')],[('🔗 Внешняя ссылка','b:reg:external')],[('Без регистрации','b:reg:none')]]))
                d=_parse_local(text,p.get("event_timezone",tz_name))
                if not d: return await m.answer("Формат: <code>15.10.2026 19:00</code>")
                p["event_at"]=d.isoformat(); await self.state_set(u["telegram_id"],"b:format",p)
                return await m.answer("Формат мероприятия:",reply_markup=_kb([[('🏛 Очно','b:format:offline'),('💻 Онлайн','b:format:online')],[('🔀 Гибрид','b:format:hybrid')]]))
            if state=="b:location":
                p["event_location"]=None if text=="/skip" else text[:500]; await self.state_set(u["telegram_id"],"b:regmode",p)
                return await m.answer("Регистрация:",reply_markup=_kb([[('✅ Внутри бота','b:reg:internal')],[('🔗 Внешняя ссылка','b:reg:external')],[('Без регистрации','b:reg:none')]]))
            if state=="b:capacity":
                if text=="/skip": p["capacity"]=None
                else:
                    try:
                        p["capacity"]=int(text)
                        if p["capacity"]<=0: raise ValueError
                    except Exception: return await m.answer("Введите положительное число или /skip.")
                await self.state_set(u["telegram_id"],"b:deadline",p)
                return await m.answer(f"Дедлайн регистрации по часовому поясу <b>{TZ_LABELS.get(p.get('event_timezone',tz_name),p.get('event_timezone',tz_name))}</b>: <code>14.10.2026 20:00</code> или /skip.")
            if state=="b:regurl":
                if not text.startswith(("http://","https://")): return await m.answer("Нужна ссылка https://...")
                p["registration_url"]=text[:1000]; await self.state_set(u["telegram_id"],"b:deadline",p)
                return await m.answer(f"Дедлайн регистрации по часовому поясу <b>{TZ_LABELS.get(p.get('event_timezone',tz_name),p.get('event_timezone',tz_name))}</b>: <code>14.10.2026 20:00</code> или /skip.")
            if state=="b:deadline":
                if text=="/skip": p["registration_deadline"]=None
                else:
                    d=_parse_local(text,p.get("event_timezone",tz_name))
                    if not d: return await m.answer("Формат: <code>14.10.2026 20:00</code>")
                    p["registration_deadline"]=d.isoformat()
                p["countries"]=["ALL"]; await self.state_set(u["telegram_id"],"b:countries",p)
                return await m.answer("Выберите страны:",reply_markup=self._countries_multi(p))
            if state=="b:customq_text":
                questions=[x.strip()[:180] for x in text.splitlines() if x.strip()][:5]
                if not questions: return await m.answer("Отправьте 1–5 вопросов, каждый с новой строки, или /skip.")
                p["custom_questions"]=questions; await self.state_set(u["telegram_id"],"b:capacity",p)
                return await m.answer("Количество мест? Отправьте число или /skip.")
            if state.startswith("regcustom:"):
                bid=int(p["broadcast_id"]); b=await self.fetchrow("SELECT custom_questions FROM broadcasts WHERE id=$1",bid)
                qs=b["custom_questions"] if isinstance(b["custom_questions"],list) else json.loads(b["custom_questions"] or "[]")
                idx=int(state.split(":")[1]); p.setdefault("answers",{})[str(idx)]=text[:1000]; idx+=1
                if idx<len(qs):
                    await self.state_set(u["telegram_id"],f"regcustom:{idx}",p); return await m.answer(f"{idx+1}/{len(qs)}. {_safe(qs[idx])}")
                await self.execute("""INSERT INTO registration_drafts(broadcast_id,telegram_id,answers,updated_at) VALUES($1,$2,$3::jsonb,NOW())
                    ON CONFLICT(broadcast_id,telegram_id) DO UPDATE SET answers=EXCLUDED.answers,updated_at=NOW()""",bid,u["telegram_id"],json.dumps(p["answers"],ensure_ascii=False))
                await self.state_clear(u["telegram_id"]); u=await self.fetchrow("SELECT * FROM users WHERE telegram_id=$1",u["telegram_id"])
                return await self.register(m.chat.id,u,bid)
            if state.startswith("schedule:publish:"):
                bid=int(state.split(":")[2]); d=_parse_local(text,tz_name)
                if not d or d<=datetime.now(timezone.utc): return await m.answer("Укажите будущие дату и время, например <code>01.10.2026 18:00</code>.")
                await self.execute("UPDATE broadcasts SET status='scheduled',publish_at=$2,updated_at=NOW() WHERE id=$1",bid,d); await self.state_clear(u["telegram_id"])
                return await m.answer(f"Публикация запланирована ✅\n{_localize(d,tz_name)}")
            if state.startswith("returnnote:"):
                bid=int(state.split(":")[1]); b=await self.fetchrow("""UPDATE broadcasts SET status='returned',review_note=$2,reviewed_by=$3,reviewed_at=NOW(),updated_at=NOW()
                    WHERE id=$1 AND status='pending' RETURNING *""",bid,text[:1000],u["telegram_id"]); await self.state_clear(u["telegram_id"])
                if b:
                    try: await self.bot.send_message(b["created_by"],f"Публикация #{bid} возвращена на доработку.\n\nКомментарий: {_safe(text[:1000])}",reply_markup=_kb([[('✏️ Исправить',f"edit:broadcast:{bid}")]]))
                    except Exception: pass
                return await m.answer("Возвращено редактору ✅")
            if state.startswith("edit:title:"):
                bid=int(state.split(":")[2]); await self.execute("UPDATE broadcasts SET title=$2,updated_at=NOW() WHERE id=$1",bid,text[:180]); await self.state_clear(u["telegram_id"])
                b=await self.fetchrow("SELECT status FROM broadcasts WHERE id=$1",bid)
                if b and b["status"]=="published": await self._resend_update(bid)
                return await m.answer("Название обновлено ✅",reply_markup=_kb([[('⬅️ К публикации',f"edit:broadcast:{bid}")]]))
            if state.startswith("edit:desc:"):
                bid=int(state.split(":")[2]); await self.execute("UPDATE broadcasts SET description=$2,updated_at=NOW() WHERE id=$1",bid,text[:3500]); await self.state_clear(u["telegram_id"])
                b=await self.fetchrow("SELECT status FROM broadcasts WHERE id=$1",bid)
                if b and b["status"]=="published": await self._resend_update(bid)
                return await m.answer("Описание обновлено ✅",reply_markup=_kb([[('⬅️ К публикации',f"edit:broadcast:{bid}")]]))
            raise SkipHandler

        @r.callback_query(F.data.startswith("b:format:"))
        async def b_format(c: CallbackQuery):
            await c.answer(); st=await self.state_get(c.from_user.id)
            if not st: return
            p=dict(st["payload"] or {}); p["event_format"]=c.data.split(":")[2]; await self.state_set(c.from_user.id,"b:location",p)
            hint="ссылку на трансляцию" if p["event_format"]=="online" else "адрес / площадку / ссылку"; await c.message.answer(f"Укажите {hint} или /skip.")

        @r.callback_query(F.data.startswith("b:regform:"))
        async def regform(c: CallbackQuery):
            await c.answer(); st=await self.state_get(c.from_user.id)
            if not st:return
            p=dict(st["payload"] or {}); p["registration_form"]=c.data.split(":",2)[2]; await self.state_set(c.from_user.id,"b:customq_choice",p)
            await c.message.answer("Добавить вопросы именно для этого мероприятия?",reply_markup=_kb([[('➕ Да, добавить','b:customq:add')],[('Без дополнительных вопросов','b:customq:none')]]))

        @r.callback_query(F.data == "b:customq:add")
        async def custom_add(c: CallbackQuery):
            await c.answer(); st=await self.state_get(c.from_user.id); p=dict(st["payload"] or {}) if st else {}; await self.state_set(c.from_user.id,"b:customq_text",p)
            await c.message.answer("Отправьте до 5 вопросов, каждый с новой строки.")

        @r.callback_query(F.data == "b:customq:none")
        async def custom_none(c: CallbackQuery):
            await c.answer(); st=await self.state_get(c.from_user.id); p=dict(st["payload"] or {}) if st else {}; p["custom_questions"]=[]; await self.state_set(c.from_user.id,"b:capacity",p)
            await c.message.answer("Количество мест? Отправьте число или /skip.")

        @r.callback_query(F.data == "b:submit")
        async def submit(c: CallbackQuery):
            await c.answer(); st=await self.state_get(c.from_user.id)
            if not st or st["state"]!="b:preview":return
            p=dict(st["payload"] or {}); aud={"countries":p.get("countries",["ALL"]),"networks":p.get("networks",["commission"]),"channels":p.get("channels",{"targets":True,"dm":False})}
            b=await self.fetchrow("""INSERT INTO broadcasts(content_type,title,description,media_file_id,event_at,event_timezone,event_format,event_location,
                registration_mode,registration_url,registration_deadline,capacity,audience,reminder_offsets,status,created_by,submitted_at,registration_form,custom_questions)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13::jsonb,$14::jsonb,'pending',$15,NOW(),$16,$17::jsonb) RETURNING *""",
                p.get("content_type","event"),p["title"],p["description"],p.get("media_file_id"),datetime.fromisoformat(p["event_at"]) if p.get("event_at") else None,
                p.get("event_timezone",DEFAULT_TZ),p.get("event_format"),p.get("event_location"),p.get("registration_mode","none"),p.get("registration_url"),
                datetime.fromisoformat(p["registration_deadline"]) if p.get("registration_deadline") else None,p.get("capacity"),json.dumps(aud,ensure_ascii=False),json.dumps(p.get("reminders",[])),
                c.from_user.id,p.get("registration_form","quick"),json.dumps(p.get("custom_questions",[]),ensure_ascii=False))
            await self.state_clear(c.from_user.id); admins=await self.fetch("SELECT telegram_id FROM users WHERE role IN ('admin','owner')")
            for a in admins:
                try: await self.bot.send_message(a["telegram_id"],f"Новая публикация на согласовании:\n<b>{_safe(b['title'])}</b>",reply_markup=_kb([[('Проверить',f"review:{b['id']}")]]))
                except Exception: pass
            await c.message.answer(f"Отправлено на согласование ✅\nПубликация #{b['id']}")

        @r.callback_query(F.data.startswith("review:approve:"))
        async def approve(c: CallbackQuery):
            await c.answer(); u=await self.ensure_user(c.from_user)
            if u["role"] not in {"admin","owner"}:return
            bid=int(c.data.split(":")[2]); b=await self.fetchrow("UPDATE broadcasts SET status='approved',reviewed_by=$2,reviewed_at=NOW(),updated_at=NOW() WHERE id=$1 AND status='pending' RETURNING *",bid,u["telegram_id"])
            if not b:return await c.message.answer("Уже обработано.")
            await c.message.answer("Публикация одобрена. Когда запускать?",reply_markup=_kb([[('🚀 Сейчас',f"review:publishnow:{bid}")],[('🕒 Запланировать',f"review:schedule:{bid}")]]))

        @r.callback_query(F.data.startswith("review:publishnow:"))
        async def publishnow(c: CallbackQuery):
            await c.answer(); bid=int(c.data.split(":")[2]); b=await self.fetchrow("SELECT * FROM broadcasts WHERE id=$1",bid)
            if b: await self.create_reminders(b)
            await c.message.answer("Рассылка запущена ✅"); asyncio.create_task(self.deliver(bid))

        @r.callback_query(F.data.startswith("review:schedule:"))
        async def schedule(c: CallbackQuery):
            await c.answer(); u=await self.ensure_user(c.from_user); bid=int(c.data.split(":")[2]); await self.state_set(u["telegram_id"],f"schedule:publish:{bid}",{})
            await c.message.answer(f"Введите дату и время публикации по часовому поясу <b>{TZ_LABELS.get(u['timezone_name'],u['timezone_name'])}</b>:\n<code>01.10.2026 18:00</code>")

        @r.callback_query(F.data.startswith("review:return:"))
        async def review_return(c: CallbackQuery):
            await c.answer(); u=await self.ensure_user(c.from_user)
            if u["role"] not in {"admin","owner"}:return
            bid=int(c.data.split(":")[2]); await self.state_set(u["telegram_id"],f"returnnote:{bid}",{}); await c.message.answer("Напишите, что нужно исправить. Комментарий получит автор публикации.")

        @r.callback_query(F.data.startswith("edit:broadcast:"))
        async def edit_broadcast(c: CallbackQuery):
            await c.answer(); u=await self.ensure_user(c.from_user); bid=int(c.data.split(":")[2]); b=await self.fetchrow("SELECT * FROM broadcasts WHERE id=$1",bid)
            if not b or (u["role"] not in {"admin","owner"} and b["created_by"]!=u["telegram_id"]):return
            buttons=[[('✏️ Название',f"edit:title:{bid}"),('📝 Описание',f"edit:desc:{bid}")]]
            if b["status"]=="returned":buttons.append([('✅ Повторно отправить',f"edit:resubmit:{bid}")])
            await c.message.answer(f"<b>#{bid} · {_safe(b['title'])}</b>\nСтатус: {b['status']}"+(f"\nКомментарий: {_safe(b['review_note'])}" if b["review_note"] else ""),reply_markup=_kb(buttons+[[('⬅️ Меню','menu')]]))

        @r.callback_query(F.data.startswith("edit:title:"))
        async def edit_title(c: CallbackQuery): await c.answer(); bid=int(c.data.split(":")[2]); await self.state_set(c.from_user.id,f"edit:title:{bid}",{}); await c.message.answer("Отправьте новое название.")
        @r.callback_query(F.data.startswith("edit:desc:"))
        async def edit_desc(c: CallbackQuery): await c.answer(); bid=int(c.data.split(":")[2]); await self.state_set(c.from_user.id,f"edit:desc:{bid}",{}); await c.message.answer("Отправьте новое описание.")
        @r.callback_query(F.data.startswith("edit:resubmit:"))
        async def edit_resubmit(c: CallbackQuery):
            await c.answer(); bid=int(c.data.split(":")[2]); b=await self.fetchrow("UPDATE broadcasts SET status='pending',review_note=NULL,submitted_at=NOW(),updated_at=NOW() WHERE id=$1 AND status='returned' RETURNING *",bid)
            if not b:return await c.message.answer("Публикация уже обработана.")
            admins=await self.fetch("SELECT telegram_id FROM users WHERE role IN ('admin','owner')")
            for a in admins:
                try: await self.bot.send_message(a["telegram_id"],f"Публикация #{bid} повторно отправлена на согласование.",reply_markup=_kb([[('Проверить',f"review:{bid}")]]))
                except Exception: pass
            await c.message.answer("Повторно отправлено на согласование ✅")

        @r.callback_query(F.data == "b:mine")
        async def mine(c: CallbackQuery):
            await c.answer(); rows=await self.fetch("SELECT * FROM broadcasts WHERE created_by=$1 ORDER BY id DESC LIMIT 20",c.from_user.id)
            if not rows:return await c.message.answer("Публикаций пока нет.")
            buttons=[]
            for b in rows:
                cb=f"edit:broadcast:{b['id']}" if b["status"] in {"returned","published"} else f"event:{b['id']}"; buttons.append([(f"#{b['id']} · {b['status']} · {b['title']}"[:60],cb)])
            await c.message.answer("Ваши публикации:",reply_markup=_kb(buttons))

        @r.callback_query(F.data.startswith("checkin:qr:"))
        async def checkin_qr(c: CallbackQuery):
            await c.answer(); u=await self.ensure_user(c.from_user)
            if u["role"] not in {"editor","admin","owner"}:return
            bid=int(c.data.split(":")[2]); b=await self.fetchrow("SELECT * FROM broadcasts WHERE id=$1",bid)
            if not b:return
            token=b["checkin_token"] or secrets.token_urlsafe(12)
            if not b["checkin_token"]:await self.execute("UPDATE broadcasts SET checkin_token=$2 WHERE id=$1",bid,token)
            me=await self.bot.get_me(); url=f"https://t.me/{me.username}?start=checkin_{bid}_{token}"; img=qrcode.make(url); buf=io.BytesIO(); img.save(buf,format="PNG")
            await self.bot.send_photo(c.message.chat.id,BufferedInputFile(buf.getvalue(),filename=f"checkin_{bid}.png"),caption=f"<b>QR check-in</b>\n{_safe(b['title'])}\n\nПокажите QR участникам на входе.")

        @r.callback_query(F.data.startswith("regadmin:event:"))
        async def regadmin_event(c: CallbackQuery):
            await c.answer(); u=await self.ensure_user(c.from_user)
            if u["role"] not in {"editor","admin","owner"}:return
            bid=int(c.data.split(":")[2]); b=await self.fetchrow("SELECT * FROM broadcasts WHERE id=$1",bid)
            if not b:return
            s=await self.fetchrow("""SELECT COUNT(*) FILTER (WHERE status IN ('registered','attended')) registered,COUNT(*) FILTER (WHERE status='attended') attended,
                COUNT(*) FILTER (WHERE status='waitlist') waitlist,COUNT(*) FILTER (WHERE status='cancelled') cancelled FROM registrations WHERE broadcast_id=$1""",bid)
            reg=s["registered"] or 0; att=s["attended"] or 0; rate=round(att*100/reg) if reg else 0
            text=f"<b>{_safe(b['title'])}</b>\n\n✅ В основном списке: {reg}"+(f" / {b['capacity']}" if b["capacity"] else "")+f"\n⏳ Лист ожидания: {s['waitlist'] or 0}\n🚪 Пришли: {att}\n📈 Посещаемость: {rate}%\n❌ Отменили: {s['cancelled'] or 0}"
            await c.message.answer(text,reply_markup=_kb([[('📷 QR check-in',f"checkin:qr:{bid}")],[('⬇️ Скачать CSV',f"regadmin:export:{bid}")],[('📲 Поделиться в WhatsApp',f"wa:share:{bid}")],[('⬅️ Все регистрации','regadmin:list')]]))

        @r.callback_query(F.data.startswith("wa:share:"))
        async def wa_share(c: CallbackQuery):
            await c.answer(); bid=int(c.data.split(":")[2]); b=await self.fetchrow("SELECT * FROM broadcasts WHERE id=$1",bid)
            if not b:return
            text=await self.broadcast_text(b); url="https://wa.me/?text="+quote(html.unescape(text.replace("<b>","").replace("</b>","")))
            await c.message.answer("Готово. Откройте WhatsApp и выберите получателя/группу.",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📲 Открыть WhatsApp",url=url)]]))

        @r.callback_query(F.data == "analytics")
        async def analytics(c: CallbackQuery):
            await c.answer(); u=await self.ensure_user(c.from_user)
            if u["role"] not in {"admin","owner"}:return
            s=await self.fetchrow("""SELECT
              (SELECT COUNT(*) FROM users WHERE onboarding_complete) users,
              (SELECT COUNT(*) FROM users WHERE role IN ('owner','admin','editor')) staff,
              (SELECT COUNT(*) FROM targets WHERE status='approved') targets,
              (SELECT COUNT(*) FROM broadcasts WHERE status='published') published,
              (SELECT COUNT(*) FROM broadcasts WHERE status='scheduled') scheduled,
              (SELECT COUNT(*) FROM registrations WHERE status IN ('registered','attended')) regs,
              (SELECT COUNT(*) FROM registrations WHERE status='attended') attended,
              (SELECT COUNT(*) FROM deliveries WHERE status='sent') sent,
              (SELECT COUNT(*) FROM deliveries WHERE status='failed') failed""")
            fail_rate=round((s['failed'] or 0)*100/max((s['sent'] or 0)+(s['failed'] or 0),1),1)
            attendance=round((s['attended'] or 0)*100/max(s['regs'] or 0,1),1)
            await c.message.answer(f"<b>Аналитика</b>\n\n👥 Пользователи: {s['users']}\n🛡 Команда: {s['staff']}\n📣 Подключённые чаты/каналы: {s['targets']}\n📰 Опубликовано: {s['published']}\n🕒 Запланировано: {s['scheduled']}\n🎟 Активные регистрации: {s['regs']}\n🚪 Посетили: {s['attended']} ({attendance}%)\n📨 Доставлено: {s['sent']}\n⚠️ Ошибки доставки: {s['failed']} ({fail_rate}%)")

        super()._register_handlers()

    async def run(self):
        await self.init_db()
        await self.bot.set_my_description("МОЛОДЁЖЬ ВКСРС — единый цифровой центр Комиссии по взаимодействию с молодёжью. Мероприятия и возможности, регистрация, персональные напоминания, списки участников и работа команды — в одном боте.")
        await self.bot.set_my_short_description("Мероприятия • регистрация • команда • аналитика")
        await self.bot.delete_webhook(drop_pending_updates=False)
        scheduler_task=asyncio.create_task(self.reminders_loop())
        try:
            await self.dp.start_polling(self.bot,allowed_updates=self.dp.resolve_used_update_types())
        finally:
            scheduler_task.cancel()
            if self.pool:await self.pool.close()
            await self.bot.session.close()

async def run_commission_bot_ultimate(database_url: str) -> None:
    token=os.getenv("COMMISSION_BOT_TOKEN","").strip()
    if not token:
        log.info("COMMISSION_BOT_TOKEN not set; commission bot disabled"); return
    bootstrap=os.getenv("COMMISSION_BOOTSTRAP_CODE","").strip(); app=CommissionBotUltimate(database_url,token,bootstrap); await app.run()
