from __future__ import annotations

import logging
import os

from aiogram import F
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, KeyboardButton, Message, ReplyKeyboardMarkup

from app.commission_bot import _kb
from app.commission_bot_region import (
    COUNTRY_LABELS,
    REGION_COUNTRIES,
    REGION_LABELS,
    REGIONS,
    WORLD_COUNTRIES,
    CommissionBotRegion,
)

log = logging.getLogger(__name__)

UX_BUTTONS = {
    "➕ Создать",
    "✅ Согласование",
    "📋 Участники",
    "📋 Регистрации",  # compatibility with the previous keyboard
    "⚙️ Управление",
    "📅 События",
    "📅 Мероприятия",  # compatibility
    "🎟 Мои заявки",
    "🎟 Мои регистрации",  # compatibility
    "👤 Профиль",
    "🔔 Уведомления",
    "❓ Помощь",
    "❓ Что делать",  # compatibility
    "🏠 Меню",
    "⬅️ Назад",
    "✖️ Отмена",
}

COUNTRIES_PER_PAGE = 12


class CommissionBotUX(CommissionBotRegion):
    """Compact, role-aware UX on top of the Commission production bot."""

    def _quick_keyboard(self, role: str) -> ReplyKeyboardMarkup:
        rows: list[list[KeyboardButton]] = []

        if role in {"admin", "owner"}:
            rows.extend(
                [
                    [KeyboardButton(text="➕ Создать"), KeyboardButton(text="✅ Согласование")],
                    [KeyboardButton(text="📋 Участники"), KeyboardButton(text="⚙️ Управление")],
                    [KeyboardButton(text="📅 События"), KeyboardButton(text="🎟 Мои заявки")],
                    [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="❓ Помощь")],
                ]
            )
        elif role == "editor":
            rows.extend(
                [
                    [KeyboardButton(text="➕ Создать"), KeyboardButton(text="📋 Участники")],
                    [KeyboardButton(text="📅 События"), KeyboardButton(text="🎟 Мои заявки")],
                    [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="❓ Помощь")],
                ]
            )
        else:
            rows.extend(
                [
                    [KeyboardButton(text="📅 События"), KeyboardButton(text="🎟 Мои заявки")],
                    [KeyboardButton(text="🔔 Уведомления"), KeyboardButton(text="👤 Профиль")],
                    [KeyboardButton(text="❓ Помощь")],
                ]
            )

        return ReplyKeyboardMarkup(
            keyboard=rows,
            resize_keyboard=True,
            is_persistent=True,
            input_field_placeholder="Выберите действие",
        )

    async def send_menu(self, chat_id: int, user, text: str = "Главное меню"):
        role = user["role"]
        lines = [f"<b>{text}</b>", "", "Выберите нужный раздел кнопками ниже."]

        try:
            upcoming = await self.fetchrow(
                "SELECT COUNT(*) AS n FROM broadcasts WHERE status='published' AND event_at IS NOT NULL AND event_at>NOW()"
            )
            if upcoming and upcoming["n"]:
                lines.append(f"📅 Ближайших событий: <b>{upcoming['n']}</b>")

            if role in {"admin", "owner"}:
                pending = await self.fetchrow("SELECT COUNT(*) AS n FROM broadcasts WHERE status='pending'")
                if pending and pending["n"]:
                    lines.append(f"✅ На согласовании: <b>{pending['n']}</b>")
        except Exception:
            log.exception("Could not build Commission menu counters")

        await self.bot.send_message(chat_id, "\n".join(lines), reply_markup=self._quick_keyboard(role))

    async def _show_management(self, chat_id: int, user) -> None:
        if user["role"] not in {"admin", "owner"}:
            await self.bot.send_message(chat_id, "Управление доступно администратору и владельцу.")
            return

        rows = [
            [("📣 Чаты и каналы", "ux:targets"), ("📊 Аналитика", "ux:analytics")],
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
        await self.bot.send_message(
            chat_id,
            "<b>⚙️ Управление</b>\n\nЗдесь собраны настройки и служебные разделы. Основные действия оставлены в нижнем меню, чтобы оно не было перегружено.",
            reply_markup=_kb(rows),
        )

    async def _show_context_help(self, chat_id: int, user) -> None:
        st = await self.state_get(user["telegram_id"])
        if not st:
            await self._show_help(chat_id, user)
            return

        state = str(st["state"])
        hints = {
            "b:type": "Выберите, что создаёте: мероприятие, возможность, конкурс или объявление.",
            "b:title": "Напишите короткое название. Лучше 3–8 слов.",
            "b:description": "Отправьте готовый текст публикации. Можно использовать несколько абзацев.",
            "b:media": "Пришлите афишу/фото. Если изображения нет — используйте /skip.",
            "b:event_at": "Введите дату и время в формате ДД.ММ.ГГГГ ЧЧ:ММ. Бот использует выбранный часовой пояс.",
            "b:format": "Выберите очный, онлайн или гибридный формат.",
            "b:location": "Укажите адрес, площадку или ссылку. Если не требуется — /skip.",
            "b:regmode": "Выберите регистрацию внутри бота, внешнюю ссылку или вариант без регистрации.",
            "b:regform": "Быстрая регистрация — один клик. Анкета — если нужны данные участника.",
            "b:customq_choice": "Можно добавить до 5 собственных вопросов для конкретного события.",
            "b:customq_text": "Каждый вопрос отправьте с новой строки.",
            "b:capacity": "Введите лимит мест числом. Если лимита нет — /skip.",
            "b:regurl": "Отправьте полную ссылку, начинающуюся с https://.",
            "b:deadline": "Введите дедлайн регистрации или /skip.",
            "b:countries": "Выберите страны, для которых предназначена публикация.",
            "b:networks": "Выберите сеть распространения: Комиссия, МДС или партнёрская сеть.",
            "b:channels": "Выберите, куда отправлять: чаты/каналы и/или личные сообщения.",
            "b:reminders": "Отметьте нужные автоматические напоминания.",
            "b:preview": "Проверьте публикацию. Если всё верно — отправьте на согласование.",
        }

        if state.startswith("onboard:"):
            await self.bot.send_message(
                chat_id,
                "<b>Регистрация профиля</b>\n\nСначала выберите регион, затем страну. Это нужно для релевантных рассылок и статистики.",
            )
            return

        hint = hints.get(state)
        if hint:
            await self.bot.send_message(
                chat_id,
                f"<b>Подсказка по текущему шагу</b>\n\n{hint}\n\nИспользуйте кнопки «⬅️ Назад» или «✖️ Отмена» под текущим шагом, если хотите изменить маршрут.",
            )
        else:
            await self._show_help(chat_id, user)

    def _region_kb(self, prefix: str):
        # Long region names get a full-width row; short pairs remain compact.
        rows = [
            [(REGION_LABELS["russia"], f"{prefix}:russia"), (REGION_LABELS["europe"], f"{prefix}:europe")],
            [(REGION_LABELS["caucasus"], f"{prefix}:caucasus"), (REGION_LABELS["central_asia"], f"{prefix}:central_asia")],
            [(REGION_LABELS["middle_east"], f"{prefix}:middle_east")],
            [(REGION_LABELS["east_se_asia"], f"{prefix}:east_se_asia")],
            [(REGION_LABELS["south_asia"], f"{prefix}:south_asia"), (REGION_LABELS["africa"], f"{prefix}:africa")],
            [(REGION_LABELS["north_america"], f"{prefix}:north_america")],
            [(REGION_LABELS["latin_caribbean"], f"{prefix}:latin_caribbean")],
            [(REGION_LABELS["oceania"], f"{prefix}:oceania")],
        ]
        return _kb(rows)

    def _region_country_kb(self, prefix: str, region: str, back_callback: str, page: int = 0):
        codes = sorted(REGION_COUNTRIES.get(region, []), key=lambda code: WORLD_COUNTRIES.get(code, code))
        total_pages = max(1, (len(codes) + COUNTRIES_PER_PAGE - 1) // COUNTRIES_PER_PAGE)
        page = max(0, min(page, total_pages - 1))
        chunk = codes[page * COUNTRIES_PER_PAGE : (page + 1) * COUNTRIES_PER_PAGE]

        buttons = [(COUNTRY_LABELS[code], f"{prefix}:{code}") for code in chunk]
        rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]

        nav = []
        page_prefix = "ux:onbpage" if prefix == "onb" else "ux:pcpage"
        if page > 0:
            nav.append(("◀️", f"{page_prefix}:{region}:{page - 1}"))
        if total_pages > 1:
            nav.append((f"{page + 1}/{total_pages}", f"ux:nop"))
        if page < total_pages - 1:
            nav.append(("▶️", f"{page_prefix}:{region}:{page + 1}"))
        if nav:
            rows.append(nav)
        rows.append([("⬅️ К регионам", back_callback)])
        return _kb(rows)

    async def _dispatch_ux_button(self, m: Message, user, text: str) -> None:
        st = await self.state_get(user["telegram_id"])
        state = str(st["state"]) if st else ""

        if st and text not in {"❓ Помощь", "❓ Что делать", "⬅️ Назад", "✖️ Отмена", "🏠 Меню"}:
            await m.answer(
                "Сейчас открыт пошаговый сценарий. Завершите текущий шаг или используйте кнопки «⬅️ Назад» / «✖️ Отмена» под ним.",
            )
            return

        if text in {"❓ Помощь", "❓ Что делать"}:
            await self._show_context_help(m.chat.id, user)
            return
        if text == "⬅️ Назад":
            await self._go_back(m.chat.id, user["telegram_id"])
            return
        if text == "✖️ Отмена":
            await self.state_clear(user["telegram_id"])
            await self.send_menu(m.chat.id, user, "Действие отменено")
            return
        if text == "🏠 Меню":
            if state.startswith("onboard:") and not user["onboarding_complete"]:
                await m.answer("Сначала завершите выбор региона и страны — это займёт несколько секунд.")
                return
            await self.state_clear(user["telegram_id"])
            await self.send_menu(m.chat.id, user)
            return

        if text == "➕ Создать":
            if user["role"] not in {"editor", "admin", "owner"}:
                await m.answer("Создание публикаций доступно команде бота.")
                return
            await self.state_set(user["telegram_id"], "b:type", {})
            await self._render_wizard_step(m.chat.id, user["telegram_id"], "b:type", {})
        elif text == "✅ Согласование":
            await self._show_reviews(m.chat.id, user)
        elif text in {"📋 Участники", "📋 Регистрации"}:
            await self._show_regadmin(m.chat.id, user)
        elif text == "⚙️ Управление":
            await self._show_management(m.chat.id, user)
        elif text in {"📅 События", "📅 Мероприятия"}:
            await self._show_events(m.chat.id)
        elif text in {"🎟 Мои заявки", "🎟 Мои регистрации"}:
            await self._show_my_regs(m.chat.id, user["telegram_id"])
        elif text == "👤 Профиль":
            await self._show_profile(m.chat.id, user)
        elif text == "🔔 Уведомления":
            await self._show_notifications(m.chat.id, user)

    def _register_handlers(self):
        r = self.router

        @r.message(F.chat.type == ChatType.PRIVATE)
        async def ux_quick_buttons(m: Message):
            text = (m.text or "").strip()
            if text not in UX_BUTTONS:
                raise SkipHandler
            user = await self.ensure_user(m.from_user)
            await self._dispatch_ux_button(m, user, text)

        @r.callback_query(F.data == "ux:nop")
        async def ux_nop(c: CallbackQuery):
            await c.answer()

        @r.callback_query(F.data.startswith("ux:onbpage:"))
        async def ux_onboarding_page(c: CallbackQuery):
            await c.answer()
            _, _, region, page_raw = c.data.split(":", 3)
            page = int(page_raw)
            await c.message.edit_text(
                f"<b>Регистрация · шаг 2 из 2</b>\n\nРегион: <b>{REGION_LABELS[region]}</b>\nВыберите страну:",
                reply_markup=self._region_country_kb("onb", region, "onbregion:back", page),
            )

        @r.callback_query(F.data.startswith("ux:pcpage:"))
        async def ux_profile_country_page(c: CallbackQuery):
            await c.answer()
            _, _, region, page_raw = c.data.split(":", 3)
            page = int(page_raw)
            await c.message.edit_text(
                f"<b>Изменение страны</b>\n\nРегион: <b>{REGION_LABELS[region]}</b>\nВыберите страну:",
                reply_markup=self._region_country_kb("pc", region, "pcregion:back", page),
            )

        @r.callback_query(F.data.startswith("onbregion:"))
        async def ux_onboarding_region(c: CallbackQuery):
            await c.answer()
            key = c.data.split(":", 1)[1]
            user = await self.ensure_user(c.from_user)
            st = await self.state_get(user["telegram_id"])
            payload = dict(st["payload"] or {}) if st else {"pending": None}

            if key == "back":
                await self.state_set(user["telegram_id"], "onboard:region", payload)
                await c.message.edit_text(
                    "<b>Регистрация · шаг 1 из 2</b>\n\nВыберите регион:",
                    reply_markup=self._region_kb("onbregion"),
                )
                return
            if key not in REGION_COUNTRIES:
                return

            payload["region"] = key
            await self.state_set(user["telegram_id"], "onboard:country", payload)
            await c.message.edit_text(
                f"<b>Регистрация · шаг 2 из 2</b>\n\nРегион: <b>{REGION_LABELS[key]}</b>\nВыберите страну:",
                reply_markup=self._region_country_kb("onb", key, "onbregion:back", 0),
            )

        @r.callback_query(F.data == "profile:country")
        async def ux_profile_country(c: CallbackQuery):
            await c.answer()
            await c.message.edit_text(
                "<b>Изменение страны</b>\n\nСначала выберите регион:",
                reply_markup=self._region_kb("pcregion"),
            )

        @r.callback_query(F.data.startswith("pcregion:"))
        async def ux_profile_region(c: CallbackQuery):
            await c.answer()
            key = c.data.split(":", 1)[1]
            if key == "back":
                await c.message.edit_text(
                    "<b>Изменение страны</b>\n\nВыберите регион:",
                    reply_markup=self._region_kb("pcregion"),
                )
                return
            if key not in REGION_COUNTRIES:
                return
            await c.message.edit_text(
                f"<b>Изменение страны</b>\n\nРегион: <b>{REGION_LABELS[key]}</b>\nВыберите страну:",
                reply_markup=self._region_country_kb("pc", key, "pcregion:back", 0),
            )

        @r.callback_query(F.data == "ux:targets")
        async def ux_targets(c: CallbackQuery):
            await c.answer()
            user = await self.ensure_user(c.from_user)
            await self._show_targets(c.message.chat.id, user)

        @r.callback_query(F.data == "ux:analytics")
        async def ux_analytics(c: CallbackQuery):
            await c.answer()
            user = await self.ensure_user(c.from_user)
            await self._show_analytics(c.message.chat.id, user)

        @r.callback_query(F.data == "ux:team")
        async def ux_team(c: CallbackQuery):
            await c.answer()
            user = await self.ensure_user(c.from_user)
            await self._show_team(c.message.chat.id, user)

        @r.callback_query(F.data == "ux:notifications")
        async def ux_notifications(c: CallbackQuery):
            await c.answer()
            user = await self.ensure_user(c.from_user)
            await self._show_notifications(c.message.chat.id, user)

        @r.callback_query(F.data == "ux:profile")
        async def ux_profile(c: CallbackQuery):
            await c.answer()
            user = await self.ensure_user(c.from_user)
            await self._show_profile(c.message.chat.id, user)

        @r.callback_query(F.data == "ux:help")
        async def ux_help(c: CallbackQuery):
            await c.answer()
            user = await self.ensure_user(c.from_user)
            await self._show_help(c.message.chat.id, user)

        super()._register_handlers()


async def run_commission_bot_ux(database_url: str) -> None:
    token = os.getenv("COMMISSION_BOT_TOKEN", "").strip()
    if not token:
        log.info("COMMISSION_BOT_TOKEN not set; commission bot disabled")
        return
    bootstrap = os.getenv("COMMISSION_BOOTSTRAP_CODE", "").strip()
    app = CommissionBotUX(database_url, token, bootstrap)
    await app.run()
