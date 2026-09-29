from __future__ import annotations

import json
import logging
import os

from aiogram import F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup

from app.commission_bot import COUNTRIES, _kb
from app.commission_bot_navigation_safe import CommissionBotNavigationSafe

log = logging.getLogger(__name__)

REGIONS = [
    ("russia", "🇷🇺 Россия"),
    ("europe", "🇪🇺 Европа"),
    ("caucasus", "⛰ Кавказ"),
    ("central_asia", "🌏 Центральная Азия"),
    ("other", "🌍 Другие страны"),
]

REGION_COUNTRIES = {
    "russia": ["RU"],
    "europe": ["BY", "MD"],
    "caucasus": ["AM", "AZ", "GE"],
    "central_asia": ["KZ", "KG", "UZ", "TJ"],
    "other": ["OTHER"],
}

REGION_LABELS = dict(REGIONS)
COUNTRY_LABELS = dict(COUNTRIES)


class CommissionBotRegion(CommissionBotNavigationSafe):
    async def state_get(self, uid: int):
        """Return state payload as a dict regardless of asyncpg JSON codec behavior."""
        row = await super().state_get(uid)
        if not row:
            return None
        data = dict(row)
        payload = data.get("payload")
        if isinstance(payload, str):
            try:
                decoded = json.loads(payload)
                data["payload"] = decoded if isinstance(decoded, dict) else {}
            except (TypeError, ValueError, json.JSONDecodeError):
                data["payload"] = {}
        elif payload is None:
            data["payload"] = {}
        return data

    def _region_kb(self, prefix: str) -> InlineKeyboardMarkup:
        rows = []
        for i in range(0, len(REGIONS), 2):
            rows.append([(label, f"{prefix}:{code}") for code, label in REGIONS[i : i + 2]])
        return _kb(rows)

    def _region_country_kb(self, prefix: str, region: str, back_callback: str) -> InlineKeyboardMarkup:
        codes = REGION_COUNTRIES.get(region, [])
        buttons = [(COUNTRY_LABELS[code], f"{prefix}:{code}") for code in codes if code in COUNTRY_LABELS]
        rows = []
        for i in range(0, len(buttons), 2):
            rows.append(buttons[i : i + 2])
        rows.append([("⬅️ К регионам", back_callback)])
        return _kb(rows)

    async def start_onboarding(self, chat_id: int, user, pending: dict | None = None):
        await self.state_set(user["telegram_id"], "onboard:region", {"pending": pending})
        await self.bot.send_message(
            chat_id,
            "<b>Регистрация · шаг 1 из 2</b>\n\n"
            "Сначала выберите регион. На следующем шаге бот покажет только страны этого региона — так список будет короче и удобнее.",
            reply_markup=self._region_kb("onbregion"),
        )

    def _register_handlers(self):
        r = self.router

        @r.callback_query(F.data.startswith("onbregion:"))
        async def onboarding_region(c: CallbackQuery):
            await c.answer()
            key = c.data.split(":", 1)[1]
            user = await self.ensure_user(c.from_user)
            st = await self.state_get(user["telegram_id"])
            payload = dict(st["payload"] or {}) if st else {"pending": None}

            if key == "back":
                await self.state_set(user["telegram_id"], "onboard:region", payload)
                return await c.message.answer(
                    "<b>Регистрация · шаг 1 из 2</b>\n\nВыберите регион:",
                    reply_markup=self._region_kb("onbregion"),
                )

            if key not in REGION_COUNTRIES:
                return

            payload["region"] = key
            await self.state_set(user["telegram_id"], "onboard:country", payload)
            await c.message.answer(
                f"<b>Регистрация · шаг 2 из 2</b>\n\n"
                f"Регион: <b>{REGION_LABELS[key]}</b>\n"
                "Теперь выберите страну:",
                reply_markup=self._region_country_kb("onb", key, "onbregion:back"),
            )

        @r.callback_query(F.data == "profile:country")
        async def profile_country_region(c: CallbackQuery):
            await c.answer()
            await c.message.answer(
                "<b>Изменение страны</b>\n\nСначала выберите регион:",
                reply_markup=self._region_kb("pcregion"),
            )

        @r.callback_query(F.data.startswith("pcregion:"))
        async def profile_region(c: CallbackQuery):
            await c.answer()
            key = c.data.split(":", 1)[1]
            if key == "back":
                return await c.message.answer(
                    "<b>Изменение страны</b>\n\nВыберите регион:",
                    reply_markup=self._region_kb("pcregion"),
                )
            if key not in REGION_COUNTRIES:
                return
            await c.message.answer(
                f"Регион: <b>{REGION_LABELS[key]}</b>\n\nВыберите страну:",
                reply_markup=self._region_country_kb("pc", key, "pcregion:back"),
            )

        super()._register_handlers()


async def run_commission_bot_region(database_url: str) -> None:
    token = os.getenv("COMMISSION_BOT_TOKEN", "").strip()
    if not token:
        log.info("COMMISSION_BOT_TOKEN not set; commission bot disabled")
        return
    bootstrap = os.getenv("COMMISSION_BOOTSTRAP_CODE", "").strip()
    app = CommissionBotRegion(database_url, token, bootstrap)
    await app.run()
