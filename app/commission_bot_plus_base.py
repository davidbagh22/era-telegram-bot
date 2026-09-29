from __future__ import annotations

import asyncio
import csv
import html
import io
import json
import logging
import os
import secrets
from datetime import datetime, timezone

from aiogram import F
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.commission_bot import CommissionBot, _kb, _fmt_dt

log = logging.getLogger(__name__)

ROLE_LABELS = {
    "owner": "Владелец",
    "admin": "Администратор",
    "editor": "Модератор",
    "viewer": "Участник",
}

EXTRA_DDL = r'''
ALTER TABLE users ADD COLUMN IF NOT EXISTS registration_name TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS organization TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS participant_profile_complete BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE broadcasts ADD COLUMN IF NOT EXISTS registration_form TEXT NOT NULL DEFAULT 'quick';
ALTER TABLE registrations ADD COLUMN IF NOT EXISTS answers JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS staff_invites (
  token TEXT PRIMARY KEY,
  role TEXT NOT NULL CHECK (role IN ('admin','editor')),
  created_by BIGINT NOT NULL REFERENCES users(telegram_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at TIMESTAMPTZ NOT NULL,
  used_by BIGINT REFERENCES users(telegram_id),
  used_at TIMESTAMPTZ,
  revoked BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_staff_invites_active
  ON staff_invites(expires_at)
  WHERE used_at IS NULL AND revoked = FALSE;
'''


def _role_label(role: str) -> str:
    return ROLE_LABELS.get(role, role)


def _safe(value) -> str:
    return html.escape(str(value or ""))


class CommissionBotPlus(CommissionBot):
    async def init_db(self) -> None:
        await super().init_db()
        await self.execute(EXTRA_DDL)

    async def send_menu(self, chat_id: int, user, text: str = "Выберите действие:"):
        role = user["role"]
        if text.startswith("Добро пожаловать") or text == "Выберите действие:":
            text = (
                "<b>МОЛОДЁЖЬ ВКСРС</b>\n\n"
                "Единое пространство Комиссии по взаимодействию с молодёжью. "
                "Здесь собраны актуальные мероприятия, возможности, регистрации "
                "и персональные напоминания.\n\nВыберите раздел:"
            )

        rows = [
            [("📅 Ближайшие", "events:list"), ("🎟 Мои регистрации", "regs:mine")],
            [("👤 Профиль", "profile:view"), ("🔔 Уведомления", "notify:view")],
        ]
        if role in {"editor", "admin", "owner"}:
            rows = [
                [("➕ Создать публикацию", "b:new")],
                [("📝 Мои публикации", "b:mine"), ("📋 Регистрации", "regadmin:list")],
            ] + rows
        if role in {"admin", "owner"}:
            rows += [
                [("✅ На согласовании", "review:list")],
                [("📣 Чаты и каналы", "targets:list"), ("📊 Аналитика", "analytics")],
            ]
        if role == "owner":
            rows += [[("👥 Команда", "team:menu")]]
        await self.bot.send_message(chat_id, text, reply_markup=_kb(rows))

    async def register(self, chat_id: int, user, bid: int):
        b = await self.fetchrow("SELECT * FROM broadcasts WHERE id=$1", bid)
        if not b or b["status"] not in {"approved", "published"}:
            return await self.bot.send_message(chat_id, "Регистрация сейчас недоступна.")
        if not user["onboarding_complete"]:
            return await self.start_onboarding(
                chat_id, user, {"type": "register", "broadcast_id": bid}
            )
        if b["registration_deadline"] and b["registration_deadline"] < datetime.now(timezone.utc):
            return await self.bot.send_message(chat_id, "Срок регистрации завершён.")

        existing = await self.fetchrow(
            "SELECT * FROM registrations WHERE broadcast_id=$1 AND telegram_id=$2",
            bid,
            user["telegram_id"],
        )
        if existing and existing["status"] in {"registered", "waitlist", "attended"}:
            label = "основном списке ✅" if existing["status"] != "waitlist" else "листе ожидания ⏳"
            return await self.bot.send_message(
                chat_id,
                f"Вы уже в {label}\n\n<b>{_safe(b['title'])}</b>",
                reply_markup=_kb([[('❌ Отменить регистрацию', f"regcancel:{bid}")]]),
            )

        if b["registration_form"] == "standard" and not user["participant_profile_complete"]:
            await self.state_set(
                user["telegram_id"],
                "regprofile:name",
                {"broadcast_id": bid},
            )
            default_name = " ".join(
                x for x in [user["first_name"], user["last_name"]] if x
            ).strip()
            await self.bot.send_message(
                chat_id,
                "<b>Короткая анкета участника</b>\n\n"
                "Заполняется один раз — на следующих мероприятиях повторять не придётся.\n\n"
                f"1/4. Отправьте ФИО для списка участников."
                + (f"\nМожно отправить <code>/auto</code>, чтобы использовать: {_safe(default_name)}" if default_name else ""),
            )
            return

        answers = {
            "name": user["registration_name"] or " ".join(
                x for x in [user["first_name"], user["last_name"]] if x
            ).strip(),
            "organization": user["organization"],
            "phone": user["phone"],
            "email": user["email"],
            "country": user["country_code"],
        }

        assert self.pool
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                br = await conn.fetchrow("SELECT * FROM broadcasts WHERE id=$1 FOR UPDATE", bid)
                status = "registered"
                if br["capacity"]:
                    count = await conn.fetchval(
                        "SELECT COUNT(*) FROM registrations WHERE broadcast_id=$1 AND status IN ('registered','attended')",
                        bid,
                    )
                    if count >= br["capacity"]:
                        status = "waitlist"
                await conn.execute(
                    """INSERT INTO registrations(broadcast_id,telegram_id,status,source,answers,updated_at)
                    VALUES($1,$2,$3,'telegram',$4::jsonb,NOW())
                    ON CONFLICT(broadcast_id,telegram_id) DO UPDATE SET
                      status=EXCLUDED.status,
                      answers=EXCLUDED.answers,
                      registered_at=NOW(),
                      updated_at=NOW()""",
                    bid,
                    user["telegram_id"],
                    status,
                    json.dumps(answers, ensure_ascii=False),
                )

        await self.audit(
            user["telegram_id"],
            "registration_created",
            "broadcast",
            bid,
            {"status": status, "form": b["registration_form"]},
        )

        date_line = f"\n📅 {_fmt_dt(b['event_at'])}" if b["event_at"] else ""
        if status == "registered":
            text = (
                "<b>Регистрация подтверждена ✅</b>\n\n"
                f"{_safe(b['title'])}{date_line}\n\n"
                "Вы в основном списке. Перед мероприятием бот пришлёт выбранные организатором напоминания."
            )
        else:
            pos = await self.fetchrow(
                """SELECT COUNT(*) AS n FROM registrations
                WHERE broadcast_id=$1 AND status='waitlist' AND registered_at <=
                    (SELECT registered_at FROM registrations WHERE broadcast_id=$1 AND telegram_id=$2)""",
                bid,
                user["telegram_id"],
            )
            text = (
                "<b>Вы в листе ожидания ⏳</b>\n\n"
                f"{_safe(b['title'])}{date_line}\n"
                f"Позиция: {pos['n'] if pos else '—'}\n\n"
                "Если освободится место, бот автоматически переведёт вас в основной список и сообщит об этом."
            )
        await self.bot.send_message(
            chat_id,
            text,
            reply_markup=_kb([[('❌ Отменить регистрацию', f"regcancel:{bid}")], [('⬅️ В меню', 'menu')]]),
        )

    async def _consume_staff_invite(self, message: Message, token: str) -> None:
        user = await self.ensure_user(message.from_user)
        invite = await self.fetchrow(
            """UPDATE staff_invites
            SET used_by=$2, used_at=NOW()
            WHERE token=$1 AND used_at IS NULL AND revoked=FALSE AND expires_at>NOW()
            RETURNING *""",
            token,
            user["telegram_id"],
        )
        if not invite:
            return await message.answer(
                "Ссылка недействительна или уже использована. Попросите владельца создать новое приглашение."
            )
        await self.execute(
            "UPDATE users SET role=$2,updated_at=NOW() WHERE telegram_id=$1",
            user["telegram_id"],
            invite["role"],
        )
        await self.audit(
            user["telegram_id"],
            "staff_invite_accepted",
            "staff_invite",
            token,
            {"role": invite["role"]},
        )
        user = await self.fetchrow("SELECT * FROM users WHERE telegram_id=$1", user["telegram_id"])
        await message.answer(
            f"Доступ активирован ✅\nРоль: <b>{_role_label(user['role'])}</b>"
        )
        if not user["onboarding_complete"]:
            return await self.start_onboarding(message.chat.id, user)
        await self.send_menu(message.chat.id, user)

    def _register_handlers(self):
        r = self.router

        @r.message(F.text.startswith("/start staff_"))
        async def staff_start(m: Message):
            token = (m.text or "").split("staff_", 1)[1].strip().split()[0]
            await self._consume_staff_invite(m, token)

        @r.message(Command("join"))
        async def staff_join(m: Message):
            parts = (m.text or "").split(maxsplit=1)
            if len(parts) != 2:
                return await m.answer("Формат: <code>/join КОД</code>")
            await self._consume_staff_invite(m, parts[1].strip())

        @r.message(F.chat.type == ChatType.PRIVATE)
        async def plus_state(m: Message):
            user = await self.ensure_user(m.from_user)
            st = await self.state_get(user["telegram_id"])
            if not st or not str(st["state"]).startswith("regprofile:"):
                raise SkipHandler
            state = st["state"]
            payload = dict(st["payload"] or {})
            text = (m.text or "").strip()
            bid = int(payload["broadcast_id"])

            if state == "regprofile:name":
                if text == "/auto":
                    value = " ".join(
                        x for x in [user["first_name"], user["last_name"]] if x
                    ).strip()
                    if not value:
                        return await m.answer("В Telegram не указано имя. Отправьте ФИО текстом.")
                elif len(text) < 3:
                    return await m.answer("Отправьте ФИО текстом или <code>/auto</code>.")
                else:
                    value = text[:180]
                await self.execute(
                    "UPDATE users SET registration_name=$2,updated_at=NOW() WHERE telegram_id=$1",
                    user["telegram_id"], value,
                )
                await self.state_set(user["telegram_id"], "regprofile:org", payload)
                return await m.answer("2/4. Организация / вуз / место работы. Если не нужно — <code>/skip</code>.")

            if state == "regprofile:org":
                value = None if text == "/skip" else text[:250]
                await self.execute(
                    "UPDATE users SET organization=$2,updated_at=NOW() WHERE telegram_id=$1",
                    user["telegram_id"], value,
                )
                await self.state_set(user["telegram_id"], "regprofile:phone", payload)
                return await m.answer("3/4. Номер телефона для связи или <code>/skip</code>.")

            if state == "regprofile:phone":
                value = None if text == "/skip" else text[:80]
                if value and len(value) < 6:
                    return await m.answer("Проверьте номер или отправьте <code>/skip</code>.")
                await self.execute(
                    "UPDATE users SET phone=$2,updated_at=NOW() WHERE telegram_id=$1",
                    user["telegram_id"], value,
                )
                await self.state_set(user["telegram_id"], "regprofile:email", payload)
                return await m.answer("4/4. Email или <code>/skip</code>.")

            if state == "regprofile:email":
                value = None if text == "/skip" else text[:180]
                if value and ("@" not in value or "." not in value.split("@")[-1]):
                    return await m.answer("Похоже, email указан неверно. Исправьте или отправьте <code>/skip</code>.")
                await self.execute(
                    """UPDATE users SET email=$2,participant_profile_complete=TRUE,
                    updated_at=NOW() WHERE telegram_id=$1""",
                    user["telegram_id"], value,
                )
                await self.state_clear(user["telegram_id"])
                user = await self.fetchrow("SELECT * FROM users WHERE telegram_id=$1", user["telegram_id"])
                await m.answer("Анкета сохранена ✅ Больше заполнять её не потребуется.")
                return await self.register(m.chat.id, user, bid)

        @r.callback_query(F.data == "b:reg:internal")
        async def registration_form_choice(c: CallbackQuery):
            await c.answer()
            st = await self.state_get(c.from_user.id)
            if not st:
                return
            p = dict(st["payload"] or {})
            p["registration_mode"] = "internal"
            await self.state_set(c.from_user.id, "b:regform", p)
            await c.message.answer(
                "Как регистрировать участников?",
                reply_markup=_kb([
                    [("⚡ Быстро — 1 клик", "b:regform:quick")],
                    [("📝 С анкетой участника", "b:regform:standard")],
                ]),
            )

        @r.callback_query(F.data.startswith("b:regform:"))
        async def registration_form_selected(c: CallbackQuery):
            await c.answer()
            st = await self.state_get(c.from_user.id)
            if not st:
                return
            p = dict(st["payload"] or {})
            p["registration_form"] = c.data.split(":", 2)[2]
            await self.state_set(c.from_user.id, "b:capacity", p)
            await c.message.answer("Количество мест? Отправьте число или <code>/skip</code>.")

        @r.callback_query(F.data == "b:submit")
        async def submit_plus(c: CallbackQuery):
            await c.answer()
            st = await self.state_get(c.from_user.id)
            if not st or st["state"] != "b:preview":
                return
            p = dict(st["payload"] or {})
            audience = {
                "countries": p.get("countries", ["ALL"]),
                "networks": p.get("networks", ["commission"]),
                "channels": p.get("channels", {"targets": True, "dm": False}),
            }
            b = await self.fetchrow(
                """INSERT INTO broadcasts(
                    content_type,title,description,media_file_id,event_at,
                    registration_mode,registration_url,registration_deadline,capacity,
                    audience,reminder_offsets,status,created_by,submitted_at,registration_form
                ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,$11::jsonb,
                         'pending',$12,NOW(),$13) RETURNING *""",
                p.get("content_type", "event"),
                p["title"],
                p["description"],
                p.get("media_file_id"),
                datetime.fromisoformat(p["event_at"]) if p.get("event_at") else None,
                p.get("registration_mode", "none"),
                p.get("registration_url"),
                datetime.fromisoformat(p["registration_deadline"]) if p.get("registration_deadline") else None,
                p.get("capacity"),
                json.dumps(audience, ensure_ascii=False),
                json.dumps(p.get("reminders", [])),
                c.from_user.id,
                p.get("registration_form", "quick"),
            )
            await self.state_clear(c.from_user.id)
            await self.audit(c.from_user.id, "broadcast_submitted", "broadcast", b["id"], audience)
            admins = await self.fetch("SELECT telegram_id FROM users WHERE role IN ('admin','owner')")
            for admin in admins:
                try:
                    await self.bot.send_message(
                        admin["telegram_id"],
                        f"Новая публикация на согласовании:\n<b>{_safe(b['title'])}</b>",
                        reply_markup=_kb([[('Проверить', f"review:{b['id']}")]]),
                    )
                except Exception:
                    pass
            await c.message.answer(f"Отправлено на согласование ✅\nПубликация #{b['id']}")

        @r.callback_query(F.data == "team:menu")
        async def team_menu(c: CallbackQuery):
            await c.answer()
            u = await self.ensure_user(c.from_user)
            if u["role"] != "owner":
                return
            await c.message.answer(
                "<b>Команда бота</b>\n\n"
                "Администратор: согласование публикаций, чаты/каналы, аналитика и регистрации.\n"
                "Модератор: создаёт публикации и работает со списками участников.\n\n"
                "Приглашения одноразовые и действуют 72 часа.",
                reply_markup=_kb([
                    [("➕ Администратор", "team:invite:admin"), ("➕ Модератор", "team:invite:editor")],
                    [("👥 Список команды", "team:list")],
                    [("⬅️ В меню", "menu")],
                ]),
            )

        @r.callback_query(F.data.startswith("team:invite:"))
        async def team_invite(c: CallbackQuery):
            await c.answer()
            owner = await self.ensure_user(c.from_user)
            if owner["role"] != "owner":
                return
            role = c.data.split(":", 2)[2]
            if role not in {"admin", "editor"}:
                return
            token = secrets.token_urlsafe(7)
            await self.execute(
                """INSERT INTO staff_invites(token,role,created_by,expires_at)
                VALUES($1,$2,$3,NOW()+INTERVAL '72 hours')""",
                token,
                role,
                owner["telegram_id"],
            )
            me = await self.bot.get_me()
            url = f"https://t.me/{me.username}?start=staff_{token}"
            await c.message.answer(
                f"<b>Приглашение: {_role_label(role)}</b>\n\n"
                "Отправьте эту кнопку нужному человеку. После нажатия роль активируется автоматически.\n"
                "Ссылка одноразовая и действует 72 часа.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=f"Войти как {_role_label(role)}", url=url)],
                    [InlineKeyboardButton(text="⬅️ Команда", callback_data="team:menu")],
                ]),
            )

        @r.callback_query(F.data == "team:list")
        async def team_list(c: CallbackQuery):
            await c.answer()
            owner = await self.ensure_user(c.from_user)
            if owner["role"] != "owner":
                return
            rows = await self.fetch(
                "SELECT * FROM users WHERE role IN ('owner','admin','editor') ORDER BY CASE role WHEN 'owner' THEN 0 WHEN 'admin' THEN 1 ELSE 2 END, first_name NULLS LAST"
            )
            buttons = []
            for x in rows:
                name = " ".join(v for v in [x["first_name"], x["last_name"]] if v).strip() or x["username"] or str(x["telegram_id"])
                buttons.append([(
                    f"{_role_label(x['role'])} · {name}"[:60],
                    f"team:user:{x['telegram_id']}",
                )])
            buttons.append([("⬅️ Команда", "team:menu")])
            await c.message.answer("<b>Команда</b>", reply_markup=_kb(buttons))

        @r.callback_query(F.data.startswith("team:user:"))
        async def team_user(c: CallbackQuery):
            await c.answer()
            owner = await self.ensure_user(c.from_user)
            if owner["role"] != "owner":
                return
            uid = int(c.data.split(":")[2])
            member = await self.fetchrow("SELECT * FROM users WHERE telegram_id=$1", uid)
            if not member:
                return
            name = " ".join(v for v in [member["first_name"], member["last_name"]] if v).strip() or member["username"] or str(uid)
            text = f"<b>{_safe(name)}</b>\nРоль: {_role_label(member['role'])}\nTelegram ID: <code>{uid}</code>"
            if member["role"] == "owner":
                return await c.message.answer(text + "\n\nРоль владельца нельзя снять из меню.")
            await c.message.answer(
                text,
                reply_markup=_kb([
                    [("Сделать администратором", f"team:set:{uid}:admin")],
                    [("Сделать модератором", f"team:set:{uid}:editor")],
                    [("Убрать доступ", f"team:set:{uid}:viewer")],
                    [("⬅️ Список", "team:list")],
                ]),
            )

        @r.callback_query(F.data.startswith("team:set:"))
        async def team_set(c: CallbackQuery):
            await c.answer()
            owner = await self.ensure_user(c.from_user)
            if owner["role"] != "owner":
                return
            _, _, uid_s, role = c.data.split(":", 3)
            uid = int(uid_s)
            if role not in {"admin", "editor", "viewer"}:
                return
            target = await self.fetchrow("SELECT role FROM users WHERE telegram_id=$1", uid)
            if not target or target["role"] == "owner":
                return await c.message.answer("Эту роль изменить нельзя.")
            await self.execute("UPDATE users SET role=$2,updated_at=NOW() WHERE telegram_id=$1", uid, role)
            await self.audit(owner["telegram_id"], "staff_role_changed", "user", uid, {"role": role})
            await c.message.answer(f"Готово ✅ Новая роль: <b>{_role_label(role)}</b>")
            try:
                await self.bot.send_message(uid, f"Ваша роль в боте изменена: <b>{_role_label(role)}</b>")
            except Exception:
                pass

        @r.callback_query(F.data == "regadmin:list")
        async def registration_admin_list(c: CallbackQuery):
            await c.answer()
            u = await self.ensure_user(c.from_user)
            if u["role"] not in {"editor", "admin", "owner"}:
                return
            rows = await self.fetch(
                """SELECT b.id,b.title,b.event_at,b.capacity,b.status,
                COUNT(r.id) FILTER (WHERE r.status IN ('registered','attended')) AS registered,
                COUNT(r.id) FILTER (WHERE r.status='waitlist') AS waitlist
                FROM broadcasts b LEFT JOIN registrations r ON r.broadcast_id=b.id
                WHERE b.registration_mode='internal'
                GROUP BY b.id ORDER BY b.event_at DESC NULLS LAST,b.id DESC LIMIT 20"""
            )
            if not rows:
                return await c.message.answer("Внутренних регистраций пока нет.")
            buttons = []
            for b in rows:
                cap = f"/{b['capacity']}" if b["capacity"] else ""
                buttons.append([(
                    f"#{b['id']} · {b['registered']}{cap} · ⏳{b['waitlist']} · {b['title']}"[:60],
                    f"regadmin:event:{b['id']}",
                )])
            buttons.append([("⬅️ В меню", "menu")])
            await c.message.answer("<b>Регистрации участников</b>", reply_markup=_kb(buttons))

        @r.callback_query(F.data.startswith("regadmin:event:"))
        async def registration_admin_event(c: CallbackQuery):
            await c.answer()
            u = await self.ensure_user(c.from_user)
            if u["role"] not in {"editor", "admin", "owner"}:
                return
            bid = int(c.data.split(":")[2])
            b = await self.fetchrow("SELECT * FROM broadcasts WHERE id=$1", bid)
            if not b:
                return
            rows = await self.fetch(
                """SELECT r.status,r.registered_at,u.telegram_id,u.username,u.first_name,u.last_name,
                u.registration_name,u.country_name,u.organization,u.phone,u.email
                FROM registrations r JOIN users u ON u.telegram_id=r.telegram_id
                WHERE r.broadcast_id=$1 AND r.status<>'cancelled'
                ORDER BY CASE r.status WHEN 'registered' THEN 0 WHEN 'attended' THEN 0 WHEN 'waitlist' THEN 1 ELSE 2 END,r.registered_at""",
                bid,
            )
            registered = sum(1 for x in rows if x["status"] in {"registered", "attended"})
            waiting = sum(1 for x in rows if x["status"] == "waitlist")
            remaining = max((b["capacity"] or registered) - registered, 0) if b["capacity"] else None
            text = (
                f"<b>{_safe(b['title'])}</b>\n\n"
                f"✅ В основном списке: {registered}"
                + (f" / {b['capacity']}" if b["capacity"] else "")
                + f"\n⏳ Лист ожидания: {waiting}"
                + (f"\n🟢 Свободно: {remaining}" if remaining is not None else "")
                + "\n\n"
            )
            for i, x in enumerate(rows[:25], 1):
                name = x["registration_name"] or " ".join(v for v in [x["first_name"], x["last_name"]] if v).strip() or x["username"] or str(x["telegram_id"])
                icon = "⏳" if x["status"] == "waitlist" else "✅"
                text += f"{i}. {icon} {_safe(name)}"
                if x["country_name"]:
                    text += f" · {_safe(x['country_name'])}"
                if x["organization"]:
                    text += f" · {_safe(x['organization'])}"
                text += "\n"
            if len(rows) > 25:
                text += f"\n…ещё {len(rows)-25}. Полный список — в CSV."
            await c.message.answer(
                text,
                reply_markup=_kb([
                    [("⬇️ Скачать CSV", f"regadmin:export:{bid}")],
                    [("⬅️ Все регистрации", "regadmin:list")],
                ]),
            )

        @r.callback_query(F.data.startswith("regadmin:export:"))
        async def registration_export(c: CallbackQuery):
            await c.answer()
            u = await self.ensure_user(c.from_user)
            if u["role"] not in {"editor", "admin", "owner"}:
                return
            bid = int(c.data.split(":")[2])
            b = await self.fetchrow("SELECT title FROM broadcasts WHERE id=$1", bid)
            rows = await self.fetch(
                """SELECT r.status,r.registered_at,u.telegram_id,u.username,u.registration_name,
                u.first_name,u.last_name,u.country_name,u.organization,u.phone,u.email
                FROM registrations r JOIN users u ON u.telegram_id=r.telegram_id
                WHERE r.broadcast_id=$1 ORDER BY r.registered_at""",
                bid,
            )
            out = io.StringIO()
            writer = csv.writer(out)
            writer.writerow(["status", "name", "telegram_id", "username", "country", "organization", "phone", "email", "registered_at"])
            for x in rows:
                name = x["registration_name"] or " ".join(v for v in [x["first_name"], x["last_name"]] if v).strip()
                writer.writerow([
                    x["status"], name, x["telegram_id"], x["username"] or "",
                    x["country_name"] or "", x["organization"] or "", x["phone"] or "",
                    x["email"] or "", x["registered_at"].isoformat() if x["registered_at"] else "",
                ])
            data = ("\ufeff" + out.getvalue()).encode("utf-8")
            await self.bot.send_document(
                c.message.chat.id,
                BufferedInputFile(data, filename=f"registrations_{bid}.csv"),
                caption=f"Регистрации: {_safe(b['title']) if b else '#'+str(bid)}",
            )

        @r.callback_query(F.data == "profile:view")
        async def profile_plus(c: CallbackQuery):
            await c.answer()
            u = await self.ensure_user(c.from_user)
            name = " ".join(v for v in [u["first_name"], u["last_name"]] if v).strip()
            text = (
                f"<b>Профиль</b>\n\n{_safe(name)}\n"
                f"Страна: {_safe(u['country_name'] or 'не выбрана')}\n"
                f"Роль: <b>{_role_label(u['role'])}</b>\n"
                f"Общие рассылки: {'✅' if u['telegram_opt_in'] else '❌'}"
            )
            if u["participant_profile_complete"]:
                text += "\nАнкета участника: ✅ сохранена"
            await c.message.answer(
                text,
                reply_markup=_kb([[('🌍 Изменить страну', 'profile:country')], [('⬅️ Меню', 'menu')]]),
            )

        super()._register_handlers()

    async def run(self):
        await self.init_db()
        await self.bot.set_my_description(
            "МОЛОДЁЖЬ ВКСРС — единое информационное пространство Комиссии по взаимодействию с молодёжью. "
            "Актуальные мероприятия и возможности, быстрая регистрация, персональные уведомления и напоминания — в одном боте."
        )
        await self.bot.set_my_short_description(
            "Мероприятия • возможности • регистрация • напоминания"
        )
        await self.bot.delete_webhook(drop_pending_updates=False)
        reminder_task = asyncio.create_task(self.reminders_loop())
        try:
            await self.dp.start_polling(
                self.bot, allowed_updates=self.dp.resolve_used_update_types()
            )
        finally:
            reminder_task.cancel()
            if self.pool:
                await self.pool.close()
            await self.bot.session.close()


async def run_commission_bot_plus(database_url: str) -> None:
    token = os.getenv("COMMISSION_BOT_TOKEN", "").strip()
    if not token:
        log.info("COMMISSION_BOT_TOKEN not set; commission bot disabled")
        return
    bootstrap = os.getenv("COMMISSION_BOOTSTRAP_CODE", "").strip()
    app = CommissionBotPlus(database_url, token, bootstrap)
    await app.run()
