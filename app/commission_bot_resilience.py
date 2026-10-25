from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from aiogram import F
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Message

from app.commission_bot import _kb
from app.commission_bot_online_only import CommissionBotOnlineOnly
from app.commission_bot_region import (
    REGION_COUNTRIES,
    REGION_LABELS,
    WORLD_COUNTRIES,
    _country_label,
)
from app.commission_bot_ultimate import DEFAULT_TZ, TZ_LABELS, _safe

log = logging.getLogger(__name__)

TOP_LEVEL_CALLBACKS = {
    "menu",
    "events:list",
    "regs:mine",
    "profile:view",
    "notify:view",
    "b:new",
    "b:mine",
    "review:list",
    "targets:list",
    "analytics",
    "regadmin:list",
    "team:menu",
    "support:new",
    "support:mine",
    "support:staff:list",
    "ux:targets",
    "ux:analytics",
    "ux:team",
    "ux:notifications",
    "ux:profile",
    "seg:menu",
    "seg:new",
    "tg:list",
    "svadm:menu",
    "crm:menu",
    "urgent:menu",
}

_MONTHS = (
    "янв",
    "фев",
    "мар",
    "апр",
    "мая",
    "июн",
    "июл",
    "авг",
    "сен",
    "окт",
    "ноя",
    "дек",
)
_WEEKDAYS = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
_TIME_PRESETS = ("10:00", "12:00", "14:00", "16:00", "18:00", "19:00", "20:00", "21:00")
_COUNTRIES_PAGE = 12


def _local_now(tz_name: str, now_utc: datetime | None = None) -> datetime:
    base = now_utc or datetime.now(timezone.utc)
    try:
        return base.astimezone(ZoneInfo(tz_name))
    except Exception:
        return base.astimezone(ZoneInfo(DEFAULT_TZ))


def _parse_flexible_local(
    raw: str,
    tz_name: str,
    now_utc: datetime | None = None,
) -> datetime | None:
    """Parse common human-friendly local date/time formats and return UTC."""
    text = re.sub(r"\s+", " ", (raw or "").strip().lower())
    if not text:
        return None

    now_local = _local_now(tz_name, now_utc)
    tz = now_local.tzinfo or ZoneInfo(DEFAULT_TZ)

    rel = re.fullmatch(r"(сегодня|завтра)\s+(\d{1,2})[:.](\d{2})", text)
    if rel:
        days = 0 if rel.group(1) == "сегодня" else 1
        hour, minute = int(rel.group(2)), int(rel.group(3))
        if hour > 23 or minute > 59:
            return None
        chosen = datetime.combine(now_local.date() + timedelta(days=days), time(hour, minute), tzinfo=tz)
        return chosen.astimezone(timezone.utc)

    normalized = text.replace("/", ".").replace("-", ".").replace(",", " ")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    formats = (
        "%d.%m.%Y %H:%M",
        "%d.%m.%y %H:%M",
        "%d.%m %H:%M",
    )
    for fmt in formats:
        try:
            parsed = datetime.strptime(normalized, fmt)
        except ValueError:
            continue
        if "%Y" not in fmt and "%y" not in fmt:
            parsed = parsed.replace(year=now_local.year)
            candidate = parsed.replace(tzinfo=tz)
            if candidate < now_local - timedelta(days=1):
                parsed = parsed.replace(year=now_local.year + 1)
        local_dt = parsed.replace(tzinfo=tz)
        return local_dt.astimezone(timezone.utc)
    return None


def _date_label(day: date, today: date) -> str:
    if day == today:
        prefix = "Сегодня"
    elif day == today + timedelta(days=1):
        prefix = "Завтра"
    else:
        prefix = _WEEKDAYS[day.weekday()]
    return f"{prefix} · {day.day} {_MONTHS[day.month - 1]}"


class CommissionBotResilient(CommissionBotOnlineOnly):
    """Final production layer: safer navigation, easier wizard and delivery guards."""

    async def _dispatch_ux_button(self, m: Message, user, text: str) -> None:
        st = await self.state_get(user["telegram_id"])
        if st:
            state = str(st["state"])
            if state.startswith("onboard:") and not user["onboarding_complete"]:
                if text not in {"❓ Помощь", "❓ Что делать", "⬅️ Назад", "✖️ Отмена"}:
                    await m.answer("Сначала выбери регион и страну — после этого откроется всё меню.")
                    return
            elif text not in {"❓ Помощь", "❓ Что делать", "⬅️ Назад"}:
                await self.state_clear(user["telegram_id"])
        await super()._dispatch_ux_button(m, user, text)

    async def _show_management(self, chat_id: int, user) -> None:
        if user["role"] not in {"admin", "owner"}:
            return await self.bot.send_message(chat_id, "Этот раздел доступен администратору и владельцу.")
        stats = await self.fetchrow(
            """SELECT
              (SELECT COUNT(*) FROM users WHERE onboarding_complete=TRUE) participants,
              (SELECT COUNT(*) FROM broadcasts WHERE status='pending') pending_reviews,
              (SELECT COUNT(*) FROM targets WHERE status='pending') pending_targets,
              (SELECT COUNT(*) FROM support_tickets WHERE status IN ('open','answered')) open_tickets,
              (SELECT COUNT(*) FROM deliveries WHERE status='failed' AND created_at>=NOW()-INTERVAL '7 days') delivery_failed,
              (SELECT COUNT(*) FROM targets WHERE status='approved' AND bot_can_post=TRUE) approved_targets,
              (SELECT COUNT(*) FROM users WHERE onboarding_complete=TRUE AND telegram_opt_in=TRUE) dm_reachable"""
        )
        lines = [
            "<b>⚙️ Центр управления</b>",
            "",
            "Сначала — то, что реально требует внимания:",
            f"👥 Участников: <b>{stats['participants'] or 0}</b>",
            f"✅ На согласовании: <b>{stats['pending_reviews'] or 0}</b>",
            f"🟡 Площадок ждут настройки: <b>{stats['pending_targets'] or 0}</b>",
            f"💬 Активных обращений: <b>{stats['open_tickets'] or 0}</b>",
            f"⚠️ Ошибок доставки за 7 дней: <b>{stats['delivery_failed'] or 0}</b>",
            "",
            f"📣 Готовых чатов/каналов: {stats['approved_targets'] or 0} · 👤 доступно для личных рассылок: {stats['dm_reachable'] or 0}",
            "",
            "Выбери задачу — всё остальное спрятано глубже, чтобы не мешало.",
        ]
        rows = [
            [("🎯 Рассылка", "seg:menu"), ("📣 Площадки", "tg:list")],
            [("👥 Участники", "crm:menu"), ("✅ Согласование", "review:list")],
            [("💬 Обращения", "support:staff:list"), ("📊 Аналитика", "ux:analytics")],
            [("📈 Эффективность", "svadm:menu"), ("🚨 Срочно", "urgent:menu")],
        ]
        if user["role"] == "owner":
            rows.append([("👥 Команда", "ux:team")])
        rows.extend(
            [
                [("🔔 Уведомления", "ux:notifications"), ("👤 Профиль", "ux:profile")],
                [("❓ Как пользоваться", "ux:help")],
                [("⬅️ Главное меню", "menu")],
            ]
        )
        await self.bot.send_message(chat_id, "\n".join(lines), reply_markup=_kb(rows))

    def _countries_multi(self, p):
        """Compact 195-country audience picker; also fixes the legacy malformed keyboard."""
        selected = list(p.get("countries") or ["ALL"])
        if "ALL" in selected:
            summary = "✅ Сейчас: все страны"
        elif selected:
            summary = f"✅ Выбрано стран: {len(selected)}"
        else:
            summary = "⚠️ География не выбрана"
        return _kb(
            [
                [(summary, "aud:nop")],
                [("🌍 Все страны", "aud:all")],
                [("🗺 Выбрать регионы", "aud:regions"), ("🏳 Выбрать страны", "aud:countries")],
                [("Готово →", "b:countries:done")],
            ]
        )

    def _channels(self, p):
        channels = p.get("channels") or {}
        return _kb(
            [
                [
                    (
                        ("✅ " if channels.get("dm") else "▫️ ") + "👤 Участникам в личку",
                        "b:channel:dm",
                    )
                ],
                [
                    (
                        ("✅ " if channels.get("targets") else "▫️ ") + "📣 В чаты и каналы",
                        "b:channel:targets",
                    )
                ],
                [("Готово →", "b:channels:done")],
            ]
        )

    async def _edit_or_send(self, c: CallbackQuery, text: str, markup) -> None:
        try:
            await c.message.edit_text(text, reply_markup=markup)
        except Exception:
            await c.message.answer(text, reply_markup=markup)

    async def _show_event_date_picker(self, chat_id: int, uid: int, p: dict) -> None:
        user = await self.fetchrow("SELECT * FROM users WHERE telegram_id=$1", uid)
        tz_name = p.get("event_timezone") or (user["timezone_name"] if user else None) or DEFAULT_TZ
        p["event_timezone"] = tz_name
        await self.state_set(uid, "b:event_at", p)
        today = _local_now(tz_name).date()
        rows = []
        choices = []
        for offset in range(7):
            day = today + timedelta(days=offset)
            choices.append((_date_label(day, today), f"dt:d:{day.strftime('%Y%m%d')}"))
        for i in range(0, len(choices), 2):
            rows.append(choices[i : i + 2])
        rows += [
            [("✍️ Ввести вручную", "dt:manual"), ("Без даты", "dt:none")],
            [("⬅️ Назад", "nav:back"), ("✖️ Отмена", "nav:cancel")],
        ]
        await self.bot.send_message(
            chat_id,
            "<b>Когда проходит событие?</b>\n\n"
            f"Часовой пояс: <b>{_safe(TZ_LABELS.get(tz_name, tz_name))}</b>.\n"
            "Сначала выбери день — время предложу следующим шагом. "
            "Если это просто информационная публикация, выбери «Без даты».",
            reply_markup=_kb(rows),
        )

    async def _show_event_time_picker(self, chat_id: int, uid: int, p: dict, chosen: date) -> None:
        p["_chosen_date"] = chosen.isoformat()
        await self.state_set(uid, "b:event_at", p)
        rows = []
        buttons = [(value, f"dt:t:{value.replace(':', '')}") for value in _TIME_PRESETS]
        for i in range(0, len(buttons), 2):
            rows.append(buttons[i : i + 2])
        rows += [[("✍️ Другое время", "dt:manual")], [("⬅️ К датам", "dt:dates")]]
        await self.bot.send_message(
            chat_id,
            f"<b>{chosen.day} {_MONTHS[chosen.month - 1]}</b> — во сколько начинаем?",
            reply_markup=_kb(rows),
        )

    async def _advance_after_event_datetime(self, chat_id: int, uid: int, p: dict, event_at: datetime) -> None:
        if event_at <= datetime.now(timezone.utc):
            return await self.bot.send_message(chat_id, "Это время уже прошло. Выбери будущую дату и время.")
        p["event_at"] = event_at.isoformat()
        p["event_format"] = "online"
        p.pop("_chosen_date", None)
        await self.state_set(uid, "b:location", p)
        await self.bot.send_message(
            chat_id,
            "<b>Событие будет онлайн 💻</b>\n\n"
            "Пришли ссылку Zoom / Teams / Meet. Она не будет показываться публично раньше времени.\n\n"
            "Если ссылки пока нет — отправь <code>/skip</code>, её можно добавить позже.",
        )

    async def _show_deadline_picker(self, chat_id: int, uid: int, p: dict) -> None:
        await self.state_set(uid, "b:deadline", p)
        if p.get("event_at"):
            rows = [
                [("За 7 дней", "dl:before:10080"), ("За 3 дня", "dl:before:4320")],
                [("За 24 часа", "dl:before:1440"), ("За 3 часа", "dl:before:180")],
                [("✍️ Другая дата", "dl:manual"), ("Без дедлайна", "dl:none")],
            ]
            text = (
                "<b>Когда закрыть регистрацию?</b>\n\n"
                "Можно выбрать дедлайн относительно начала события — так быстрее и без ручного ввода."
            )
        else:
            rows = [
                [("Через 7 дней", "dl:after:10080"), ("Через 14 дней", "dl:after:20160")],
                [("Через 30 дней", "dl:after:43200")],
                [("✍️ Другая дата", "dl:manual"), ("Без дедлайна", "dl:none")],
            ]
            text = "<b>Когда закрыть регистрацию?</b>\n\nВыбери быстрый вариант или задай дату вручную."
        rows.append([("⬅️ Назад", "nav:back"), ("✖️ Отмена", "nav:cancel")])
        await self.bot.send_message(chat_id, text, reply_markup=_kb(rows))

    async def _start_audience(self, chat_id: int, uid: int, p: dict) -> None:
        if not p.get("countries"):
            p["countries"] = ["ALL"]
        await self.state_set(uid, "b:countries", p)
        await self.bot.send_message(
            chat_id,
            "<b>Кому показываем публикацию?</b>\n\n"
            "По умолчанию выбраны все страны. Можно оставить так или сузить аудиторию по регионам/странам.",
            reply_markup=self._countries_multi(p),
        )

    async def _advance_to_networks(self, chat_id: int, uid: int, p: dict) -> None:
        countries = list(p.get("countries") or [])
        if not countries:
            return await self.bot.send_message(chat_id, "Выбери хотя бы одну страну/регион или «Все страны».")
        p["networks"] = list(p.get("networks") or ["commission"])
        await self.state_set(uid, "b:networks", p)
        await self.bot.send_message(
            chat_id,
            "<b>Какая сеть получит публикацию?</b>\n\n"
            "Комиссия выбрана по умолчанию. МДС отмечай только когда есть договорённость по этой публикации.",
            reply_markup=self._networks(p),
        )

    def _target_matches(self, target, countries: list[str]) -> bool:
        if "ALL" in countries:
            return True
        scope = target["geography_scope"] or "country"
        if scope == "global":
            return True
        if scope == "region":
            codes = set(REGION_COUNTRIES.get(target["region_code"], []))
            return bool(codes.intersection(countries))
        return bool(target["country_code"] and target["country_code"] in countries)

    async def _estimate_wizard_delivery(self, p: dict) -> tuple[int, int]:
        countries = list(p.get("countries") or ["ALL"])
        networks = list(p.get("networks") or ["commission"])
        channels = p.get("channels") or {}
        users_count = 0
        targets_count = 0
        if channels.get("dm"):
            if "ALL" in countries:
                row = await self.fetchrow(
                    "SELECT COUNT(*) n FROM users WHERE onboarding_complete=TRUE AND telegram_opt_in=TRUE"
                )
            else:
                row = await self.fetchrow(
                    "SELECT COUNT(*) n FROM users WHERE onboarding_complete=TRUE AND telegram_opt_in=TRUE AND country_code=ANY($1::text[])",
                    countries,
                )
            users_count = int(row["n"] or 0) if row else 0
        if channels.get("targets"):
            rows = await self.fetch(
                "SELECT * FROM targets WHERE status='approved' AND bot_can_post=TRUE AND network=ANY($1::text[])",
                networks,
            )
            targets_count = sum(1 for target in rows if self._target_matches(target, countries))
        return users_count, targets_count

    async def _show_delivery_picker(self, chat_id: int, uid: int, p: dict) -> None:
        p["channels"] = p.get("channels") or {"dm": True, "targets": False}
        await self.state_set(uid, "b:channels", p)
        users_count, targets_count = await self._estimate_wizard_delivery(p)
        await self.bot.send_message(
            chat_id,
            "<b>Куда отправляем?</b>\n\n"
            f"👤 Личные сообщения: <b>{users_count}</b> получателей\n"
            f"📣 Подключённые чаты/каналы: <b>{targets_count}</b>\n\n"
            "Можно включить оба способа. Перед публикацией бот ещё раз покажет настройки.",
            reply_markup=self._channels(p),
        )

    async def _advance_after_delivery(self, chat_id: int, uid: int, p: dict) -> None:
        channels = p.get("channels") or {}
        if not channels.get("dm") and not channels.get("targets"):
            return await self.bot.send_message(chat_id, "Выбери хотя бы один способ доставки.")
        users_count, targets_count = await self._estimate_wizard_delivery(p)
        if users_count + targets_count == 0:
            return await self.bot.send_message(
                chat_id,
                "<b>Сейчас отправлять некому.</b>\n\n"
                "Для личной рассылки нужны участники с включёнными уведомлениями. "
                "Для площадок — хотя бы один подтверждённый чат/канал с правом публикации.\n\n"
                "Измени способ доставки или подключи площадку в ⚙️ Управление → 📣 Площадки.",
                reply_markup=self._channels(p),
            )
        p["_delivery_estimate"] = {"users": users_count, "targets": targets_count}
        if not p.get("event_at"):
            p["reminders"] = []
            await self.state_set(uid, "b:preview", p)
            return await self.bot.send_message(
                chat_id,
                self._preview(p)
                + f"\n\n<b>Доставка</b>\n👤 {users_count} участников · 📣 {targets_count} площадок",
                reply_markup=_kb([[("✅ Отправить на согласование", "b:submit")], [("⬅️ Назад", "nav:back"), ("✖️ Отмена", "nav:cancel")]]),
            )
        p["reminders"] = p.get("reminders") or [4320, 1440, 180, 60]
        await self.state_set(uid, "b:reminders", p)
        await self.bot.send_message(
            chat_id,
            f"<b>Напоминания</b>\n\nДоставка: 👤 {users_count} участников · 📣 {targets_count} площадок.\n"
            "Отметь, когда напомнить зарегистрированным участникам.",
            reply_markup=self._reminders(p),
        )

    def _audience_country_markup(self, p: dict, region: str, page: int):
        codes = sorted(REGION_COUNTRIES[region], key=lambda code: WORLD_COUNTRIES[code])
        total_pages = max(1, (len(codes) + _COUNTRIES_PAGE - 1) // _COUNTRIES_PAGE)
        page = max(0, min(page, total_pages - 1))
        chunk = codes[page * _COUNTRIES_PAGE : (page + 1) * _COUNTRIES_PAGE]
        selected = set(p.get("countries") or [])
        buttons = [
            (("✅ " if code in selected else "▫️ ") + _country_label(code), f"aud:c:{code}")
            for code in chunk
        ]
        rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
        nav = []
        if page > 0:
            nav.append(("◀️", f"aud:cr:{region}:{page - 1}"))
        nav.append((f"{page + 1}/{total_pages}", "aud:nop"))
        if page < total_pages - 1:
            nav.append(("▶️", f"aud:cr:{region}:{page + 1}"))
        rows.append(nav)
        rows.append([("Готово →", "aud:c:done"), ("⬅️ К регионам", "aud:countries")])
        return _kb(rows), page

    async def _render_wizard_step(self, chat_id: int, uid: int, state: str, payload: dict) -> None:
        if state == "b:event_at":
            return await self._show_event_date_picker(chat_id, uid, payload)
        if state == "b:deadline":
            return await self._show_deadline_picker(chat_id, uid, payload)
        if state == "b:countries":
            return await self._start_audience(chat_id, uid, payload)
        if state == "b:channels":
            return await self._show_delivery_picker(chat_id, uid, payload)
        await super()._render_wizard_step(chat_id, uid, state, payload)

    async def deliver(self, bid: int, reminder_id: int | None = None, reminder=False):
        """Broadcast delivery with global/region/country target matching."""
        b = await self.fetchrow("SELECT * FROM broadcasts WHERE id=$1", bid)
        if not b:
            return
        audience = b["audience"] if isinstance(b["audience"], dict) else json.loads(b["audience"] or "{}")
        countries = list(audience.get("countries") or ["ALL"])
        networks = list(audience.get("networks") or ["commission"])
        channels = audience.get("channels") or {"targets": True, "dm": False}
        suffix = f"r{reminder_id}" if reminder_id else "initial"

        async def one(channel: str, recipient: int, direct: bool):
            key = f"b{bid}:{suffix}:{channel}:{recipient}"
            if await self.fetchrow("SELECT 1 FROM deliveries WHERE dedupe_key=$1 AND status='sent'", key):
                return
            msg, attempts, error = await self._send_with_retry(int(recipient), b, direct, reminder)
            if msg:
                await self.execute(
                    """INSERT INTO deliveries(broadcast_id,reminder_id,channel,recipient_key,status,dedupe_key,sent_at,message_id,attempts)
                    VALUES($1,$2,$3,$4,'sent',$5,NOW(),$6,$7)
                    ON CONFLICT(dedupe_key) DO UPDATE SET status='sent',error=NULL,sent_at=NOW(),message_id=EXCLUDED.message_id,attempts=EXCLUDED.attempts""",
                    bid,
                    reminder_id,
                    channel,
                    str(recipient),
                    key,
                    msg.message_id,
                    attempts,
                )
            else:
                await self.execute(
                    """INSERT INTO deliveries(broadcast_id,reminder_id,channel,recipient_key,status,error,dedupe_key,attempts)
                    VALUES($1,$2,$3,$4,'failed',$5,$6,$7)
                    ON CONFLICT(dedupe_key) DO UPDATE SET status='failed',error=EXCLUDED.error,attempts=EXCLUDED.attempts""",
                    bid,
                    reminder_id,
                    channel,
                    str(recipient),
                    str(error)[:500] if error else "unknown",
                    key,
                    attempts,
                )

        if channels.get("targets"):
            targets = await self.fetch(
                "SELECT * FROM targets WHERE status='approved' AND bot_can_post=TRUE AND network=ANY($1::text[])",
                networks,
            )
            for target in targets:
                if not self._target_matches(target, countries):
                    continue
                await one("telegram_target", int(target["chat_id"]), False)
                await asyncio.sleep(0.05)

        if channels.get("dm"):
            users = await self.fetch(
                "SELECT * FROM users WHERE onboarding_complete=TRUE AND telegram_opt_in=TRUE"
            )
            for user in users:
                if "ALL" not in countries and user["country_code"] not in countries:
                    continue
                await one("telegram_dm", int(user["telegram_id"]), True)
                await asyncio.sleep(0.05)

        if reminder and b["registration_mode"] == "internal":
            regs = await self.fetch(
                """SELECT u.* FROM registrations r
                   JOIN users u ON u.telegram_id=r.telegram_id
                   WHERE r.broadcast_id=$1 AND r.status IN ('registered','attended')""",
                bid,
            )
            for user in regs:
                await one("telegram_reg", int(user["telegram_id"]), True)

        if not reminder:
            await self.execute(
                "UPDATE broadcasts SET status='published',published_at=COALESCE(published_at,NOW()),updated_at=NOW() WHERE id=$1",
                bid,
            )

    def _register_handlers(self):
        r = self.router

        @r.callback_query(F.data.in_(TOP_LEVEL_CALLBACKS))
        async def clear_stale_state_before_navigation(c: CallbackQuery):
            user = await self.ensure_user(c.from_user)
            st = await self.state_get(user["telegram_id"])
            if not st:
                raise SkipHandler
            state = str(st["state"])
            if state.startswith("onboard:") and not user["onboarding_complete"]:
                await c.answer()
                await c.message.answer("Сначала выбери регион и страну — после этого откроется всё меню.")
                return
            await self.state_clear(user["telegram_id"])
            raise SkipHandler

        @r.message(F.chat.type == ChatType.PRIVATE)
        async def hardened_wizard_text(m: Message):
            user = await self.ensure_user(m.from_user)
            st = await self.state_get(user["telegram_id"])
            if not st:
                raise SkipHandler
            state = str(st["state"])
            p = dict(st["payload"] or {})
            text = (m.text or "").strip()
            tz_name = p.get("event_timezone") or user["timezone_name"] or DEFAULT_TZ

            if state == "b:media":
                if m.photo:
                    p["media_file_id"] = m.photo[-1].file_id
                elif text != "/skip":
                    return await m.answer("Пришли афишу как фото или нажми /skip.")
                p["event_timezone"] = tz_name
                return await self._show_event_date_picker(m.chat.id, user["telegram_id"], p)

            if state == "b:event_at":
                if text == "/skip":
                    p["event_at"] = None
                    p["event_format"] = None
                    p["event_location"] = None
                    await self.state_set(user["telegram_id"], "b:regmode", p)
                    return await m.answer(
                        "<b>Оставляем публикацию без даты.</b>\n\nНужна регистрация?",
                        reply_markup=_kb(
                            [
                                [("✅ Внутри бота", "b:reg:internal")],
                                [("🔗 Внешняя ссылка", "b:reg:external")],
                                [("Без регистрации", "b:reg:none")],
                            ]
                        ),
                    )
                parsed = _parse_flexible_local(text, tz_name)
                if not parsed:
                    await m.answer(
                        "Не смог распознать дату. Можно написать, например:\n"
                        "• <code>15.10 19:00</code>\n"
                        "• <code>15/10/2026 19:00</code>\n"
                        "• <code>завтра 19:00</code>\n\n"
                        "Или просто выбери день кнопкой ниже."
                    )
                    return await self._show_event_date_picker(m.chat.id, user["telegram_id"], p)
                return await self._advance_after_event_datetime(m.chat.id, user["telegram_id"], p, parsed)

            if state == "b:location":
                if text == "/skip":
                    p["event_location"] = None
                elif not text.startswith(("http://", "https://")):
                    return await m.answer("Для онлайн-события нужна ссылка вида <code>https://...</code> или /skip.")
                else:
                    p["event_location"] = text[:1000]
                await self.state_set(user["telegram_id"], "b:regmode", p)
                return await m.answer(
                    "<b>Как люди будут регистрироваться?</b>",
                    reply_markup=_kb(
                        [
                            [("✅ Внутри бота", "b:reg:internal")],
                            [("🔗 Внешняя ссылка", "b:reg:external")],
                            [("Без регистрации", "b:reg:none")],
                        ]
                    ),
                )

            if state == "b:capacity":
                if text == "/skip":
                    p["capacity"] = None
                else:
                    try:
                        value = int(text)
                        if value <= 0:
                            raise ValueError
                    except Exception:
                        return await m.answer("Введи положительное число или /skip.")
                    p["capacity"] = value
                return await self._show_deadline_picker(m.chat.id, user["telegram_id"], p)

            if state == "b:regurl":
                if not text.startswith(("http://", "https://")):
                    return await m.answer("Нужна полная ссылка, начинающаяся с <code>https://</code>.")
                p["registration_url"] = text[:1000]
                return await self._show_deadline_picker(m.chat.id, user["telegram_id"], p)

            if state == "b:deadline":
                if text == "/skip":
                    p["registration_deadline"] = None
                    return await self._start_audience(m.chat.id, user["telegram_id"], p)
                parsed = _parse_flexible_local(text, tz_name)
                if not parsed:
                    return await m.answer(
                        "Не понял дедлайн. Примеры: <code>14.10 20:00</code>, "
                        "<code>14/10/2026 20:00</code> или <code>завтра 18:00</code>."
                    )
                if parsed <= datetime.now(timezone.utc):
                    return await m.answer("Дедлайн должен быть в будущем.")
                if p.get("event_at") and parsed >= datetime.fromisoformat(p["event_at"]):
                    return await m.answer("Дедлайн регистрации должен быть раньше начала события.")
                p["registration_deadline"] = parsed.isoformat()
                return await self._start_audience(m.chat.id, user["telegram_id"], p)

            raise SkipHandler

        @r.callback_query(F.data == "dt:dates")
        async def date_back(c: CallbackQuery):
            await c.answer()
            st = await self.state_get(c.from_user.id)
            if not st:
                return
            await self._show_event_date_picker(c.message.chat.id, c.from_user.id, dict(st["payload"] or {}))

        @r.callback_query(F.data.startswith("dt:d:"))
        async def date_choose(c: CallbackQuery):
            await c.answer()
            st = await self.state_get(c.from_user.id)
            if not st:
                return
            try:
                chosen = datetime.strptime(c.data.split(":", 2)[2], "%Y%m%d").date()
            except ValueError:
                return
            await self._show_event_time_picker(c.message.chat.id, c.from_user.id, dict(st["payload"] or {}), chosen)

        @r.callback_query(F.data.startswith("dt:t:"))
        async def time_choose(c: CallbackQuery):
            await c.answer()
            st = await self.state_get(c.from_user.id)
            if not st:
                return
            p = dict(st["payload"] or {})
            chosen_date = p.get("_chosen_date")
            if not chosen_date:
                return await self._show_event_date_picker(c.message.chat.id, c.from_user.id, p)
            hhmm = c.data.split(":", 2)[2]
            try:
                hh, mm = int(hhmm[:2]), int(hhmm[2:])
                day = date.fromisoformat(chosen_date)
                tz_name = p.get("event_timezone") or DEFAULT_TZ
                local_dt = datetime.combine(day, time(hh, mm), tzinfo=ZoneInfo(tz_name))
            except Exception:
                return
            await self._advance_after_event_datetime(
                c.message.chat.id, c.from_user.id, p, local_dt.astimezone(timezone.utc)
            )

        @r.callback_query(F.data == "dt:manual")
        async def date_manual(c: CallbackQuery):
            await c.answer()
            st = await self.state_get(c.from_user.id)
            if not st:
                return
            p = dict(st["payload"] or {})
            p.pop("_chosen_date", None)
            await self.state_set(c.from_user.id, "b:event_at", p)
            await c.message.answer(
                "Напиши дату и время одним сообщением. Пойму варианты "
                "<code>15.10 19:00</code>, <code>15/10/2026 19:00</code> или <code>завтра 19:00</code>."
            )

        @r.callback_query(F.data == "dt:none")
        async def date_none(c: CallbackQuery):
            await c.answer()
            st = await self.state_get(c.from_user.id)
            if not st:
                return
            p = dict(st["payload"] or {})
            p["event_at"] = None
            p["event_format"] = None
            p["event_location"] = None
            p.pop("_chosen_date", None)
            await self.state_set(c.from_user.id, "b:regmode", p)
            await c.message.answer(
                "<b>Публикация без даты.</b>\n\nНужна регистрация?",
                reply_markup=_kb(
                    [
                        [("✅ Внутри бота", "b:reg:internal")],
                        [("🔗 Внешняя ссылка", "b:reg:external")],
                        [("Без регистрации", "b:reg:none")],
                    ]
                ),
            )

        @r.callback_query(F.data.startswith("b:reg:"))
        async def registration_mode(c: CallbackQuery):
            await c.answer()
            st = await self.state_get(c.from_user.id)
            if not st:
                return
            p = dict(st["payload"] or {})
            mode = c.data.split(":", 2)[2]
            if mode not in {"internal", "external", "none"}:
                return
            p["registration_mode"] = mode
            if mode == "internal":
                await self.state_set(c.from_user.id, "b:regform", p)
                return await c.message.answer(
                    "<b>Регистрация внутри бота</b>\n\nКакой сценарий нужен?",
                    reply_markup=_kb(
                        [
                            [("⚡ Быстро — 1 клик", "b:regform:quick")],
                            [("📝 С анкетой участника", "b:regform:standard")],
                        ]
                    ),
                )
            if mode == "external":
                await self.state_set(c.from_user.id, "b:regurl", p)
                return await c.message.answer("Пришли ссылку на внешнюю регистрацию <code>https://...</code>.")
            p["registration_url"] = None
            p["registration_deadline"] = None
            p["capacity"] = None
            return await self._start_audience(c.message.chat.id, c.from_user.id, p)

        @r.callback_query(F.data.startswith("dl:before:"))
        async def deadline_before(c: CallbackQuery):
            await c.answer()
            st = await self.state_get(c.from_user.id)
            if not st:
                return
            p = dict(st["payload"] or {})
            if not p.get("event_at"):
                return
            minutes = int(c.data.rsplit(":", 1)[1])
            event_at = datetime.fromisoformat(p["event_at"])
            deadline = event_at - timedelta(minutes=minutes)
            if deadline <= datetime.now(timezone.utc):
                return await c.message.answer("Этот вариант уже в прошлом — выбери более близкий дедлайн.")
            p["registration_deadline"] = deadline.isoformat()
            await self._start_audience(c.message.chat.id, c.from_user.id, p)

        @r.callback_query(F.data.startswith("dl:after:"))
        async def deadline_after(c: CallbackQuery):
            await c.answer()
            st = await self.state_get(c.from_user.id)
            if not st:
                return
            p = dict(st["payload"] or {})
            minutes = int(c.data.rsplit(":", 1)[1])
            p["registration_deadline"] = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()
            await self._start_audience(c.message.chat.id, c.from_user.id, p)

        @r.callback_query(F.data == "dl:none")
        async def deadline_none(c: CallbackQuery):
            await c.answer()
            st = await self.state_get(c.from_user.id)
            if not st:
                return
            p = dict(st["payload"] or {})
            p["registration_deadline"] = None
            await self._start_audience(c.message.chat.id, c.from_user.id, p)

        @r.callback_query(F.data == "dl:manual")
        async def deadline_manual(c: CallbackQuery):
            await c.answer()
            st = await self.state_get(c.from_user.id)
            if not st:
                return
            await self.state_set(c.from_user.id, "b:deadline", dict(st["payload"] or {}))
            await c.message.answer(
                "Напиши дедлайн одним сообщением: <code>14.10 20:00</code>, "
                "<code>14/10/2026 20:00</code> или <code>завтра 18:00</code>."
            )

        @r.callback_query(F.data == "aud:nop")
        async def audience_nop(c: CallbackQuery):
            await c.answer()

        @r.callback_query(F.data == "aud:all")
        async def audience_all(c: CallbackQuery):
            await c.answer()
            st = await self.state_get(c.from_user.id)
            if not st:
                return
            p = dict(st["payload"] or {})
            p["countries"] = ["ALL"]
            p.pop("_aud_regions", None)
            await self.state_set(c.from_user.id, "b:countries", p)
            await self._edit_or_send(
                c,
                "<b>Кому показываем публикацию?</b>\n\nВыбраны все страны.",
                self._countries_multi(p),
            )

        @r.callback_query(F.data == "aud:regions")
        async def audience_regions(c: CallbackQuery):
            await c.answer()
            st = await self.state_get(c.from_user.id)
            p = dict(st["payload"] or {}) if st else {}
            if "ALL" in list(p.get("countries") or []):
                p["countries"] = []
                p["_aud_regions"] = []
                await self.state_set(c.from_user.id, "b:countries", p)
            selected = set(p.get("_aud_regions") or [])
            rows = []
            items = list(REGION_LABELS.items())
            for i in range(0, len(items), 2):
                rows.append(
                    [
                        (("✅ " if key in selected else "▫️ ") + label, f"aud:r:{key}")
                        for key, label in items[i : i + 2]
                    ]
                )
            rows.append([("Готово →", "aud:r:done"), ("⬅️ Назад", "aud:back")])
            await self._edit_or_send(c, "<b>Выбери один или несколько регионов</b>", _kb(rows))

        @r.callback_query(F.data.startswith("aud:r:"))
        async def audience_region_toggle(c: CallbackQuery):
            await c.answer()
            region = c.data.split(":", 2)[2]
            if region == "done":
                st = await self.state_get(c.from_user.id)
                if not st:
                    return
                p = dict(st["payload"] or {})
                if not p.get("countries"):
                    return await c.message.answer("Выбери хотя бы один регион.")
                return await self._advance_to_networks(c.message.chat.id, c.from_user.id, p)
            if region not in REGION_COUNTRIES:
                return
            st = await self.state_get(c.from_user.id)
            if not st:
                return
            p = dict(st["payload"] or {})
            selected = list(p.get("_aud_regions") or [])
            selected = [x for x in selected if x != region] if region in selected else selected + [region]
            p["_aud_regions"] = selected
            countries = []
            for key in selected:
                countries.extend(REGION_COUNTRIES[key])
            p["countries"] = list(dict.fromkeys(countries))
            await self.state_set(c.from_user.id, "b:countries", p)
            items = list(REGION_LABELS.items())
            rows = []
            chosen = set(selected)
            for i in range(0, len(items), 2):
                rows.append(
                    [
                        (("✅ " if key in chosen else "▫️ ") + label, f"aud:r:{key}")
                        for key, label in items[i : i + 2]
                    ]
                )
            rows.append([("Готово →", "aud:r:done"), ("⬅️ Назад", "aud:back")])
            await self._edit_or_send(c, "<b>Выбери один или несколько регионов</b>", _kb(rows))

        @r.callback_query(F.data == "aud:countries")
        async def audience_country_regions(c: CallbackQuery):
            await c.answer()
            st = await self.state_get(c.from_user.id)
            p = dict(st["payload"] or {}) if st else {}
            if "ALL" in list(p.get("countries") or []):
                p["countries"] = []
                await self.state_set(c.from_user.id, "b:countries", p)
            items = list(REGION_LABELS.items())
            rows = []
            for i in range(0, len(items), 2):
                rows.append([(label, f"aud:cr:{key}:0") for key, label in items[i : i + 2]])
            rows.append([("⬅️ Назад", "aud:back")])
            await self._edit_or_send(c, "<b>Сначала выбери регион</b>\nТак быстрее найти страну.", _kb(rows))

        @r.callback_query(F.data.startswith("aud:cr:"))
        async def audience_country_region(c: CallbackQuery):
            await c.answer()
            _, _, region, page_raw = c.data.split(":", 3)
            if region not in REGION_COUNTRIES:
                return
            st = await self.state_get(c.from_user.id)
            p = dict(st["payload"] or {}) if st else {}
            p["_aud_country_region"] = region
            markup, page = self._audience_country_markup(p, region, int(page_raw))
            p["_aud_country_page"] = page
            p.pop("_aud_regions", None)
            await self.state_set(c.from_user.id, "b:countries", p)
            await self._edit_or_send(
                c,
                f"<b>{_safe(REGION_LABELS[region])}</b>\nМожно отметить несколько стран.",
                markup,
            )

        @r.callback_query(F.data.startswith("aud:c:"))
        async def audience_country_toggle(c: CallbackQuery):
            await c.answer()
            code = c.data.split(":", 2)[2]
            st = await self.state_get(c.from_user.id)
            if not st:
                return
            p = dict(st["payload"] or {})
            if code == "done":
                if not p.get("countries"):
                    return await c.message.answer("Выбери хотя бы одну страну.")
                return await self._advance_to_networks(c.message.chat.id, c.from_user.id, p)
            if code not in WORLD_COUNTRIES:
                return
            selected = [x for x in list(p.get("countries") or []) if x != "ALL"]
            selected = [x for x in selected if x != code] if code in selected else selected + [code]
            p["countries"] = selected
            p.pop("_aud_regions", None)
            region = p.get("_aud_country_region")
            page = int(p.get("_aud_country_page") or 0)
            await self.state_set(c.from_user.id, "b:countries", p)
            if region in REGION_COUNTRIES:
                markup, _ = self._audience_country_markup(p, region, page)
                await self._edit_or_send(
                    c,
                    f"<b>{_safe(REGION_LABELS[region])}</b>\nМожно отметить несколько стран.",
                    markup,
                )

        @r.callback_query(F.data == "aud:back")
        async def audience_back(c: CallbackQuery):
            await c.answer()
            st = await self.state_get(c.from_user.id)
            if not st:
                return
            p = dict(st["payload"] or {})
            await self._edit_or_send(
                c,
                "<b>Кому показываем публикацию?</b>\n\nМожно оставить все страны или сузить аудиторию.",
                self._countries_multi(p),
            )

        @r.callback_query(F.data == "b:countries:done")
        async def countries_done(c: CallbackQuery):
            await c.answer()
            st = await self.state_get(c.from_user.id)
            if not st:
                return
            await self._advance_to_networks(c.message.chat.id, c.from_user.id, dict(st["payload"] or {}))

        @r.callback_query(F.data == "b:networks:done")
        async def networks_done(c: CallbackQuery):
            await c.answer()
            st = await self.state_get(c.from_user.id)
            if not st:
                return
            p = dict(st["payload"] or {})
            if not p.get("networks"):
                return await c.message.answer("Выбери хотя бы одну сеть.")
            p["channels"] = {"dm": True, "targets": False}
            await self._show_delivery_picker(c.message.chat.id, c.from_user.id, p)

        @r.callback_query(F.data == "b:channels:done")
        async def channels_done(c: CallbackQuery):
            await c.answer()
            st = await self.state_get(c.from_user.id)
            if not st:
                return
            await self._advance_after_delivery(c.message.chat.id, c.from_user.id, dict(st["payload"] or {}))

        super()._register_handlers()


async def run_commission_bot_resilient(database_url: str) -> None:
    token = os.getenv("COMMISSION_BOT_TOKEN", "").strip()
    if not token:
        log.info("COMMISSION_BOT_TOKEN not set; commission bot disabled")
        return
    bootstrap = os.getenv("COMMISSION_BOOTSTRAP_CODE", "").strip()
    app = CommissionBotResilient(database_url, token, bootstrap)
    await app.run()
