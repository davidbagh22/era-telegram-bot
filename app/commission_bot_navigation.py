from __future__ import annotations

import json
import logging
import os
from typing import Any

from aiogram import F
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from app.commission_bot import CONTENT_TYPES, COUNTRY_MAP, _kb
from app.commission_bot_plus_base import _role_label
from app.commission_bot_ultimate import (
    DEFAULT_TZ,
    TZ_LABELS,
    CommissionBotUltimate,
    _localize,
    _safe,
)

log = logging.getLogger(__name__)

QUICK_BUTTONS = {
    "📅 Мероприятия",
    "🎟 Мои регистрации",
    "👤 Профиль",
    "🔔 Уведомления",
    "➕ Создать",
    "📋 Регистрации",
    "✅ Согласование",
    "📣 Чаты и каналы",
    "📊 Аналитика",
    "👥 Команда",
    "❓ Что делать",
    "🏠 Меню",
    "⬅️ Назад",
    "✖️ Отмена",
}


class CommissionBotNavigation(CommissionBotUltimate):
    def _quick_keyboard(self, role: str) -> ReplyKeyboardMarkup:
        rows: list[list[KeyboardButton]] = []
        if role in {"editor", "admin", "owner"}:
            rows.append([KeyboardButton(text="➕ Создать"), KeyboardButton(text="📋 Регистрации")])
        if role in {"admin", "owner"}:
            rows.append([KeyboardButton(text="✅ Согласование"), KeyboardButton(text="📣 Чаты и каналы")])
            rows.append([KeyboardButton(text="📊 Аналитика")])
        if role == "owner":
            rows[-1].append(KeyboardButton(text="👥 Команда"))
        rows.extend(
            [
                [KeyboardButton(text="📅 Мероприятия"), KeyboardButton(text="🎟 Мои регистрации")],
                [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="🔔 Уведомления")],
                [KeyboardButton(text="❓ Что делать"), KeyboardButton(text="🏠 Меню")],
                [KeyboardButton(text="⬅️ Назад"), KeyboardButton(text="✖️ Отмена")],
            ]
        )
        return ReplyKeyboardMarkup(
            keyboard=rows,
            resize_keyboard=True,
            is_persistent=True,
            input_field_placeholder="Выберите действие или напишите сообщение",
        )

    async def send_menu(self, chat_id: int, user, text: str = "Выберите действие:"):
        await super().send_menu(chat_id, user, text)
        await self.bot.send_message(
            chat_id,
            "⌨️ Быстрый доступ включён — основные кнопки теперь всегда под строкой ввода.",
            reply_markup=self._quick_keyboard(user["role"]),
        )

    async def state_set(self, uid: int, state: str, payload: dict[str, Any]) -> None:
        data = dict(payload or {})
        if state.startswith("b:"):
            current = await self.state_get(uid)
            if current and str(current["state"]).startswith("b:"):
                old_state = str(current["state"])
                old_payload = dict(current["payload"] or {})
                history = list(old_payload.get("_nav_history", []))
                if old_state != state:
                    snapshot = {k: v for k, v in old_payload.items() if k != "_nav_history"}
                    history.append({"state": old_state, "payload": snapshot})
                    data["_nav_history"] = history[-25:]
                elif "_nav_history" not in data:
                    data["_nav_history"] = history
        await super().state_set(uid, state, data)

    def _with_nav(self, markup: InlineKeyboardMarkup | None = None) -> InlineKeyboardMarkup:
        rows = list(markup.inline_keyboard) if markup else []
        rows.append(
            [
                *[button for button in _kb([[('⬅️ Назад', 'nav:back'), ('✖️ Отмена', 'nav:cancel')]]).inline_keyboard[0]],
            ]
        )
        return InlineKeyboardMarkup(inline_keyboard=rows)

    async def _render_wizard_step(self, chat_id: int, uid: int, state: str, payload: dict[str, Any]) -> None:
        user = await self.fetchrow("SELECT * FROM users WHERE telegram_id=$1", uid)
        tz_name = payload.get("event_timezone") or (user["timezone_name"] if user else DEFAULT_TZ) or DEFAULT_TZ
        tz_label = TZ_LABELS.get(tz_name, tz_name)

        text = "Вернулись к предыдущему шагу."
        markup: InlineKeyboardMarkup | None = None

        if state == "b:type":
            text = "<b>Создание публикации</b> · тип\n\nВыберите тип публикации:"
            markup = _kb([[(label, f"b:type:{code}")] for code, label in CONTENT_TYPES])
        elif state == "b:title":
            text = "<b>Создание публикации</b> · название\n\nОтправьте название."
        elif state == "b:description":
            text = "<b>Создание публикации</b> · описание\n\nОтправьте описание."
        elif state == "b:media":
            text = "<b>Создание публикации</b> · афиша\n\nПришлите фото или отправьте <code>/skip</code>."
        elif state == "b:event_at":
            text = (
                "<b>Создание публикации</b> · дата и время\n\n"
                f"Часовой пояс: <b>{_safe(tz_label)}</b>\n"
                "Введите, например: <code>15.10.2026 19:00</code>\nИли <code>/skip</code>."
            )
        elif state == "b:format":
            text = "<b>Создание публикации</b> · формат\n\nВыберите формат мероприятия:"
            markup = _kb(
                [
                    [("🏛 Очно", "b:format:offline"), ("💻 Онлайн", "b:format:online")],
                    [("🔀 Гибрид", "b:format:hybrid")],
                ]
            )
        elif state == "b:location":
            fmt = payload.get("event_format")
            hint = "ссылку на трансляцию" if fmt == "online" else "адрес / площадку / ссылку"
            text = f"<b>Создание публикации</b> · место\n\nУкажите {hint} или <code>/skip</code>."
        elif state == "b:regmode":
            text = "<b>Создание публикации</b> · регистрация\n\nВыберите вариант:"
            markup = _kb(
                [
                    [("✅ Внутри бота", "b:reg:internal")],
                    [("🔗 Внешняя ссылка", "b:reg:external")],
                    [("Без регистрации", "b:reg:none")],
                ]
            )
        elif state == "b:regform":
            text = "<b>Создание публикации</b> · анкета\n\nКак регистрировать участников?"
            markup = _kb(
                [
                    [("⚡ Быстро — 1 клик", "b:regform:quick")],
                    [("📝 С анкетой участника", "b:regform:standard")],
                ]
            )
        elif state == "b:customq_choice":
            text = "<b>Создание публикации</b> · вопросы\n\nДобавить вопросы именно для этого мероприятия?"
            markup = _kb(
                [
                    [("➕ Да, добавить", "b:customq:add")],
                    [("Без дополнительных вопросов", "b:customq:none")],
                ]
            )
        elif state == "b:customq_text":
            text = "<b>Создание публикации</b> · вопросы\n\nОтправьте до 5 вопросов, каждый с новой строки."
        elif state == "b:capacity":
            text = "<b>Создание публикации</b> · места\n\nВведите количество мест или <code>/skip</code>."
        elif state == "b:regurl":
            text = "<b>Создание публикации</b> · ссылка\n\nОтправьте ссылку регистрации вида https://..."
        elif state == "b:deadline":
            text = (
                "<b>Создание публикации</b> · дедлайн\n\n"
                f"Часовой пояс: <b>{_safe(tz_label)}</b>\n"
                "Введите, например: <code>14.10.2026 20:00</code>\nИли <code>/skip</code>."
            )
        elif state == "b:countries":
            text = "<b>Создание публикации</b> · страны\n\nВыберите аудиторию по странам:"
            markup = self._countries_multi(payload)
        elif state == "b:networks":
            text = "<b>Создание публикации</b> · сети\n\nВыберите сети распространения:"
            markup = self._networks(payload)
        elif state == "b:channels":
            text = "<b>Создание публикации</b> · доставка\n\nВыберите каналы доставки:"
            markup = self._channels(payload)
        elif state == "b:reminders":
            text = "<b>Создание публикации</b> · напоминания\n\nВыберите напоминания:"
            markup = self._reminders(payload)
        elif state == "b:preview":
            text = self._preview(payload)
            markup = _kb([[('✅ Отправить на согласование', 'b:submit')]])

        await self.bot.send_message(chat_id, text, reply_markup=self._with_nav(markup))

    async def _go_back(self, chat_id: int, uid: int) -> None:
        st = await self.state_get(uid)
        if not st or not str(st["state"]).startswith("b:"):
            user = await self.ensure_user(type("U", (), {"id": uid, "username": None, "first_name": None, "last_name": None})())
            await self.send_menu(chat_id, user, "Вы уже в начале.")
            return

        payload = dict(st["payload"] or {})
        history = list(payload.get("_nav_history", []))
        if not history:
            await self.state_clear(uid)
            user = await self.fetchrow("SELECT * FROM users WHERE telegram_id=$1", uid)
            await self.send_menu(chat_id, user, "Создание публикации закрыто.")
            return

        previous = history.pop()
        restored = dict(previous.get("payload") or {})
        restored["_nav_history"] = history
        await super().state_set(uid, str(previous["state"]), restored)
        await self._render_wizard_step(chat_id, uid, str(previous["state"]), restored)

    async def _show_help(self, chat_id: int, user) -> None:
        role = user["role"]
        text = (
            "<b>Что делать в этом боте?</b>\n\n"
            "<b>Участнику</b>\n"
            "• 📅 Мероприятия — посмотреть актуальные события.\n"
            "• 🎟 Мои регистрации — проверить заявки и статус.\n"
            "• 👤 Профиль — страна, часовой пояс и данные анкеты.\n"
            "• 🔔 Уведомления — включить или выключить общие личные рассылки.\n"
        )
        if role in {"editor", "admin", "owner"}:
            text += (
                "\n<b>Модератору</b>\n"
                "• ➕ Создать — подготовить публикацию или мероприятие.\n"
                "• 📋 Регистрации — участники, QR check-in, посещаемость и CSV.\n"
            )
        if role in {"admin", "owner"}:
            text += (
                "\n<b>Администратору</b>\n"
                "• ✅ Согласование — проверить и запустить публикацию.\n"
                "• 📣 Чаты и каналы — подключить площадки для рассылок.\n"
                "• 📊 Аналитика — пользователи, доставки, регистрации и посещаемость.\n"
            )
        if role == "owner":
            text += "\n<b>Владельцу</b>\n• 👥 Команда — приглашать администраторов и модераторов и менять роли.\n"

        text += (
            "\n<b>Во время заполнения</b>\n"
            "⬅️ Назад — вернуться ровно на предыдущий шаг.\n"
            "✖️ Отмена — закрыть текущий сценарий без публикации.\n"
            "🏠 Меню — выйти из сценария и открыть главное меню.\n\n"
            "Если не понимаете, что делать на текущем шаге, нажмите <b>❓ Что делать</b>."
        )
        await self.bot.send_message(chat_id, text, reply_markup=self._quick_keyboard(role))

    async def _show_attach_help(self, chat_id: int, user, include_targets: bool = True) -> None:
        text = (
            "<b>Как подключить чат или канал</b>\n\n"
            "<b>Группа / супергруппа</b>\n"
            "1. Откройте нужную группу.\n"
            "2. Добавьте <b>@MVKSRS_bot</b>.\n"
            "3. Назначьте бота администратором. Это важно: без статуса администратора бот не будет использовать чат для рассылок.\n\n"
            "<b>Telegram-канал</b>\n"
            "1. Откройте канал → Управление каналом → Администраторы.\n"
            "2. Добавьте <b>@MVKSRS_bot</b> как администратора.\n"
            "3. Разрешите минимум <b>публикацию сообщений</b>. Для корректного обновления опубликованных материалов также лучше разрешить <b>редактирование сообщений</b>.\n\n"
            "<b>После добавления</b>\n"
            "4. Вернитесь сюда в раздел «📣 Чаты и каналы».\n"
            "5. Новый чат/канал появится со статусом 🟡.\n"
            "6. Откройте его, выберите сеть: Комиссия / МДС / Партнёр, укажите страну или «Международный» и нажмите «✅ Подтвердить».\n"
            "7. После подтверждения статус станет 🟢 и площадку можно выбирать для рассылок.\n\n"
            "Если площадка не появилась, удалите бота и добавьте его снова либо снимите/верните права администратора — Telegram пришлёт боту новое событие подключения."
        )
        markup = None
        if include_targets and user["role"] in {"admin", "owner"}:
            markup = _kb([[('📣 Открыть список чатов и каналов', 'targets:list')], [('⬅️ Меню', 'menu')]])
        await self.bot.send_message(chat_id, text, reply_markup=markup)

    async def _show_events(self, chat_id: int) -> None:
        rows = await self.fetch(
            "SELECT * FROM broadcasts WHERE status='published' AND event_at IS NOT NULL AND event_at>NOW() ORDER BY event_at LIMIT 10"
        )
        if not rows:
            await self.bot.send_message(chat_id, "Ближайших мероприятий пока нет.")
            return
        buttons = []
        for b in rows:
            label = f"{_localize(b['event_at'], b['event_timezone'])} · {b['title']}"[:60]
            buttons.append([(label, f"event:{b['id']}")])
        await self.bot.send_message(chat_id, "<b>Ближайшие мероприятия</b>", reply_markup=_kb(buttons))

    async def _show_my_regs(self, chat_id: int, uid: int) -> None:
        rows = await self.fetch(
            """SELECT r.status,b.* FROM registrations r JOIN broadcasts b ON b.id=r.broadcast_id
            WHERE r.telegram_id=$1 AND r.status<>'cancelled'
            ORDER BY b.event_at NULLS LAST,b.id DESC LIMIT 20""",
            uid,
        )
        if not rows:
            await self.bot.send_message(chat_id, "У вас пока нет активных регистраций.")
            return
        buttons = []
        for b in rows:
            icon = "⏳" if b["status"] == "waitlist" else "✅"
            buttons.append([(f"{icon} {b['title']}"[:60], f"event:{b['id']}")])
        await self.bot.send_message(chat_id, "<b>Мои регистрации</b>", reply_markup=_kb(buttons))

    async def _show_profile(self, chat_id: int, user) -> None:
        name = " ".join(v for v in [user["first_name"], user["last_name"]] if v).strip()
        text = (
            f"<b>Профиль</b>\n\n{_safe(name)}\n"
            f"Страна: {_safe(user['country_name'] or 'не выбрана')}\n"
            f"Часовой пояс: {_safe(TZ_LABELS.get(user['timezone_name'], user['timezone_name']))}\n"
            f"Роль: <b>{_role_label(user['role'])}</b>\n"
            f"Общие рассылки: {'✅' if user['telegram_opt_in'] else '❌'}\n"
            f"Анкета участника: {'✅' if user['participant_profile_complete'] else '—'}"
        )
        await self.bot.send_message(
            chat_id,
            text,
            reply_markup=_kb(
                [
                    [('🌍 Изменить страну', 'profile:country'), ('🕒 Часовой пояс', 'profile:tz')],
                    [('🗑 Удалить мои данные', 'privacy:delete')],
                    [('⬅️ Меню', 'menu')],
                ]
            ),
        )

    async def _show_notifications(self, chat_id: int, user) -> None:
        await self.bot.send_message(
            chat_id,
            f"Общие личные Telegram-рассылки: {'✅ включены' if user['telegram_opt_in'] else '❌ выключены'}",
            reply_markup=_kb([[('Выключить' if user['telegram_opt_in'] else 'Включить', 'notify:toggle')], [('⬅️ Меню', 'menu')]]),
        )

    async def _show_regadmin(self, chat_id: int, user) -> None:
        if user["role"] not in {"editor", "admin", "owner"}:
            await self.bot.send_message(chat_id, "Этот раздел доступен команде бота.")
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
            await self.bot.send_message(chat_id, "Внутренних регистраций пока нет.")
            return
        buttons = []
        for b in rows:
            cap = f"/{b['capacity']}" if b["capacity"] else ""
            buttons.append(
                [(f"#{b['id']} · {b['registered']}{cap} · ⏳{b['waitlist']} · {b['title']}"[:60], f"regadmin:event:{b['id']}")]
            )
        await self.bot.send_message(chat_id, "<b>Регистрации участников</b>", reply_markup=_kb(buttons))

    async def _show_reviews(self, chat_id: int, user) -> None:
        if user["role"] not in {"admin", "owner"}:
            await self.bot.send_message(chat_id, "Согласование доступно администратору и владельцу.")
            return
        rows = await self.fetch("SELECT * FROM broadcasts WHERE status='pending' ORDER BY submitted_at,id LIMIT 20")
        if not rows:
            await self.bot.send_message(chat_id, "На согласовании сейчас ничего нет ✅")
            return
        await self.bot.send_message(
            chat_id,
            "<b>На согласовании</b>",
            reply_markup=_kb([[(f"#{b['id']} · {b['title']}"[:60], f"review:{b['id']}")] for b in rows]),
        )

    async def _show_targets(self, chat_id: int, user) -> None:
        if user["role"] not in {"admin", "owner"}:
            await self.bot.send_message(chat_id, "Подключение чатов и каналов доступно администратору и владельцу.")
            return
        rows = await self.fetch(
            "SELECT * FROM targets ORDER BY CASE status WHEN 'pending' THEN 0 WHEN 'approved' THEN 1 ELSE 2 END,updated_at DESC LIMIT 30"
        )
        buttons = [[('➕ Как подключить чат/канал', 'nav:attachhelp')]]
        for target in rows:
            icon = "🟡" if target["status"] == "pending" else "🟢" if target["status"] == "approved" else "⚫"
            buttons.append([(f"{icon} {target['title']}"[:60], f"target:{target['chat_id']}")])
        text = "<b>Чаты и каналы</b>\n\n🟡 ждёт подтверждения · 🟢 подключён · ⚫ отключён"
        if not rows:
            text += "\n\nПока ничего не подключено. Нажмите «Как подключить чат/канал»."
        await self.bot.send_message(chat_id, text, reply_markup=_kb(buttons + [[('⬅️ Меню', 'menu')]]))

    async def _show_analytics(self, chat_id: int, user) -> None:
        if user["role"] not in {"admin", "owner"}:
            await self.bot.send_message(chat_id, "Аналитика доступна администратору и владельцу.")
            return
        s = await self.fetchrow(
            """SELECT
              (SELECT COUNT(*) FROM users WHERE onboarding_complete) users,
              (SELECT COUNT(*) FROM users WHERE role IN ('owner','admin','editor')) staff,
              (SELECT COUNT(*) FROM targets WHERE status='approved') targets,
              (SELECT COUNT(*) FROM broadcasts WHERE status='published') published,
              (SELECT COUNT(*) FROM broadcasts WHERE status='scheduled') scheduled,
              (SELECT COUNT(*) FROM registrations WHERE status IN ('registered','attended')) regs,
              (SELECT COUNT(*) FROM registrations WHERE status='attended') attended,
              (SELECT COUNT(*) FROM deliveries WHERE status='sent') sent,
              (SELECT COUNT(*) FROM deliveries WHERE status='failed') failed"""
        )
        fail_rate = round((s["failed"] or 0) * 100 / max((s["sent"] or 0) + (s["failed"] or 0), 1), 1)
        attendance = round((s["attended"] or 0) * 100 / max(s["regs"] or 0, 1), 1)
        text = (
            "<b>Аналитика</b>\n\n"
            f"👥 Пользователи: {s['users']}\n"
            f"🛡 Команда: {s['staff']}\n"
            f"📣 Подключённые чаты/каналы: {s['targets']}\n"
            f"📰 Опубликовано: {s['published']}\n"
            f"🕒 Запланировано: {s['scheduled']}\n"
            f"🎟 Активные регистрации: {s['regs']}\n"
            f"🚪 Посетили: {s['attended']} ({attendance}%)\n"
            f"📨 Доставлено: {s['sent']}\n"
            f"⚠️ Ошибки доставки: {s['failed']} ({fail_rate}%)"
        )
        await self.bot.send_message(chat_id, text)

    async def _show_team(self, chat_id: int, user) -> None:
        if user["role"] != "owner":
            await self.bot.send_message(chat_id, "Управление командой доступно владельцу.")
            return
        await self.bot.send_message(
            chat_id,
            "<b>Команда бота</b>\n\n"
            "Администратор: согласование публикаций, чаты/каналы, аналитика и регистрации.\n"
            "Модератор: создаёт публикации и работает со списками участников.\n\n"
            "Приглашения одноразовые и действуют 72 часа.",
            reply_markup=_kb(
                [
                    [('➕ Администратор', 'team:invite:admin'), ('➕ Модератор', 'team:invite:editor')],
                    [('👥 Список команды', 'team:list')],
                    [('⬅️ В меню', 'menu')],
                ]
            ),
        )

    async def _dispatch_quick(self, m: Message, user, text: str) -> None:
        st = await self.state_get(user["telegram_id"])
        if st and text not in {"❓ Что делать", "⬅️ Назад", "✖️ Отмена", "🏠 Меню"}:
            await m.answer(
                "Сейчас открыт пошаговый сценарий. Завершите текущий шаг либо используйте «⬅️ Назад» / «✖️ Отмена».",
                reply_markup=self._quick_keyboard(user["role"]),
            )
            return

        if text == "❓ Что делать":
            if st and str(st["state"]).startswith("b:"):
                await m.answer(
                    "Вы сейчас создаёте публикацию. Можно заполнить текущий шаг, вернуться назад или отменить сценарий.",
                    reply_markup=self._with_nav(),
                )
            await self._show_help(m.chat.id, user)
            return
        if text == "⬅️ Назад":
            await self._go_back(m.chat.id, user["telegram_id"])
            return
        if text in {"✖️ Отмена", "🏠 Меню"}:
            await self.state_clear(user["telegram_id"])
            await self.send_menu(m.chat.id, user, "Главное меню" if text == "🏠 Меню" else "Действие отменено.")
            return
        if text == "➕ Создать":
            if user["role"] not in {"editor", "admin", "owner"}:
                await m.answer("Создание публикаций доступно команде бота.")
                return
            await self.state_set(user["telegram_id"], "b:type", {})
            await self._render_wizard_step(m.chat.id, user["telegram_id"], "b:type", {})
            return
        if text == "📅 Мероприятия":
            await self._show_events(m.chat.id)
        elif text == "🎟 Мои регистрации":
            await self._show_my_regs(m.chat.id, user["telegram_id"])
        elif text == "👤 Профиль":
            await self._show_profile(m.chat.id, user)
        elif text == "🔔 Уведомления":
            await self._show_notifications(m.chat.id, user)
        elif text == "📋 Регистрации":
            await self._show_regadmin(m.chat.id, user)
        elif text == "✅ Согласование":
            await self._show_reviews(m.chat.id, user)
        elif text == "📣 Чаты и каналы":
            await self._show_targets(m.chat.id, user)
        elif text == "📊 Аналитика":
            await self._show_analytics(m.chat.id, user)
        elif text == "👥 Команда":
            await self._show_team(m.chat.id, user)

    def _register_handlers(self):
        r = self.router

        @r.message(Command("help"))
        async def help_command(m: Message):
            user = await self.ensure_user(m.from_user)
            await self._show_help(m.chat.id, user)

        @r.message(Command("menu"))
        async def menu_command(m: Message):
            user = await self.ensure_user(m.from_user)
            await self.state_clear(user["telegram_id"])
            await self.send_menu(m.chat.id, user, "Главное меню")

        @r.message(F.chat.type == ChatType.PRIVATE)
        async def quick_buttons(m: Message):
            text = (m.text or "").strip()
            if text not in QUICK_BUTTONS:
                raise SkipHandler
            user = await self.ensure_user(m.from_user)
            await self._dispatch_quick(m, user, text)

        @r.callback_query(F.data == "nav:back")
        async def nav_back(c: CallbackQuery):
            await c.answer()
            await self._go_back(c.message.chat.id, c.from_user.id)

        @r.callback_query(F.data == "nav:cancel")
        async def nav_cancel(c: CallbackQuery):
            await c.answer()
            user = await self.ensure_user(c.from_user)
            await self.state_clear(user["telegram_id"])
            await self.send_menu(c.message.chat.id, user, "Действие отменено.")

        @r.callback_query(F.data == "nav:attachhelp")
        async def nav_attach_help(c: CallbackQuery):
            await c.answer()
            user = await self.ensure_user(c.from_user)
            await self._show_attach_help(c.message.chat.id, user)

        super()._register_handlers()

    async def run(self):
        await self.bot.set_my_commands(
            [
                BotCommand(command="start", description="Открыть бот"),
                BotCommand(command="menu", description="Главное меню"),
                BotCommand(command="help", description="Что делать"),
                BotCommand(command="cancel", description="Отменить текущий шаг"),
            ]
        )
        await super().run()


async def run_commission_bot_navigation(database_url: str) -> None:
    token = os.getenv("COMMISSION_BOT_TOKEN", "").strip()
    if not token:
        log.info("COMMISSION_BOT_TOKEN not set; commission bot disabled")
        return
    bootstrap = os.getenv("COMMISSION_BOOTSTRAP_CODE", "").strip()
    app = CommissionBotNavigation(database_url, token, bootstrap)
    await app.run()
