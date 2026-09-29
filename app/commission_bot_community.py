from __future__ import annotations

import csv
import html
import io
import json
import logging
import os
import re
from datetime import datetime, timezone

from aiogram import F
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.enums import ChatType
from aiogram.types import BufferedInputFile, CallbackQuery, KeyboardButton, Message, ReplyKeyboardMarkup

from app.commission_bot import _kb
from app.commission_bot_plus_base import _role_label
from app.commission_bot_ultimate import DEFAULT_TZ, TZ_LABELS, _localize, _safe
from app.commission_bot_ux import CommissionBotUX

log = logging.getLogger(__name__)

COMMUNITY_DDL = r"""
ALTER TABLE users ADD COLUMN IF NOT EXISTS age INTEGER;
ALTER TABLE users ADD COLUMN IF NOT EXISTS city TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS participant_status TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS social_url TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS interests JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_updated_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS support_tickets (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
  topic TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','answered','closed')),
  assigned_to BIGINT REFERENCES users(telegram_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_message_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_support_tickets_status_last
  ON support_tickets(status,last_message_at DESC);
CREATE INDEX IF NOT EXISTS idx_support_tickets_user
  ON support_tickets(user_id,last_message_at DESC);

CREATE TABLE IF NOT EXISTS support_messages (
  id BIGSERIAL PRIMARY KEY,
  ticket_id BIGINT NOT NULL REFERENCES support_tickets(id) ON DELETE CASCADE,
  sender_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
  sender_role TEXT NOT NULL,
  body TEXT,
  media_file_id TEXT,
  media_type TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (body IS NOT NULL OR media_file_id IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_support_messages_ticket
  ON support_messages(ticket_id,id);
"""

STATUS_OPTIONS = [
    ("student", "🎓 Студент"),
    ("school", "📚 Школьник"),
    ("working", "💼 Работаю"),
    ("ngo", "🤝 НКО / волонтёрство"),
    ("entrepreneur", "🚀 Предприниматель"),
    ("other", "✨ Другое"),
]
STATUS_LABELS = dict(STATUS_OPTIONS)

INTEREST_OPTIONS = [
    ("volunteering", "🤝 Волонтёрство"),
    ("education", "🎓 Образование и карьера"),
    ("culture", "🎭 Культура"),
    ("media", "📱 Медиа"),
    ("international", "🌍 Международные проекты"),
    ("leadership", "🚀 Проекты и лидерство"),
]
INTEREST_LABELS = dict(INTEREST_OPTIONS)

SUPPORT_TOPICS = {
    "registration": "🎟 Регистрация",
    "events": "📅 Мероприятия",
    "technical": "🛠 Технический вопрос",
    "cooperation": "🤝 Сотрудничество",
    "other": "💬 Другое",
}

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _json_list(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            return decoded if isinstance(decoded, list) else []
        except Exception:
            return []
    return []


class CommissionBotCommunity(CommissionBotUX):
    async def init_db(self) -> None:
        await super().init_db()
        await self.execute(COMMUNITY_DDL)

    def _quick_keyboard(self, role: str) -> ReplyKeyboardMarkup:
        if role in {"admin", "owner"}:
            rows = [
                [KeyboardButton(text="➕ Создать"), KeyboardButton(text="✅ Согласование")],
                [KeyboardButton(text="📋 Участники"), KeyboardButton(text="⚙️ Управление")],
                [KeyboardButton(text="📅 События"), KeyboardButton(text="🎟 Мои заявки")],
                [KeyboardButton(text="💬 Обращения"), KeyboardButton(text="👤 Профиль")],
                [KeyboardButton(text="❓ Помощь")],
            ]
        elif role == "editor":
            rows = [
                [KeyboardButton(text="➕ Создать"), KeyboardButton(text="📋 Участники")],
                [KeyboardButton(text="📅 События"), KeyboardButton(text="🎟 Мои заявки")],
                [KeyboardButton(text="💬 Обращения"), KeyboardButton(text="👤 Профиль")],
                [KeyboardButton(text="❓ Помощь")],
            ]
        else:
            rows = [
                [KeyboardButton(text="📅 События"), KeyboardButton(text="🎟 Мои заявки")],
                [KeyboardButton(text="💬 Связаться"), KeyboardButton(text="👤 Профиль")],
                [KeyboardButton(text="🔔 Уведомления"), KeyboardButton(text="❓ Помощь")],
            ]
        return ReplyKeyboardMarkup(
            keyboard=rows,
            resize_keyboard=True,
            is_persistent=True,
            input_field_placeholder="Выберите действие",
        )

    async def send_menu(self, chat_id: int, user, text: str = "Главное меню"):
        role = user["role"]
        if role in {"editor", "admin", "owner"}:
            intro = (
                f"<b>{html.escape(text)}</b>\n\n"
                "Здесь всё, что нужно команде: публикации, участники, обращения и аналитика. "
                "Главные действия — в один тап."
            )
        else:
            intro = (
                f"<b>{html.escape(text)}</b>\n\n"
                "Возможности должны находить тебя вовремя ✨\n"
                "Смотри события, регистрируйся без длинных анкет и получай только нужные напоминания."
            )
        lines = [intro]
        try:
            upcoming = await self.fetchrow(
                "SELECT COUNT(*) AS n FROM broadcasts WHERE status='published' AND event_at IS NOT NULL AND event_at>NOW()"
            )
            if upcoming and upcoming["n"]:
                lines.append(f"\n📅 Ближайших событий: <b>{upcoming['n']}</b>")
            if role in {"admin", "owner"}:
                pending = await self.fetchrow("SELECT COUNT(*) AS n FROM broadcasts WHERE status='pending'")
                open_support = await self.fetchrow("SELECT COUNT(*) AS n FROM support_tickets WHERE status='open'")
                if pending and pending["n"]:
                    lines.append(f"✅ На согласовании: <b>{pending['n']}</b>")
                if open_support and open_support["n"]:
                    lines.append(f"💬 Новых обращений: <b>{open_support['n']}</b>")
        except Exception:
            log.exception("Could not build Community menu counters")
        await self.bot.send_message(chat_id, "\n".join(lines), reply_markup=self._quick_keyboard(role))

    async def _show_management(self, chat_id: int, user) -> None:
        if user["role"] not in {"admin", "owner"}:
            return await self.bot.send_message(chat_id, "Этот раздел доступен администратору и владельцу.")
        rows = [
            [("📣 Чаты и каналы", "ux:targets"), ("📊 Аналитика", "ux:analytics")],
            [("💬 Обращения", "support:staff:list")],
        ]
        if user["role"] == "owner":
            rows.append([("👥 Команда", "ux:team")])
        rows.extend([
            [("🔔 Уведомления", "ux:notifications"), ("👤 Профиль", "ux:profile")],
            [("❓ Как пользоваться", "ux:help")],
            [("⬅️ Главное меню", "menu")],
        ])
        await self.bot.send_message(
            chat_id,
            "<b>⚙️ Управление</b>\n\nНастройки, каналы, аналитика и обращения участников — без перегруженного главного экрана.",
            reply_markup=_kb(rows),
        )

    async def start_onboarding(self, chat_id: int, user, pending: dict | None = None):
        await self.state_set(user["telegram_id"], "onboard:region", {"pending": pending})
        await self.bot.send_message(
            chat_id,
            "<b>Добро пожаловать 👋</b>\n\n"
            "Пара быстрых шагов — и бот сможет показывать тебе релевантные события и возможности.\n\n"
            "🌍 Сначала выбери регион:",
            reply_markup=self._region_kb("onbregion"),
        )

    def _profile_status_kb(self):
        rows = []
        for i in range(0, len(STATUS_OPTIONS), 2):
            rows.append([(label, f"regp10:status:{key}") for key, label in STATUS_OPTIONS[i:i + 2]])
        return _kb(rows)

    def _interests_kb(self, selected: list[str]):
        chosen = set(selected)
        rows = []
        for i in range(0, len(INTEREST_OPTIONS), 2):
            row = []
            for key, label in INTEREST_OPTIONS[i:i + 2]:
                row.append((("✅ " if key in chosen else "▫️ ") + label, f"regp10:interest:{key}"))
            rows.append(row)
        rows.append([("Готово ✨", "regp10:interest:done")])
        return _kb(rows)

    async def _start_profile10(self, chat_id: int, user, broadcast_id: int | None = None):
        payload = {"broadcast_id": broadcast_id}
        await self.state_set(user["telegram_id"], "regprofile10:name", payload)
        default_name = " ".join(x for x in [user["first_name"], user["last_name"]] if x).strip()
        text = (
            "<b>Соберём твой профиль ✨</b>\n\n"
            "Это нужно заполнить только один раз. Потом регистрация на большинство мероприятий займёт буквально пару секунд.\n\n"
            "<b>1/9 · Как тебя записать?</b>\nОтправь имя и фамилию для списков участников."
        )
        if default_name:
            text += f"\n\nМожно отправить <code>/auto</code> и взять имя из Telegram: <b>{_safe(default_name)}</b>"
        await self.bot.send_message(chat_id, text)

    async def register(self, chat_id: int, user, bid: int):
        b = await self.fetchrow("SELECT * FROM broadcasts WHERE id=$1", bid)
        if not b or b["status"] not in {"approved", "published"}:
            return await self.bot.send_message(chat_id, "Эта регистрация сейчас недоступна.")
        if not user["onboarding_complete"]:
            return await self.start_onboarding(chat_id, user, {"type": "register", "broadcast_id": bid})
        if b["registration_deadline"] and b["registration_deadline"] < datetime.now(timezone.utc):
            return await self.bot.send_message(chat_id, "Регистрация уже закрыта. Следи за новыми возможностями — они появляются здесь регулярно ✨")

        existing = await self.fetchrow(
            "SELECT * FROM registrations WHERE broadcast_id=$1 AND telegram_id=$2", bid, user["telegram_id"]
        )
        if existing and existing["status"] in {"registered", "waitlist", "attended"}:
            label = "в основном списке ✅" if existing["status"] != "waitlist" else "в листе ожидания ⏳"
            return await self.bot.send_message(
                chat_id,
                f"Ты уже {label}\n\n<b>{_safe(b['title'])}</b>",
                reply_markup=_kb([[("❌ Отменить регистрацию", f"regcancel:{bid}")], [("⬅️ В меню", "menu")]]),
            )

        if not user["registration_consent_at"]:
            await self.state_set(user["telegram_id"], "privacy:register", {"broadcast_id": bid})
            return await self.bot.send_message(
                chat_id,
                "<b>Один важный момент 🔐</b>\n\n"
                "Чтобы оформить участие, бот сохранит данные твоего профиля и ответы на вопросы мероприятия. "
                "Они нужны только для организации участия и связи по событию.\n\n"
                "Удалить сохранённые данные можно в профиле в любой момент.",
                reply_markup=_kb([[("✅ Всё понятно, продолжить", f"privacy:accept:{bid}")], [("Не сейчас", "menu")]]),
            )

        questions = b["custom_questions"] if isinstance(b["custom_questions"], list) else json.loads(b["custom_questions"] or "[]")
        if questions:
            draft = await self.fetchrow(
                "SELECT answers FROM registration_drafts WHERE broadcast_id=$1 AND telegram_id=$2", bid, user["telegram_id"]
            )
            if not draft:
                await self.state_set(user["telegram_id"], "regcustom:0", {"broadcast_id": bid, "answers": {}})
                return await self.bot.send_message(
                    chat_id,
                    f"<b>Почти готово — пара вопросов от организаторов</b>\n\n1/{len(questions)} · {_safe(questions[0])}",
                )

        if b["registration_form"] == "standard" and not user["participant_profile_complete"]:
            return await self._start_profile10(chat_id, user, bid)

        draft = await self.fetchrow(
            "SELECT answers FROM registration_drafts WHERE broadcast_id=$1 AND telegram_id=$2", bid, user["telegram_id"]
        )
        custom_answers = dict(draft["answers"] or {}) if draft else {}
        interests = _json_list(user["interests"])
        answers = {
            "name": user["registration_name"] or " ".join(x for x in [user["first_name"], user["last_name"]] if x).strip(),
            "age": user["age"],
            "country": user["country_code"],
            "city": user["city"],
            "participant_status": user["participant_status"],
            "organization": user["organization"],
            "phone": user["phone"],
            "email": user["email"],
            "social_url": user["social_url"],
            "interests": interests,
        }
        if custom_answers:
            answers["custom"] = custom_answers

        assert self.pool
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                br = await conn.fetchrow("SELECT * FROM broadcasts WHERE id=$1 FOR UPDATE", bid)
                status = "registered"
                if br["capacity"]:
                    count = await conn.fetchval(
                        "SELECT COUNT(*) FROM registrations WHERE broadcast_id=$1 AND status IN ('registered','attended')", bid
                    )
                    if count >= br["capacity"]:
                        status = "waitlist"
                await conn.execute(
                    """INSERT INTO registrations(broadcast_id,telegram_id,status,source,answers,updated_at)
                    VALUES($1,$2,$3,'telegram',$4::jsonb,NOW())
                    ON CONFLICT(broadcast_id,telegram_id) DO UPDATE SET
                      status=EXCLUDED.status,answers=EXCLUDED.answers,registered_at=NOW(),updated_at=NOW()""",
                    bid, user["telegram_id"], status, json.dumps(answers, ensure_ascii=False),
                )
                if draft:
                    await conn.execute(
                        "DELETE FROM registration_drafts WHERE broadcast_id=$1 AND telegram_id=$2", bid, user["telegram_id"]
                    )

        await self.audit(user["telegram_id"], "registration_created", "broadcast", bid, {"status": status, "form": b["registration_form"]})
        date_line = f"\n📅 {_localize(b['event_at'], b['event_timezone'] or DEFAULT_TZ)}" if b["event_at"] else ""
        if status == "registered":
            text = (
                "<b>Ты в списке ✅</b>\n\n"
                f"<b>{_safe(b['title'])}</b>{date_line}\n\n"
                "Готово — место за тобой. Перед событием бот напомнит всё важное, чтобы ничего не потерялось."
            )
        else:
            pos = await self.fetchrow(
                """SELECT COUNT(*) AS n FROM registrations WHERE broadcast_id=$1 AND status='waitlist' AND registered_at <=
                (SELECT registered_at FROM registrations WHERE broadcast_id=$1 AND telegram_id=$2)""", bid, user["telegram_id"]
            )
            text = (
                "<b>Ты в листе ожидания ⏳</b>\n\n"
                f"<b>{_safe(b['title'])}</b>{date_line}\n"
                f"Позиция: <b>{pos['n'] if pos else '—'}</b>\n\n"
                "Если место освободится, бот сам переведёт тебя в основной список и сразу напишет."
            )
        await self.bot.send_message(
            chat_id,
            text,
            reply_markup=_kb([[("❌ Отменить регистрацию", f"regcancel:{bid}")], [("📅 Другие события", "events:list"), ("🏠 Меню", "menu")]]),
        )

    async def _finish_profile10(self, chat_id: int, user_id: int, payload: dict):
        await self.execute(
            "UPDATE users SET participant_profile_complete=TRUE,profile_updated_at=NOW(),updated_at=NOW() WHERE telegram_id=$1",
            user_id,
        )
        await self.state_clear(user_id)
        user = await self.fetchrow("SELECT * FROM users WHERE telegram_id=$1", user_id)
        await self.bot.send_message(
            chat_id,
            "<b>Профиль готов ✨</b>\n\n"
            "Теперь не придётся заполнять одно и то же снова и снова. Для большинства событий останется только нажать «Зарегистрироваться» и, если нужно, ответить на вопросы организаторов.",
        )
        bid = payload.get("broadcast_id")
        if bid:
            await self.register(chat_id, user, int(bid))
        else:
            await self.send_menu(chat_id, user, "Профиль обновлён")

    async def _show_profile10(self, chat_id: int, user) -> None:
        interests = _json_list(user["interests"])
        interest_text = ", ".join(INTEREST_LABELS.get(x, x) for x in interests) or "не выбраны"
        name = user["registration_name"] or " ".join(x for x in [user["first_name"], user["last_name"]] if x).strip() or "не указано"
        text = (
            "<b>Твой профиль</b>\n\n"
            f"👤 {_safe(name)}\n"
            f"🎂 Возраст: {_safe(user['age'] or '—')}\n"
            f"🌍 {_safe(user['country_name'] or 'страна не выбрана')}"
            + (f" · {_safe(user['city'])}" if user["city"] else "") + "\n"
            f"✨ Статус: {_safe(STATUS_LABELS.get(user['participant_status'], user['participant_status'] or '—'))}\n"
            f"🏢 Организация: {_safe(user['organization'] or '—')}\n"
            f"📱 Телефон: {_safe(user['phone'] or '—')}\n"
            f"✉️ Email: {_safe(user['email'] or '—')}\n"
            f"🔗 Соцсети: {_safe(user['social_url'] or '—')}\n"
            f"💡 Интересы: {_safe(interest_text)}\n\n"
            f"🔔 Общие рассылки: {'включены ✅' if user['telegram_opt_in'] else 'выключены'}"
        )
        await self.bot.send_message(
            chat_id,
            text,
            reply_markup=_kb([
                [("✏️ Обновить анкету", "profile10:edit")],
                [("🌍 Изменить страну", "profile:country"), ("🕒 Часовой пояс", "profile:tz")],
                [("🗑 Удалить мои данные", "privacy:delete")],
                [("⬅️ Меню", "menu")],
            ]),
        )

    async def _show_contact(self, chat_id: int) -> None:
        await self.bot.send_message(
            chat_id,
            "<b>Связаться с командой 💬</b>\n\n"
            "Если что-то непонятно, не работает или есть идея — пиши. Обращение увидят администраторы и модераторы, а ответ придёт прямо сюда.",
            reply_markup=_kb([
                [("✍️ Задать вопрос", "support:new")],
                [("🗂 Мои обращения", "support:mine")],
                [("⬅️ Меню", "menu")],
            ]),
        )

    async def _support_notify_staff(self, ticket_id: int, prefix: str = "Новое обращение") -> None:
        ticket = await self.fetchrow(
            """SELECT t.*,u.first_name,u.last_name,u.username,u.country_name
            FROM support_tickets t JOIN users u ON u.telegram_id=t.user_id WHERE t.id=$1""", ticket_id
        )
        if not ticket:
            return
        name = " ".join(x for x in [ticket["first_name"], ticket["last_name"]] if x).strip() or ticket["username"] or str(ticket["user_id"])
        staff = await self.fetch("SELECT telegram_id FROM users WHERE role IN ('owner','admin','editor')")
        for member in staff:
            try:
                await self.bot.send_message(
                    member["telegram_id"],
                    f"<b>{_safe(prefix)} · #{ticket_id}</b>\n\n"
                    f"👤 {_safe(name)}\n🌍 {_safe(ticket['country_name'] or '—')}\n"
                    f"Тема: {_safe(SUPPORT_TOPICS.get(ticket['topic'], ticket['topic']))}",
                    reply_markup=_kb([[("Открыть обращение", f"support:staff:{ticket_id}")]]),
                )
            except Exception:
                pass

    async def _show_support_inbox(self, chat_id: int, user) -> None:
        if user["role"] not in {"owner", "admin", "editor"}:
            return await self.bot.send_message(chat_id, "Этот раздел доступен команде.")
        rows = await self.fetch(
            """SELECT t.id,t.topic,t.status,t.last_message_at,u.first_name,u.last_name,u.username
            FROM support_tickets t JOIN users u ON u.telegram_id=t.user_id
            WHERE t.status<>'closed' ORDER BY CASE t.status WHEN 'open' THEN 0 ELSE 1 END,t.last_message_at DESC LIMIT 30"""
        )
        if not rows:
            return await self.bot.send_message(chat_id, "<b>Обращения</b>\n\nСейчас всё спокойно — новых вопросов нет ✨", reply_markup=_kb([[("⬅️ Меню", "menu")]]))
        buttons = []
        for x in rows:
            name = " ".join(v for v in [x["first_name"], x["last_name"]] if v).strip() or x["username"] or "участник"
            icon = "🔴" if x["status"] == "open" else "🟢"
            buttons.append([(f"{icon} #{x['id']} · {name} · {SUPPORT_TOPICS.get(x['topic'], x['topic'])}"[:64], f"support:staff:{x['id']}")])
        buttons.append([("⬅️ Меню", "menu")])
        await self.bot.send_message(chat_id, "<b>💬 Обращения участников</b>\n\n🔴 ждёт ответа · 🟢 команда уже ответила", reply_markup=_kb(buttons))

    async def _ticket_text(self, ticket_id: int, staff_view: bool) -> tuple[str, object | None]:
        ticket = await self.fetchrow(
            """SELECT t.*,u.first_name,u.last_name,u.username,u.country_name
            FROM support_tickets t JOIN users u ON u.telegram_id=t.user_id WHERE t.id=$1""", ticket_id
        )
        if not ticket:
            return "Обращение не найдено.", None
        messages = await self.fetch(
            "SELECT * FROM support_messages WHERE ticket_id=$1 ORDER BY id DESC LIMIT 12", ticket_id
        )
        messages = list(reversed(messages))
        name = " ".join(x for x in [ticket["first_name"], ticket["last_name"]] if x).strip() or ticket["username"] or str(ticket["user_id"])
        header = f"<b>Обращение #{ticket_id}</b>\nТема: {_safe(SUPPORT_TOPICS.get(ticket['topic'], ticket['topic']))}\n"
        if staff_view:
            header += f"👤 {_safe(name)} · {_safe(ticket['country_name'] or '—')}\n"
        header += f"Статус: <b>{'закрыто' if ticket['status']=='closed' else 'ждёт ответа' if ticket['status']=='open' else 'ответ отправлен'}</b>\n\n"
        body = []
        for msg in messages:
            who = "Ты" if (staff_view and msg["sender_role"] != "viewer") else ("Команда" if msg["sender_role"] != "viewer" else ("Участник" if staff_view else "Ты"))
            text = _safe(msg["body"] or "📎 Вложение")
            body.append(f"<b>{who}:</b> {text}")
        return header + "\n\n".join(body), ticket

    async def _send_support_message(self, ticket_id: int, sender, message: Message, sender_role: str) -> bool:
        body = (message.text or message.caption or "").strip()[:3500] or None
        media_file_id = message.photo[-1].file_id if message.photo else None
        media_type = "photo" if media_file_id else None
        if not body and not media_file_id:
            await message.answer("Отправь текст или фото/скриншот с пояснением.")
            return False
        await self.execute(
            "INSERT INTO support_messages(ticket_id,sender_id,sender_role,body,media_file_id,media_type) VALUES($1,$2,$3,$4,$5,$6)",
            ticket_id, sender["telegram_id"], sender_role, body, media_file_id, media_type,
        )
        return True

    async def _dispatch_ux_button(self, m: Message, user, text: str) -> None:
        if text == "💬 Связаться":
            return await self._show_contact(m.chat.id)
        if text == "💬 Обращения":
            return await self._show_support_inbox(m.chat.id, user)
        await super()._dispatch_ux_button(m, user, text)

    def _register_handlers(self):
        r = self.router

        @r.message(F.chat.type == ChatType.PRIVATE, F.text.in_({"💬 Связаться", "💬 Обращения"}))
        async def community_quick(m: Message):
            user = await self.ensure_user(m.from_user)
            await self._dispatch_ux_button(m, user, (m.text or "").strip())

        @r.callback_query(F.data == "profile:view")
        async def profile_view10(c: CallbackQuery):
            await c.answer()
            user = await self.ensure_user(c.from_user)
            await self._show_profile10(c.message.chat.id, user)

        @r.callback_query(F.data == "ux:profile")
        async def ux_profile_view10(c: CallbackQuery):
            await c.answer()
            user = await self.ensure_user(c.from_user)
            await self._show_profile10(c.message.chat.id, user)

        @r.callback_query(F.data == "profile10:edit")
        async def profile_edit10(c: CallbackQuery):
            await c.answer()
            user = await self.ensure_user(c.from_user)
            await self._start_profile10(c.message.chat.id, user, None)

        @r.callback_query(F.data.startswith("regp10:status:"))
        async def profile_status10(c: CallbackQuery):
            await c.answer()
            key = c.data.split(":", 2)[2]
            if key not in STATUS_LABELS:
                return
            st = await self.state_get(c.from_user.id)
            if not st or st["state"] != "regprofile10:status":
                return
            payload = dict(st["payload"] or {})
            await self.execute("UPDATE users SET participant_status=$2,updated_at=NOW() WHERE telegram_id=$1", c.from_user.id, key)
            await self.state_set(c.from_user.id, "regprofile10:phone", payload)
            await c.message.answer(
                "<b>6/9 · Телефон</b>\nНомер пригодится организаторам, если нужно быстро связаться перед событием.\n\nОтправь номер с кодом страны или <code>/skip</code>."
            )

        @r.callback_query(F.data.startswith("regp10:interest:"))
        async def profile_interest10(c: CallbackQuery):
            await c.answer()
            key = c.data.split(":", 2)[2]
            st = await self.state_get(c.from_user.id)
            if not st or st["state"] != "regprofile10:interests":
                return
            payload = dict(st["payload"] or {})
            selected = list(payload.get("interests", []))
            if key == "done":
                await self.execute(
                    "UPDATE users SET interests=$2::jsonb,updated_at=NOW() WHERE telegram_id=$1",
                    c.from_user.id, json.dumps(selected, ensure_ascii=False),
                )
                return await self._finish_profile10(c.message.chat.id, c.from_user.id, payload)
            if key not in INTEREST_LABELS:
                return
            if key in selected:
                selected.remove(key)
            else:
                selected.append(key)
            payload["interests"] = selected
            await self.state_set(c.from_user.id, "regprofile10:interests", payload)
            try:
                await c.message.edit_reply_markup(reply_markup=self._interests_kb(selected))
            except Exception:
                pass

        @r.callback_query(F.data == "privacy:delete:confirm")
        async def privacy_delete10(c: CallbackQuery):
            await c.answer()
            assert self.pool
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute("DELETE FROM registrations WHERE telegram_id=$1", c.from_user.id)
                    await conn.execute("DELETE FROM registration_drafts WHERE telegram_id=$1", c.from_user.id)
                    await conn.execute(
                        """UPDATE users SET registration_name=NULL,organization=NULL,phone=NULL,email=NULL,age=NULL,city=NULL,
                        participant_status=NULL,social_url=NULL,interests='[]'::jsonb,profile_updated_at=NULL,
                        participant_profile_complete=FALSE,registration_consent_at=NULL,privacy_policy_version=NULL,
                        telegram_opt_in=FALSE,updated_at=NOW() WHERE telegram_id=$1""", c.from_user.id
                    )
            await c.message.answer("Сохранённые данные анкеты и регистрации удалены ✅")

        @r.callback_query(F.data == "support:new")
        async def support_new(c: CallbackQuery):
            await c.answer()
            rows = [[(label, f"support:topic:{key}")] for key, label in SUPPORT_TOPICS.items()]
            rows.append([("⬅️ Назад", "menu")])
            await c.message.answer("<b>О чём вопрос?</b>\n\nВыбери тему — так команда быстрее сориентируется.", reply_markup=_kb(rows))

        @r.callback_query(F.data.startswith("support:topic:"))
        async def support_topic(c: CallbackQuery):
            await c.answer()
            topic = c.data.split(":", 2)[2]
            if topic not in SUPPORT_TOPICS:
                return
            await self.state_set(c.from_user.id, f"support:new:{topic}", {})
            await c.message.answer(
                f"<b>{SUPPORT_TOPICS[topic]}</b>\n\nНапиши вопрос одним сообщением. Можно приложить фото или скриншот.\n\nЧем понятнее контекст, тем быстрее команда сможет помочь ✨"
            )

        @r.callback_query(F.data == "support:mine")
        async def support_mine(c: CallbackQuery):
            await c.answer()
            rows = await self.fetch("SELECT id,topic,status FROM support_tickets WHERE user_id=$1 ORDER BY last_message_at DESC LIMIT 20", c.from_user.id)
            if not rows:
                return await c.message.answer("У тебя пока нет обращений.", reply_markup=_kb([[('✍️ Задать вопрос','support:new')],[('⬅️ Меню','menu')]]))
            buttons = [[(f"#{x['id']} · {SUPPORT_TOPICS.get(x['topic'],x['topic'])} · {'закрыто' if x['status']=='closed' else 'ответ получен' if x['status']=='answered' else 'в работе'}"[:64], f"support:user:{x['id']}")] for x in rows]
            buttons.append([("⬅️ Меню", "menu")])
            await c.message.answer("<b>Мои обращения</b>", reply_markup=_kb(buttons))

        @r.callback_query(F.data.startswith("support:user:"))
        async def support_user_ticket(c: CallbackQuery):
            await c.answer()
            ticket_id = int(c.data.split(":")[2])
            text, ticket = await self._ticket_text(ticket_id, False)
            if not ticket or ticket["user_id"] != c.from_user.id:
                return
            buttons = []
            if ticket["status"] != "closed":
                buttons.append([("↩️ Ответить", f"support:userreply:{ticket_id}")])
            buttons.append([("⬅️ Мои обращения", "support:mine")])
            await c.message.answer(text, reply_markup=_kb(buttons))

        @r.callback_query(F.data.startswith("support:userreply:"))
        async def support_user_reply(c: CallbackQuery):
            await c.answer()
            ticket_id = int(c.data.split(":")[2])
            ticket = await self.fetchrow("SELECT * FROM support_tickets WHERE id=$1 AND user_id=$2 AND status<>'closed'", ticket_id, c.from_user.id)
            if not ticket:
                return await c.message.answer("Обращение уже закрыто.")
            await self.state_set(c.from_user.id, f"support:userreply:{ticket_id}", {})
            await c.message.answer("Напиши ответ. Можно приложить скриншот.")

        @r.callback_query(F.data == "support:staff:list")
        async def support_staff_list(c: CallbackQuery):
            await c.answer()
            user = await self.ensure_user(c.from_user)
            await self._show_support_inbox(c.message.chat.id, user)

        @r.callback_query(F.data.startswith("support:staff:"))
        async def support_staff_ticket(c: CallbackQuery):
            await c.answer()
            user = await self.ensure_user(c.from_user)
            if user["role"] not in {"owner", "admin", "editor"}:
                return
            ticket_id = int(c.data.split(":")[2])
            text, ticket = await self._ticket_text(ticket_id, True)
            if not ticket:
                return await c.message.answer(text)
            buttons = []
            if ticket["status"] != "closed":
                buttons.extend([
                    [("✍️ Ответить", f"support:reply:{ticket_id}")],
                    [("✅ Закрыть", f"support:close:{ticket_id}")],
                ])
            buttons.append([("⬅️ Все обращения", "support:staff:list")])
            await c.message.answer(text, reply_markup=_kb(buttons))

        @r.callback_query(F.data.startswith("support:reply:"))
        async def support_staff_reply(c: CallbackQuery):
            await c.answer()
            user = await self.ensure_user(c.from_user)
            if user["role"] not in {"owner", "admin", "editor"}:
                return
            ticket_id = int(c.data.split(":")[2])
            ticket = await self.fetchrow("SELECT * FROM support_tickets WHERE id=$1 AND status<>'closed'", ticket_id)
            if not ticket:
                return await c.message.answer("Обращение уже закрыто.")
            await self.state_set(user["telegram_id"], f"support:reply:{ticket_id}", {})
            await c.message.answer("Напиши ответ участнику. Он получит его прямо в этом боте.")

        @r.callback_query(F.data.startswith("support:close:"))
        async def support_close(c: CallbackQuery):
            await c.answer()
            user = await self.ensure_user(c.from_user)
            if user["role"] not in {"owner", "admin", "editor"}:
                return
            ticket_id = int(c.data.split(":")[2])
            ticket = await self.fetchrow(
                "UPDATE support_tickets SET status='closed',assigned_to=COALESCE(assigned_to,$2),updated_at=NOW() WHERE id=$1 RETURNING *",
                ticket_id, user["telegram_id"],
            )
            if ticket:
                try:
                    await self.bot.send_message(ticket["user_id"], f"Обращение #{ticket_id} закрыто ✅\nЕсли появится новый вопрос — просто создай новое обращение.")
                except Exception:
                    pass
            await c.message.answer("Обращение закрыто ✅")

        @r.callback_query(F.data.startswith("regadmin:event:"))
        async def regadmin_event10(c: CallbackQuery):
            await c.answer()
            user = await self.ensure_user(c.from_user)
            if user["role"] not in {"owner", "admin", "editor"}:
                return
            bid = int(c.data.split(":")[2])
            b = await self.fetchrow("SELECT * FROM broadcasts WHERE id=$1", bid)
            if not b:
                return
            rows = await self.fetch(
                """SELECT r.status,r.registered_at,u.registration_name,u.first_name,u.last_name,u.username,u.age,u.country_name,u.city,
                u.participant_status,u.organization FROM registrations r JOIN users u ON u.telegram_id=r.telegram_id
                WHERE r.broadcast_id=$1 AND r.status<>'cancelled'
                ORDER BY CASE r.status WHEN 'attended' THEN 0 WHEN 'registered' THEN 0 WHEN 'waitlist' THEN 1 ELSE 2 END,r.registered_at""", bid
            )
            registered = sum(1 for x in rows if x["status"] in {"registered", "attended"})
            attended = sum(1 for x in rows if x["status"] == "attended")
            waitlist = sum(1 for x in rows if x["status"] == "waitlist")
            text = f"<b>{_safe(b['title'])}</b>\n\n✅ Участники: <b>{registered}</b>" + (f" / {b['capacity']}" if b["capacity"] else "") + f"\n⏳ Ожидают: <b>{waitlist}</b>\n🚪 Пришли: <b>{attended}</b>\n\n"
            for idx, x in enumerate(rows[:15], 1):
                name = x["registration_name"] or " ".join(v for v in [x["first_name"], x["last_name"]] if v).strip() or x["username"] or "участник"
                text += f"{idx}. {'⏳' if x['status']=='waitlist' else '✅'} {_safe(name)}"
                if x["age"]:
                    text += f" · {x['age']}"
                if x["city"]:
                    text += f" · {_safe(x['city'])}"
                text += "\n"
            if len(rows) > 15:
                text += f"\n…и ещё {len(rows)-15}. Полный список — в CSV."
            await c.message.answer(text, reply_markup=_kb([
                [("📷 QR check-in", f"checkin:qr:{bid}")],
                [("⬇️ Скачать полный CSV", f"regadmin:export:{bid}")],
                [("⬅️ Все регистрации", "regadmin:list")],
            ]))

        @r.callback_query(F.data.startswith("regadmin:export:"))
        async def regadmin_export10(c: CallbackQuery):
            await c.answer()
            user = await self.ensure_user(c.from_user)
            if user["role"] not in {"owner", "admin", "editor"}:
                return
            bid = int(c.data.split(":")[2])
            b = await self.fetchrow("SELECT title,custom_questions FROM broadcasts WHERE id=$1", bid)
            if not b:
                return
            rows = await self.fetch(
                """SELECT r.status,r.registered_at,r.answers,u.telegram_id,u.username,u.registration_name,u.first_name,u.last_name,u.age,
                u.country_name,u.city,u.participant_status,u.organization,u.phone,u.email,u.social_url,u.interests
                FROM registrations r JOIN users u ON u.telegram_id=r.telegram_id WHERE r.broadcast_id=$1 ORDER BY r.registered_at""", bid
            )
            questions = b["custom_questions"] if isinstance(b["custom_questions"], list) else json.loads(b["custom_questions"] or "[]")
            out = io.StringIO()
            writer = csv.writer(out)
            header = ["status","name","age","country","city","participant_status","organization","phone","email","social","interests","telegram","registered_at"]
            header.extend([f"Q{i+1}: {q}" for i, q in enumerate(questions)])
            writer.writerow(header)
            for x in rows:
                answers = dict(x["answers"] or {})
                custom = dict(answers.get("custom") or {})
                name = x["registration_name"] or " ".join(v for v in [x["first_name"], x["last_name"]] if v).strip()
                interests = ", ".join(INTEREST_LABELS.get(v, v) for v in _json_list(x["interests"]))
                row = [x["status"],name,x["age"],x["country_name"],x["city"],STATUS_LABELS.get(x["participant_status"],x["participant_status"]),x["organization"],x["phone"],x["email"],x["social_url"],interests,"@"+x["username"] if x["username"] else x["telegram_id"],x["registered_at"].isoformat() if x["registered_at"] else ""]
                row.extend([custom.get(str(i), "") for i in range(len(questions))])
                writer.writerow(row)
            data = ("\ufeff" + out.getvalue()).encode("utf-8")
            await self.bot.send_document(c.message.chat.id, BufferedInputFile(data, filename=f"participants_{bid}.csv"), caption=f"Полный список · {_safe(b['title'])}")

        @r.message(F.chat.type == ChatType.PRIVATE)
        async def community_state(m: Message):
            user = await self.ensure_user(m.from_user)
            st = await self.state_get(user["telegram_id"])
            if not st:
                raise SkipHandler
            state = str(st["state"])
            payload = dict(st["payload"] or {})
            text = (m.text or m.caption or "").strip()

            if state == "regprofile10:name":
                if text == "/auto":
                    value = " ".join(x for x in [user["first_name"], user["last_name"]] if x).strip()
                    if not value:
                        return await m.answer("Имя в Telegram не найдено — отправь имя и фамилию текстом.")
                elif len(text) < 3:
                    return await m.answer("Напиши имя и фамилию текстом или отправь <code>/auto</code>.")
                else:
                    value = text[:180]
                await self.execute("UPDATE users SET registration_name=$2,updated_at=NOW() WHERE telegram_id=$1", user["telegram_id"], value)
                await self.state_set(user["telegram_id"], "regprofile10:age", payload)
                return await m.answer("<b>2/9 · Возраст</b>\nОтправь число — например <code>22</code>. Это помогает организаторам понимать аудиторию и подбирать релевантные возможности.")

            if state == "regprofile10:age":
                try:
                    age = int(text)
                    if age < 10 or age > 100:
                        raise ValueError
                except Exception:
                    return await m.answer("Отправь возраст числом от 10 до 100.")
                await self.execute("UPDATE users SET age=$2,updated_at=NOW() WHERE telegram_id=$1", user["telegram_id"], age)
                await self.state_set(user["telegram_id"], "regprofile10:city", payload)
                return await m.answer("<b>3/9 · Город</b>\nГде ты сейчас живёшь или учишься?\n\nНапиши город или <code>/skip</code>.")

            if state == "regprofile10:city":
                value = None if text == "/skip" else text[:120]
                await self.execute("UPDATE users SET city=$2,updated_at=NOW() WHERE telegram_id=$1", user["telegram_id"], value)
                await self.state_set(user["telegram_id"], "regprofile10:org", payload)
                return await m.answer("<b>4/9 · Организация / вуз / место работы</b>\nЕсли представляешь команду, университет, школу или компанию — укажи здесь.\n\nЕсли неактуально — <code>/skip</code>.")

            if state == "regprofile10:org":
                value = None if text == "/skip" else text[:250]
                await self.execute("UPDATE users SET organization=$2,updated_at=NOW() WHERE telegram_id=$1", user["telegram_id"], value)
                await self.state_set(user["telegram_id"], "regprofile10:status", payload)
                return await m.answer("<b>5/9 · Чем ты сейчас занимаешься?</b>\nВыбери вариант, который ближе всего:", reply_markup=self._profile_status_kb())

            if state == "regprofile10:phone":
                value = None if text == "/skip" else text[:80]
                if value:
                    digits = re.sub(r"\D", "", value)
                    if len(digits) < 7 or len(digits) > 15:
                        return await m.answer("Проверь номер: лучше отправить его с кодом страны, например <code>+374...</code>, или <code>/skip</code>.")
                await self.execute("UPDATE users SET phone=$2,updated_at=NOW() WHERE telegram_id=$1", user["telegram_id"], value)
                await self.state_set(user["telegram_id"], "regprofile10:email", payload)
                return await m.answer("<b>7/9 · Email</b>\nПолезен для подтверждений, материалов и организационной связи.\n\nОтправь email или <code>/skip</code>.")

            if state == "regprofile10:email":
                value = None if text == "/skip" else text[:180].lower()
                if value and not _EMAIL_RE.match(value):
                    return await m.answer("Похоже, в email есть ошибка. Проверь адрес или отправь <code>/skip</code>.")
                await self.execute("UPDATE users SET email=$2,updated_at=NOW() WHERE telegram_id=$1", user["telegram_id"], value)
                await self.state_set(user["telegram_id"], "regprofile10:social", payload)
                return await m.answer("<b>8/9 · Соцсети</b>\nОставь одну удобную ссылку: Telegram, Instagram, VK, LinkedIn или другую. Можно просто <code>@username</code>.\n\nЕсли не хочешь указывать — <code>/skip</code>.")

            if state == "regprofile10:social":
                value = None if text == "/skip" else text[:300]
                if value and len(value) < 3:
                    return await m.answer("Отправь ссылку / @username или <code>/skip</code>.")
                await self.execute("UPDATE users SET social_url=$2,updated_at=NOW() WHERE telegram_id=$1", user["telegram_id"], value)
                payload["interests"] = _json_list(user["interests"])
                await self.state_set(user["telegram_id"], "regprofile10:interests", payload)
                return await m.answer(
                    "<b>9/9 · Что тебе интересно?</b>\n\nВыбери несколько направлений. Это поможет со временем делать рекомендации точнее, а не присылать всё подряд.",
                    reply_markup=self._interests_kb(payload["interests"]),
                )

            if state.startswith("support:new:"):
                topic = state.split(":", 2)[2]
                if topic not in SUPPORT_TOPICS:
                    raise SkipHandler
                ticket = await self.fetchrow(
                    "INSERT INTO support_tickets(user_id,topic,status) VALUES($1,$2,'open') RETURNING *", user["telegram_id"], topic
                )
                ok = await self._send_support_message(ticket["id"], user, m, "viewer")
                if not ok:
                    await self.execute("DELETE FROM support_tickets WHERE id=$1", ticket["id"])
                    return
                await self.state_clear(user["telegram_id"])
                await m.answer(
                    f"<b>Отправлено ✅ · обращение #{ticket['id']}</b>\n\nКоманда увидит вопрос в общем входящем. Ответ придёт сюда — ничего дополнительно проверять не нужно.",
                    reply_markup=_kb([[('🗂 Мои обращения','support:mine')],[('🏠 Меню','menu')]]),
                )
                await self._support_notify_staff(ticket["id"])
                return

            if state.startswith("support:userreply:"):
                ticket_id = int(state.split(":")[2])
                ticket = await self.fetchrow("SELECT * FROM support_tickets WHERE id=$1 AND user_id=$2 AND status<>'closed'", ticket_id, user["telegram_id"])
                if not ticket:
                    await self.state_clear(user["telegram_id"])
                    return await m.answer("Это обращение уже закрыто.")
                if not await self._send_support_message(ticket_id, user, m, "viewer"):
                    return
                await self.execute("UPDATE support_tickets SET status='open',last_message_at=NOW(),updated_at=NOW() WHERE id=$1", ticket_id)
                await self.state_clear(user["telegram_id"])
                await m.answer("Ответ отправлен команде ✅")
                await self._support_notify_staff(ticket_id, "Новый ответ участника")
                return

            if state.startswith("support:reply:"):
                if user["role"] not in {"owner", "admin", "editor"}:
                    await self.state_clear(user["telegram_id"])
                    return
                ticket_id = int(state.split(":")[2])
                ticket = await self.fetchrow("SELECT * FROM support_tickets WHERE id=$1 AND status<>'closed'", ticket_id)
                if not ticket:
                    await self.state_clear(user["telegram_id"])
                    return await m.answer("Обращение уже закрыто.")
                if not await self._send_support_message(ticket_id, user, m, user["role"]):
                    return
                await self.execute(
                    "UPDATE support_tickets SET status='answered',assigned_to=$2,last_message_at=NOW(),updated_at=NOW() WHERE id=$1",
                    ticket_id, user["telegram_id"],
                )
                await self.state_clear(user["telegram_id"])
                reply_body = (m.text or m.caption or "Ответ с вложением").strip()[:3000]
                try:
                    await self.bot.send_message(
                        ticket["user_id"],
                        f"<b>Ответ команды · обращение #{ticket_id}</b> 💬\n\n{_safe(reply_body)}",
                        reply_markup=_kb([[('↩️ Ответить', f"support:userreply:{ticket_id}")], [('🗂 Мои обращения','support:mine')]]),
                    )
                    if m.photo:
                        await self.bot.send_photo(ticket["user_id"], m.photo[-1].file_id)
                except Exception:
                    log.exception("Could not deliver support reply ticket=%s", ticket_id)
                await m.answer("Ответ отправлен участнику ✅", reply_markup=_kb([[('⬅️ К обращению', f"support:staff:{ticket_id}")]]))
                return

            raise SkipHandler

        super()._register_handlers()


async def run_commission_bot_community(database_url: str) -> None:
    token = os.getenv("COMMISSION_BOT_TOKEN", "").strip()
    if not token:
        log.info("COMMISSION_BOT_TOKEN not set; commission bot disabled")
        return
    bootstrap = os.getenv("COMMISSION_BOOTSTRAP_CODE", "").strip()
    app = CommissionBotCommunity(database_url, token, bootstrap)
    await app.run()
