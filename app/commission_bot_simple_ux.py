from __future__ import annotations

import html
import logging
import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from aiogram import F
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, KeyboardButton, Message, ReplyKeyboardMarkup

from app.commission_bot import TYPE_MAP, _kb
from app.commission_bot_hardened import CommissionBotHardened
from app.commission_bot_resilience import (
    _MONTHS,
    _TIME_PRESETS,
    _date_label,
    _local_now,
)
from app.commission_bot_ultimate import DEFAULT_TZ, TZ_LABELS, _localize, _safe

log = logging.getLogger(__name__)


class CommissionBotSimpleUX(CommissionBotHardened):
    """Progressive-disclosure UX: simple defaults first, power controls on demand."""

    def _quick_keyboard(self, role: str) -> ReplyKeyboardMarkup:
        if role in {"admin", "owner"}:
            rows = [
                [KeyboardButton(text="➕ Создать"), KeyboardButton(text="✅ Согласование")],
                [KeyboardButton(text="👥 Люди"), KeyboardButton(text="📊 Аналитика")],
                [KeyboardButton(text="⚙️ Ещё")],
            ]
        elif role == "editor":
            rows = [
                [KeyboardButton(text="➕ Создать"), KeyboardButton(text="👥 Люди")],
                [KeyboardButton(text="📅 События"), KeyboardButton(text="🎟 Мои заявки")],
                [KeyboardButton(text="⚙️ Ещё")],
            ]
        else:
            rows = [
                [KeyboardButton(text="📅 События"), KeyboardButton(text="🎟 Мои заявки")],
                [KeyboardButton(text="💬 Связаться"), KeyboardButton(text="👤 Профиль")],
                [KeyboardButton(text="⚙️ Ещё")],
            ]
        return ReplyKeyboardMarkup(
            keyboard=rows,
            resize_keyboard=True,
            is_persistent=True,
            input_field_placeholder="Что хочешь сделать?",
        )

    async def send_menu(self, chat_id: int, user, text: str = "Главное меню"):
        role = user["role"]
        lines = [f"<b>{html.escape(text)}</b>"]
        try:
            if role in {"admin", "owner"}:
                pending = await self.fetchrow("SELECT COUNT(*) n FROM broadcasts WHERE status='pending'")
                tickets = await self.fetchrow("SELECT COUNT(*) n FROM support_tickets WHERE status='open'")
                notes = []
                if pending and pending["n"]:
                    notes.append(f"на согласовании {pending['n']}")
                if tickets and tickets["n"]:
                    notes.append(f"обращений {tickets['n']}")
                if notes:
                    lines += ["", "Сейчас: " + " · ".join(notes)]
        except Exception:
            log.exception("simple menu counters")
        await self.bot.send_message(chat_id, "\n".join(lines), reply_markup=self._quick_keyboard(role))

    async def _show_people_hub(self, chat_id: int, user) -> None:
        if user["role"] not in {"editor", "admin", "owner"}:
            return await self._show_profile(chat_id, user)
        rows = [[("👥 Участники", "simple:people:participants"), ("📋 Регистрации", "simple:people:regs")]]
        if user["role"] in {"admin", "owner"}:
            rows.append([("💬 Обращения", "simple:people:support")])
        rows.append([("⬅️ Назад", "menu")])
        await self.bot.send_message(
            chat_id,
            "<b>👥 Люди</b>\n\nУчастники, регистрации и обращения — в одном месте.",
            reply_markup=_kb(rows),
        )

    async def _show_crm_hub(self, chat_id: int) -> None:
        stats = await self.fetchrow(
            """SELECT COUNT(*) total,
            COUNT(*) FILTER(WHERE activity_level IN ('active','very_active','core')) active,
            COUNT(*) FILTER(WHERE activity_level='inactive') inactive
            FROM users WHERE onboarding_complete=TRUE"""
        )
        await self.bot.send_message(
            chat_id,
            f"<b>👥 Участники</b>\n\n"
            f"Всего: <b>{stats['total']}</b> · активных: <b>{stats['active']}</b> · неактивных: {stats['inactive']}\n\n"
            "Найди человека или открой готовую выборку.",
            reply_markup=_kb(
                [
                    [("🔎 Найти", "crm:search")],
                    [("⚡ Активные", "crm:list:active"), ("😴 Неактивные", "crm:list:inactive")],
                    [("⬅️ К людям", "menu")],
                ]
            ),
        )

    async def _show_more_hub(self, chat_id: int, user) -> None:
        role = user["role"]
        rows = [
            [("📅 События", "simple:more:events"), ("🎟 Мои заявки", "simple:more:regs")],
            [("👤 Профиль", "simple:more:profile"), ("❓ Помощь", "simple:more:help")],
        ]
        if role in {"admin", "owner"}:
            rows.insert(0, [("📣 Площадки", "simple:more:targets"), ("🎯 Рассылки", "simple:more:segments")])
            if role == "owner":
                rows.insert(1, [("👥 Команда", "simple:more:team")])
        rows.append([("⬅️ Главное меню", "menu")])
        await self.bot.send_message(
            chat_id,
            "<b>⚙️ Ещё</b>\n\nЗдесь то, что нужно реже. Главное меню оставили коротким.",
            reply_markup=_kb(rows),
        )

    async def _show_event_date_picker(self, chat_id: int, uid: int, p: dict) -> None:
        user = await self.fetchrow("SELECT * FROM users WHERE telegram_id=$1", uid)
        tz_name = p.get("event_timezone") or (user["timezone_name"] if user else None) or DEFAULT_TZ
        p["event_timezone"] = tz_name
        await self.state_set(uid, "b:event_at", p)
        today = _local_now(tz_name).date()
        tomorrow = today + timedelta(days=1)
        rows = [
            [
                (f"Сегодня · {today.day} {_MONTHS[today.month - 1]}", f"dt:d:{today.strftime('%Y%m%d')}"),
                (f"Завтра · {tomorrow.day} {_MONTHS[tomorrow.month - 1]}", f"dt:d:{tomorrow.strftime('%Y%m%d')}"),
            ],
            [("📅 Выбрать другую дату", "simple:date:more")],
            [("Без даты", "dt:none")],
            [("⬅️ Назад", "nav:back"), ("✖️ Отмена", "nav:cancel")],
        ]
        await self.bot.send_message(
            chat_id,
            "<b>Когда?</b>\n\n"
            f"Время покажу по <b>{_safe(TZ_LABELS.get(tz_name, tz_name))}</b>. "
            "Если это просто новость — выбери «Без даты».",
            reply_markup=_kb(rows),
        )

    async def _show_full_date_picker(self, chat_id: int, uid: int, p: dict) -> None:
        user = await self.fetchrow("SELECT * FROM users WHERE telegram_id=$1", uid)
        tz_name = p.get("event_timezone") or (user["timezone_name"] if user else None) or DEFAULT_TZ
        today = _local_now(tz_name).date()
        choices = []
        for offset in range(2, 9):
            day = today + timedelta(days=offset)
            choices.append((_date_label(day, today), f"dt:d:{day.strftime('%Y%m%d')}"))
        rows = [choices[i : i + 2] for i in range(0, len(choices), 2)]
        rows += [[("✍️ Ввести вручную", "dt:manual")], [("⬅️ Назад", "dt:dates")]]
        await self.bot.send_message(chat_id, "<b>Выбери дату</b>", reply_markup=_kb(rows))

    async def _show_event_time_picker(self, chat_id: int, uid: int, p: dict, chosen: date) -> None:
        p["_chosen_date"] = chosen.isoformat()
        await self.state_set(uid, "b:event_at", p)
        preferred = ("12:00", "15:00", "18:00", "19:00", "20:00")
        rows = [
            [(value, f"dt:t:{value.replace(':', '')}") for value in preferred[:2]],
            [(value, f"dt:t:{value.replace(':', '')}") for value in preferred[2:4]],
            [(preferred[4], f"dt:t:{preferred[4].replace(':', '')}"), ("Другое", "dt:manual")],
            [("⬅️ К датам", "dt:dates")],
        ]
        await self.bot.send_message(
            chat_id,
            f"<b>{chosen.day} {_MONTHS[chosen.month - 1]} · во сколько?</b>",
            reply_markup=_kb(rows),
        )

    async def _start_audience(self, chat_id: int, uid: int, p: dict) -> None:
        if not p.get("countries"):
            p["countries"] = ["ALL"]
        p["networks"] = p.get("networks") or ["commission"]
        await self.state_set(uid, "b:countries", p)
        await self.bot.send_message(
            chat_id,
            "<b>Кому отправляем?</b>\n\n"
            "По умолчанию — всем странам в сети Комиссии. "
            "Если нужна точная выборка, открой настройку аудитории.",
            reply_markup=_kb(
                [
                    [("Продолжить · 🌍 все страны", "simple:aud:continue")],
                    [("🎯 Настроить аудиторию", "simple:aud:advanced")],
                    [("⬅️ Назад", "nav:back"), ("✖️ Отмена", "nav:cancel")],
                ]
            ),
        )

    async def _advance_to_networks(self, chat_id: int, uid: int, p: dict) -> None:
        if not p.get("countries"):
            return await self.bot.send_message(chat_id, "Выбери хотя бы один регион или страну.")
        p["networks"] = p.get("networks") or ["commission"]
        await self._show_delivery_picker(chat_id, uid, p)

    async def _show_delivery_picker(self, chat_id: int, uid: int, p: dict) -> None:
        p["networks"] = p.get("networks") or ["commission"]
        # Count both independently so the screen only offers routes that actually work.
        probe = dict(p)
        probe["channels"] = {"dm": True, "targets": True}
        users_count, targets_count = await self._estimate_wizard_delivery(probe)
        await self.state_set(uid, "b:channels", p)

        rows = []
        if users_count:
            rows.append([(f"👤 Участникам · {users_count}", "simple:delivery:dm")])
        if targets_count:
            rows.append([(f"📣 В площадки · {targets_count}", "simple:delivery:targets")])
        if users_count and targets_count:
            rows.append([(f"✨ Везде · {users_count + targets_count}", "simple:delivery:both")])
        if not users_count and not targets_count:
            rows.append([("📣 Подключить площадку", "simple:more:targets")])
        rows.append([("⚙️ Точная настройка", "simple:delivery:advanced")])
        rows.append([("⬅️ Назад", "nav:back"), ("✖️ Отмена", "nav:cancel")])

        if users_count or targets_count:
            text = "<b>Куда отправляем?</b>\n\nВыбери один вариант — бот уже посчитал доступных получателей."
        else:
            text = (
                "<b>Пока отправлять некуда</b>\n\n"
                "Нет доступных участников и подтверждённых площадок для этой аудитории. "
                "Можно подключить площадку или изменить аудиторию."
            )
        await self.bot.send_message(chat_id, text, reply_markup=_kb(rows))

    def _audience_summary(self, p: dict) -> str:
        countries = list(p.get("countries") or ["ALL"])
        if "ALL" in countries:
            return "Все страны"
        return f"{len(countries)} стран"

    def _network_summary(self, p: dict) -> str:
        labels = {"commission": "Комиссия", "mds": "МДС", "partner": "Партнёры"}
        return ", ".join(labels.get(x, x) for x in (p.get("networks") or ["commission"]))

    def _delivery_summary(self, p: dict, users_count: int, targets_count: int) -> str:
        channels = p.get("channels") or {}
        parts = []
        if channels.get("dm"):
            parts.append(f"лично {users_count}")
        if channels.get("targets"):
            parts.append(f"площадки {targets_count}")
        return " · ".join(parts) or "—"

    def _simple_preview(self, p: dict, users_count: int, targets_count: int) -> str:
        event_at = "Без даты"
        if p.get("event_at"):
            try:
                dt = datetime.fromisoformat(p["event_at"])
                event_at = _localize(dt, p.get("event_timezone") or DEFAULT_TZ)
            except Exception:
                event_at = str(p.get("event_at"))
        reg_labels = {"internal": "В боте", "external": "По ссылке", "none": "Не нужна"}
        reminders = p.get("reminders") or []
        reminder_text = "нет"
        if p.get("event_at") and reminders:
            names = {1440: "24 ч", 60: "1 ч", 180: "3 ч", 4320: "3 дня", 10080: "7 дней"}
            reminder_text = ", ".join(names.get(x, f"{x} мин") for x in reminders)
        return (
            "<b>Готово к согласованию</b>\n\n"
            f"<b>{html.escape(str(p.get('title') or 'Без названия'))}</b>\n"
            f"{html.escape(str(p.get('description') or ''))}\n\n"
            f"📌 {html.escape(TYPE_MAP.get(p.get('content_type'), str(p.get('content_type') or 'Публикация')))}\n"
            f"🕒 {html.escape(event_at)}\n"
            f"🎟 Регистрация: {reg_labels.get(p.get('registration_mode', 'none'), 'Не нужна')}\n"
            f"🌍 Аудитория: {html.escape(self._audience_summary(p))}\n"
            f"🔗 Сеть: {html.escape(self._network_summary(p))}\n"
            f"📨 Доставка: {html.escape(self._delivery_summary(p, users_count, targets_count))}\n"
            f"🔔 Напоминания: {html.escape(reminder_text)}"
        )

    async def _advance_after_delivery(self, chat_id: int, uid: int, p: dict) -> None:
        channels = p.get("channels") or {}
        if not channels.get("dm") and not channels.get("targets"):
            return await self._show_delivery_picker(chat_id, uid, p)
        users_count, targets_count = await self._estimate_wizard_delivery(p)
        if users_count + targets_count == 0:
            return await self._show_delivery_picker(chat_id, uid, p)

        # Best-practice defaults for online events: one day and one hour.
        # Advanced users can still change them before submission.
        if p.get("event_at") and "reminders" not in p:
            p["reminders"] = [1440, 60]
        if not p.get("event_at"):
            p["reminders"] = []

        p["_delivery_estimate"] = {"users": users_count, "targets": targets_count}
        await self.state_set(uid, "b:preview", p)
        await self.bot.send_message(
            chat_id,
            self._simple_preview(p, users_count, targets_count),
            reply_markup=_kb(
                [
                    [("✅ Отправить на согласование", "b:submit")],
                    [("👁 Тест себе", "simple:preview:test"), ("✏️ Изменить", "simple:preview:edit")],
                    [("✖️ Отмена", "nav:cancel")],
                ]
            ),
        )

    async def _show_preview_edit(self, chat_id: int, uid: int, p: dict) -> None:
        await self.bot.send_message(
            chat_id,
            "<b>Что изменить?</b>",
            reply_markup=_kb(
                [
                    [("🌍 Аудитория", "simple:edit:aud"), ("📨 Доставка", "simple:edit:delivery")],
                    [("🔗 Сети", "simple:edit:networks"), ("🔔 Напоминания", "simple:edit:reminders")],
                    [("⬅️ К проверке", "simple:edit:back")],
                ]
            ),
        )

    def _register_handlers(self):
        r = self.router

        @r.message(F.chat.type == ChatType.PRIVATE)
        async def simple_main_buttons(m: Message):
            text = (m.text or "").strip()
            if text not in {"👥 Люди", "📊 Аналитика", "⚙️ Ещё", "💬 Связаться"}:
                raise SkipHandler
            user = await self.ensure_user(m.from_user)
            st = await self.state_get(user["telegram_id"])
            if st:
                state = str(st["state"])
                if state.startswith("onboard:") and not user["onboarding_complete"]:
                    return await m.answer("Сначала закончи регистрацию профиля — осталось совсем немного.")
                await self.state_clear(user["telegram_id"])
            if text == "👥 Люди":
                return await self._show_people_hub(m.chat.id, user)
            if text == "📊 Аналитика":
                return await self._show_analytics(m.chat.id, user)
            if text == "💬 Связаться":
                return await self._show_contact(m.chat.id)
            return await self._show_more_hub(m.chat.id, user)

        @r.callback_query(F.data == "simple:people:participants")
        async def simple_people_participants(c: CallbackQuery):
            await c.answer()
            user = await self.ensure_user(c.from_user)
            if user["role"] not in {"editor", "admin", "owner"}:
                return
            await self._show_crm_hub(c.message.chat.id)

        @r.callback_query(F.data == "simple:people:regs")
        async def simple_people_regs(c: CallbackQuery):
            await c.answer()
            user = await self.ensure_user(c.from_user)
            await self._show_regadmin(c.message.chat.id, user)

        @r.callback_query(F.data == "simple:people:support")
        async def simple_people_support(c: CallbackQuery):
            await c.answer()
            user = await self.ensure_user(c.from_user)
            await self._show_support_inbox(c.message.chat.id, user)

        @r.callback_query(F.data.startswith("simple:more:"))
        async def simple_more(c: CallbackQuery):
            await c.answer()
            user = await self.ensure_user(c.from_user)
            action = c.data.split(":", 2)[2]
            if action == "events":
                return await self._show_events(c.message.chat.id)
            if action == "regs":
                return await self._show_my_regs(c.message.chat.id, user["telegram_id"])
            if action == "profile":
                return await self._show_profile(c.message.chat.id, user)
            if action == "help":
                return await self._show_help(c.message.chat.id, user)
            if action == "targets":
                return await self._show_targets(c.message.chat.id, user)
            if action == "segments":
                return await c.message.answer("Точные рассылки и сохранённые сегменты.", reply_markup=_kb([[("🎯 Открыть сегменты", "seg:menu")]]))
            if action == "team":
                return await self._show_team(c.message.chat.id, user)

        @r.callback_query(F.data == "simple:date:more")
        async def simple_date_more(c: CallbackQuery):
            await c.answer()
            st = await self.state_get(c.from_user.id)
            if not st:
                return
            await self._show_full_date_picker(c.message.chat.id, c.from_user.id, dict(st["payload"] or {}))

        @r.callback_query(F.data == "simple:aud:continue")
        async def simple_audience_continue(c: CallbackQuery):
            await c.answer()
            st = await self.state_get(c.from_user.id)
            if not st:
                return
            p = dict(st["payload"] or {})
            p["countries"] = ["ALL"]
            p["networks"] = ["commission"]
            await self._show_delivery_picker(c.message.chat.id, c.from_user.id, p)

        @r.callback_query(F.data == "simple:aud:advanced")
        async def simple_audience_advanced(c: CallbackQuery):
            await c.answer()
            st = await self.state_get(c.from_user.id)
            if not st:
                return
            p = dict(st["payload"] or {})
            await self.state_set(c.from_user.id, "b:countries", p)
            await c.message.answer(
                "<b>Точная аудитория</b>\n\nВыбери регионы или конкретные страны.",
                reply_markup=self._countries_multi(p),
            )

        @r.callback_query(F.data.startswith("simple:delivery:"))
        async def simple_delivery(c: CallbackQuery):
            await c.answer()
            st = await self.state_get(c.from_user.id)
            if not st:
                return
            p = dict(st["payload"] or {})
            action = c.data.split(":", 2)[2]
            if action == "advanced":
                p["networks"] = p.get("networks") or ["commission"]
                await self.state_set(c.from_user.id, "b:networks", p)
                return await c.message.answer(
                    "<b>Точная настройка</b>\n\n"
                    "Комиссия включена по умолчанию. МДС и партнёров добавляй только когда они действительно участвуют в этой рассылке.",
                    reply_markup=self._networks(p),
                )
            if action == "dm":
                p["channels"] = {"dm": True, "targets": False}
            elif action == "targets":
                p["channels"] = {"dm": False, "targets": True}
            elif action == "both":
                p["channels"] = {"dm": True, "targets": True}
            else:
                return
            await self._advance_after_delivery(c.message.chat.id, c.from_user.id, p)

        @r.callback_query(F.data == "simple:preview:test")
        async def simple_preview_test(c: CallbackQuery):
            await c.answer("Тест отправлен тебе")
            st = await self.state_get(c.from_user.id)
            if not st:
                return
            p = dict(st["payload"] or {})
            est = p.get("_delivery_estimate") or {}
            await c.message.answer(
                "<b>👁 Тестовая копия</b>\n\n" + self._simple_preview(
                    p, int(est.get("users") or 0), int(est.get("targets") or 0)
                )
            )

        @r.callback_query(F.data == "simple:preview:edit")
        async def simple_preview_edit(c: CallbackQuery):
            await c.answer()
            st = await self.state_get(c.from_user.id)
            if st:
                await self._show_preview_edit(c.message.chat.id, c.from_user.id, dict(st["payload"] or {}))

        @r.callback_query(F.data.startswith("simple:edit:"))
        async def simple_edit(c: CallbackQuery):
            await c.answer()
            st = await self.state_get(c.from_user.id)
            if not st:
                return
            p = dict(st["payload"] or {})
            action = c.data.split(":", 2)[2]
            if action == "aud":
                return await self._start_audience(c.message.chat.id, c.from_user.id, p)
            if action == "delivery":
                return await self._show_delivery_picker(c.message.chat.id, c.from_user.id, p)
            if action == "networks":
                await self.state_set(c.from_user.id, "b:networks", p)
                return await c.message.answer("<b>Сети распространения</b>", reply_markup=self._networks(p))
            if action == "reminders":
                if not p.get("event_at"):
                    return await c.message.answer("У публикации без даты напоминания не нужны.")
                await self.state_set(c.from_user.id, "b:reminders", p)
                return await c.message.answer("<b>Напоминания</b>", reply_markup=self._reminders(p))
            if action == "back":
                est = p.get("_delivery_estimate") or {}
                await self.state_set(c.from_user.id, "b:preview", p)
                return await c.message.answer(
                    self._simple_preview(p, int(est.get("users") or 0), int(est.get("targets") or 0)),
                    reply_markup=_kb(
                        [
                            [("✅ Отправить на согласование", "b:submit")],
                            [("👁 Тест себе", "simple:preview:test"), ("✏️ Изменить", "simple:preview:edit")],
                            [("✖️ Отмена", "nav:cancel")],
                        ]
                    ),
                )

        super()._register_handlers()


async def run_commission_bot_simple_ux(database_url: str) -> None:
    token = os.getenv("COMMISSION_BOT_TOKEN", "").strip()
    if not token:
        log.info("COMMISSION_BOT_TOKEN not set; commission bot disabled")
        return
    bootstrap = os.getenv("COMMISSION_BOOTSTRAP_CODE", "").strip()
    app = CommissionBotSimpleUX(database_url, token, bootstrap)
    await app.run()
