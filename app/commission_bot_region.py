from __future__ import annotations

import json
import logging
import os

from aiogram import F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup

from app.commission_bot import _kb
from app.commission_bot_navigation_safe import CommissionBotNavigationSafe

log = logging.getLogger(__name__)

REGIONS = [
    ("russia", "🇷🇺 Россия"),
    ("europe", "🇪🇺 Европа"),
    ("caucasus", "⛰ Кавказ"),
    ("central_asia", "🌏 Центральная Азия"),
    ("middle_east", "🌍 Ближний Восток"),
    ("east_se_asia", "🌏 Восточная и Юго-Восточная Азия"),
    ("south_asia", "🌏 Южная Азия"),
    ("africa", "🌍 Африка"),
    ("north_america", "🌎 Северная Америка"),
    ("latin_caribbean", "🌎 Латинская Америка и Карибы"),
    ("oceania", "🌊 Океания"),
]

WORLD_COUNTRIES = {
    "AD": "Андорра",
    "AE": "ОАЭ",
    "AF": "Афганистан",
    "AG": "Антигуа и Барбуда",
    "AL": "Албания",
    "AM": "Армения",
    "AO": "Ангола",
    "AR": "Аргентина",
    "AT": "Австрия",
    "AU": "Австралия",
    "AZ": "Азербайджан",
    "BA": "Босния и Герцеговина",
    "BB": "Барбадос",
    "BD": "Бангладеш",
    "BE": "Бельгия",
    "BF": "Буркина-Фасо",
    "BG": "Болгария",
    "BH": "Бахрейн",
    "BI": "Бурунди",
    "BJ": "Бенин",
    "BN": "Бруней",
    "BO": "Боливия",
    "BR": "Бразилия",
    "BS": "Багамы",
    "BT": "Бутан",
    "BW": "Ботсвана",
    "BY": "Беларусь",
    "BZ": "Белиз",
    "CA": "Канада",
    "CD": "ДР Конго",
    "CF": "ЦАР",
    "CG": "Республика Конго",
    "CH": "Швейцария",
    "CI": "Кот-д’Ивуар",
    "CL": "Чили",
    "CM": "Камерун",
    "CN": "Китай",
    "CO": "Колумбия",
    "CR": "Коста-Рика",
    "CU": "Куба",
    "CV": "Кабо-Верде",
    "CY": "Кипр",
    "CZ": "Чехия",
    "DE": "Германия",
    "DJ": "Джибути",
    "DK": "Дания",
    "DM": "Доминика",
    "DO": "Доминиканская Республика",
    "DZ": "Алжир",
    "EC": "Эквадор",
    "EE": "Эстония",
    "EG": "Египет",
    "ER": "Эритрея",
    "ES": "Испания",
    "ET": "Эфиопия",
    "FI": "Финляндия",
    "FJ": "Фиджи",
    "FM": "Микронезия",
    "FR": "Франция",
    "GA": "Габон",
    "GB": "Великобритания",
    "GD": "Гренада",
    "GE": "Грузия",
    "GH": "Гана",
    "GM": "Гамбия",
    "GN": "Гвинея",
    "GQ": "Экваториальная Гвинея",
    "GR": "Греция",
    "GT": "Гватемала",
    "GW": "Гвинея-Бисау",
    "GY": "Гайана",
    "HN": "Гондурас",
    "HR": "Хорватия",
    "HT": "Гаити",
    "HU": "Венгрия",
    "ID": "Индонезия",
    "IE": "Ирландия",
    "IL": "Израиль",
    "IN": "Индия",
    "IQ": "Ирак",
    "IR": "Иран",
    "IS": "Исландия",
    "IT": "Италия",
    "JM": "Ямайка",
    "JO": "Иордания",
    "JP": "Япония",
    "KE": "Кения",
    "KG": "Кыргызстан",
    "KH": "Камбоджа",
    "KI": "Кирибати",
    "KM": "Коморы",
    "KN": "Сент-Китс и Невис",
    "KP": "Северная Корея",
    "KR": "Южная Корея",
    "KW": "Кувейт",
    "KZ": "Казахстан",
    "LA": "Лаос",
    "LB": "Ливан",
    "LC": "Сент-Люсия",
    "LI": "Лихтенштейн",
    "LK": "Шри-Ланка",
    "LR": "Либерия",
    "LS": "Лесото",
    "LT": "Литва",
    "LU": "Люксембург",
    "LV": "Латвия",
    "LY": "Ливия",
    "MA": "Марокко",
    "MC": "Монако",
    "MD": "Молдова",
    "ME": "Черногория",
    "MG": "Мадагаскар",
    "MH": "Маршалловы Острова",
    "MK": "Северная Македония",
    "ML": "Мали",
    "MM": "Мьянма",
    "MN": "Монголия",
    "MR": "Мавритания",
    "MT": "Мальта",
    "MU": "Маврикий",
    "MV": "Мальдивы",
    "MW": "Малави",
    "MX": "Мексика",
    "MY": "Малайзия",
    "MZ": "Мозамбик",
    "NA": "Намибия",
    "NE": "Нигер",
    "NG": "Нигерия",
    "NI": "Никарагуа",
    "NL": "Нидерланды",
    "NO": "Норвегия",
    "NP": "Непал",
    "NR": "Науру",
    "NZ": "Новая Зеландия",
    "OM": "Оман",
    "PA": "Панама",
    "PE": "Перу",
    "PG": "Папуа — Новая Гвинея",
    "PH": "Филиппины",
    "PK": "Пакистан",
    "PL": "Польша",
    "PS": "Палестина",
    "PT": "Португалия",
    "PW": "Палау",
    "PY": "Парагвай",
    "QA": "Катар",
    "RO": "Румыния",
    "RS": "Сербия",
    "RU": "Россия",
    "RW": "Руанда",
    "SA": "Саудовская Аравия",
    "SB": "Соломоновы Острова",
    "SC": "Сейшелы",
    "SD": "Судан",
    "SE": "Швеция",
    "SG": "Сингапур",
    "SI": "Словения",
    "SK": "Словакия",
    "SL": "Сьерра-Леоне",
    "SM": "Сан-Марино",
    "SN": "Сенегал",
    "SO": "Сомали",
    "SR": "Суринам",
    "SS": "Южный Судан",
    "ST": "Сан-Томе и Принсипи",
    "SV": "Сальвадор",
    "SY": "Сирия",
    "SZ": "Эсватини",
    "TD": "Чад",
    "TG": "Того",
    "TH": "Таиланд",
    "TJ": "Таджикистан",
    "TL": "Восточный Тимор",
    "TM": "Туркменистан",
    "TN": "Тунис",
    "TO": "Тонга",
    "TR": "Турция",
    "TT": "Тринидад и Тобаго",
    "TV": "Тувалу",
    "TZ": "Танзания",
    "UA": "Украина",
    "UG": "Уганда",
    "US": "США",
    "UY": "Уругвай",
    "UZ": "Узбекистан",
    "VA": "Ватикан",
    "VC": "Сент-Винсент и Гренадины",
    "VE": "Венесуэла",
    "VN": "Вьетнам",
    "VU": "Вануату",
    "WS": "Самоа",
    "YE": "Йемен",
    "ZA": "ЮАР",
    "ZM": "Замбия",
    "ZW": "Зимбабве",
}

REGION_COUNTRIES = {
    "russia": ["RU"],
    "europe": ["AT", "AL", "AD", "BY", "BE", "BG", "BA", "VA", "GB", "HU", "DE", "GR", "DK", "IE", "IS", "ES", "IT", "CY", "LV", "LT", "LI", "LU", "MT", "MD", "MC", "NL", "NO", "PL", "PT", "RO", "SM", "MK", "RS", "SK", "SI", "UA", "FI", "FR", "HR", "ME", "CZ", "CH", "SE", "EE"],
    "caucasus": ["AZ", "AM", "GE"],
    "central_asia": ["KZ", "KG", "TJ", "TM", "UZ"],
    "middle_east": ["BH", "IL", "JO", "IQ", "IR", "YE", "QA", "KW", "LB", "AE", "OM", "PS", "SA", "SY", "TR"],
    "east_se_asia": ["BN", "TL", "VN", "ID", "KH", "CN", "LA", "MY", "MN", "MM", "SG", "KP", "TH", "PH", "KR", "JP"],
    "south_asia": ["AF", "BD", "BT", "IN", "MV", "NP", "PK", "LK"],
    "africa": ["DZ", "AO", "BJ", "BW", "BF", "BI", "GA", "GM", "GH", "GN", "GW", "DJ", "EG", "ZM", "ZW", "CV", "CM", "KE", "KM", "CD", "CG", "CI", "LS", "LR", "LY", "MU", "MR", "MG", "MW", "ML", "MA", "MZ", "NA", "NE", "NG", "RW", "ST", "SC", "SN", "SO", "SD", "SL", "TZ", "TG", "TN", "UG", "CF", "TD", "GQ", "ER", "SZ", "ET", "ZA", "SS"],
    "north_america": ["CA", "MX", "US"],
    "latin_caribbean": ["AG", "AR", "BS", "BB", "BZ", "BO", "BR", "VE", "HT", "GY", "GT", "HN", "GD", "DM", "DO", "CO", "CR", "CU", "NI", "PA", "PY", "PE", "SV", "KN", "LC", "VC", "SR", "TT", "UY", "CL", "EC", "JM"],
    "oceania": ["AU", "VU", "KI", "MH", "FM", "NR", "NZ", "PW", "PG", "WS", "SB", "TO", "TV", "FJ"],
}

REGION_LABELS = dict(REGIONS)

_all_region_codes = [code for codes in REGION_COUNTRIES.values() for code in codes]
if len(WORLD_COUNTRIES) != 195 or len(_all_region_codes) != 195 or set(_all_region_codes) != set(WORLD_COUNTRIES):
    raise RuntimeError("World country catalogue must contain exactly 195 countries without duplicates")


def _flag(code: str) -> str:
    return "".join(chr(0x1F1E6 + ord(ch) - ord("A")) for ch in code)


def _country_label(code: str) -> str:
    return f"{_flag(code)} {WORLD_COUNTRIES[code]}"


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
        buttons = [(_country_label(code), f"{prefix}:{code}") for code in codes]
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
            "Сначала выберите регион. Затем бот покажет страны этого региона. В каталоге доступны все 195 стран мира.",
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

        @r.callback_query(F.data.startswith("onb:"))
        async def onboarding_country_world(c: CallbackQuery):
            await c.answer()
            code = c.data.split(":", 1)[1]
            if code not in WORLD_COUNTRIES:
                return
            user = await self.ensure_user(c.from_user)
            st = await self.state_get(user["telegram_id"])
            payload = dict(st["payload"] or {}) if st else {}
            await self.execute(
                "UPDATE users SET country_code=$2,country_name=$3,updated_at=NOW() WHERE telegram_id=$1",
                user["telegram_id"],
                code,
                _country_label(code),
            )
            await self.state_set(user["telegram_id"], "onboard:notify", payload)
            await c.message.answer(
                "Хотите получать общие личные рассылки по вашей стране? Напоминания по мероприятиям, на которые вы зарегистрировались, приходят отдельно.",
                reply_markup=_kb([[("✅ Да", "onbnotify:1"), ("Нет", "onbnotify:0")]]),
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

        @r.callback_query(F.data.startswith("pc:"))
        async def profile_country_world(c: CallbackQuery):
            await c.answer()
            code = c.data.split(":", 1)[1]
            if code not in WORLD_COUNTRIES:
                return
            await self.execute(
                "UPDATE users SET country_code=$2,country_name=$3,updated_at=NOW() WHERE telegram_id=$1",
                c.from_user.id,
                code,
                _country_label(code),
            )
            await c.message.answer(f"Страна обновлена ✅\n{_country_label(code)}")

        super()._register_handlers()


async def run_commission_bot_region(database_url: str) -> None:
    token = os.getenv("COMMISSION_BOT_TOKEN", "").strip()
    if not token:
        log.info("COMMISSION_BOT_TOKEN not set; commission bot disabled")
        return
    bootstrap = os.getenv("COMMISSION_BOOTSTRAP_CODE", "").strip()
    app = CommissionBotRegion(database_url, token, bootstrap)
    await app.run()
