from __future__ import annotations

from datetime import datetime

from aiogram import F
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Message

from app.commission_bot import _kb
from app.commission_bot_admin_ops import CommissionBotAdminOps
from app.commission_bot_ultimate import DEFAULT_TZ, TZ_LABELS, _parse_local


class CommissionBotOnlineOnly(CommissionBotAdminOps):
    """Commission events are online; announcements without a date remain supported."""

    def _register_handlers(self):
        r = self.router

        @r.message(F.chat.type == ChatType.PRIVATE)
        async def online_event_creation_state(m: Message):
            user = await self.ensure_user(m.from_user)
            st = await self.state_get(user["telegram_id"])
            if not st or str(st["state"]) != "b:event_at":
                raise SkipHandler
            p = dict(st["payload"] or {})
            text = (m.text or "").strip()
            tz_name = p.get("event_timezone") or user["timezone_name"] or DEFAULT_TZ
            if text == "/skip":
                p["event_at"] = None
                p["event_format"] = None
                p["event_location"] = None
                await self.state_set(user["telegram_id"], "b:regmode", p)
                return await m.answer(
                    "У этой публикации нет даты — оставляем её как информационную. Нужна регистрация?",
                    reply_markup=_kb([
                        [("✅ Внутри бота", "b:reg:internal")],
                        [("🔗 Внешняя ссылка", "b:reg:external")],
                        [("Без регистрации", "b:reg:none")],
                    ]),
                )
            event_at = _parse_local(text, tz_name)
            if not event_at:
                return await m.answer("Не узнал дату. Отправь так: <code>15.10.2026 19:00</code> — время в твоём часовом поясе.")
            p["event_at"] = event_at.isoformat()
            p["event_format"] = "online"
            await self.state_set(user["telegram_id"], "b:location", p)
            return await m.answer(
                "<b>Событие будет онлайн 💻</b>\n\nОтправь ссылку Zoom / Teams / Meet. Она сохранится как ссылка подключения и не будет показываться участникам раньше времени.\n\nЕсли ссылка появится позже — отправь /skip и добавь её из управления событием.",
            )

        @r.callback_query(F.data.startswith("b:format:"))
        async def obsolete_format_choice(c: CallbackQuery):
            await c.answer("Все события Комиссии проходят онлайн")
            st = await self.state_get(c.from_user.id)
            if not st:
                return
            p = dict(st["payload"] or {})
            p["event_format"] = "online"
            await self.state_set(c.from_user.id, "b:location", p)
            await c.message.answer("💻 Формат: онлайн. Отправь ссылку подключения или /skip — её можно добавить позже.")

        super()._register_handlers()
