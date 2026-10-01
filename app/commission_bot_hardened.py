from __future__ import annotations

import asyncio
import html
import json
import logging
import os

from aiogram import F
from aiogram.types import CallbackQuery

from app.commission_bot import _kb
from app.commission_bot_engagement import (
    TARGET_PURPOSES,
    TARGET_TAGS,
    user_matches_segment,
)
from app.commission_bot_region import REGION_COUNTRIES, REGION_LABELS, WORLD_COUNTRIES, _country_label
from app.commission_bot_resilience import CommissionBotResilient

log = logging.getLogger(__name__)

_NETWORKS = {
    "commission": "Комиссия",
    "mds": "МДС",
    "partner": "Партнёр",
}
_COUNTRY_PAGE = 12
_SINGLETON_LOCK = 8842890484


def _json_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(x) for x in value]
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            return [str(x) for x in decoded] if isinstance(decoded, list) else []
        except Exception:
            return []
    return []


class CommissionBotHardened(CommissionBotResilient):
    """Product-hardening layer for admin segmentation and zero-downtime rollouts."""

    def _target_segment_match(self, target: dict, segment: dict) -> bool:
        networks = set(segment.get("target_networks") or ["commission"])
        if target.get("network") not in networks:
            return False

        purposes = set(segment.get("target_purposes") or [])
        if purposes and target.get("purpose") not in purposes:
            return False

        wanted_tags = set(segment.get("target_tags") or [])
        target_tags = set(_json_list(target.get("tags")))
        if wanted_tags and not wanted_tags.intersection(target_tags):
            return False

        countries = set(segment.get("countries") or [])
        regions = set(segment.get("regions") or [])
        scope = target.get("geography_scope") or "country"

        if not countries and not regions:
            return True
        if scope == "global":
            return bool(segment.get("include_global_targets"))
        if countries:
            # A region-wide channel is broader than a country filter, so do not
            # silently include it in a country-specific campaign.
            return scope == "country" and target.get("country_code") in countries
        if regions:
            if scope == "region":
                return target.get("region_code") in regions
            if scope == "country":
                code = target.get("country_code")
                return any(code in REGION_COUNTRIES.get(region, []) for region in regions)
        return False

    async def _matching_targets(self, segment: dict) -> list[dict]:
        rows = await self.fetch("SELECT * FROM targets WHERE status='approved' AND bot_can_post=TRUE ORDER BY title")
        return [dict(row) for row in rows if self._target_segment_match(dict(row), segment)]

    async def _estimate_segment(self, segment: dict, channels: dict) -> tuple[int, int]:
        users_count = 0
        targets_count = 0
        if channels.get("dm"):
            users_count = sum(
                1 for user in await self._segment_candidates() if user_matches_segment(user, segment)
            )
        if channels.get("targets"):
            targets_count = len(await self._matching_targets(segment))
        return users_count, targets_count

    def _segment_summary(self, p: dict) -> str:
        base = super()._segment_summary(p)
        channels = p.get("channels") or {}
        if not channels.get("targets"):
            return base
        segment = p.get("segment") or {}
        networks = segment.get("target_networks") or ["commission"]
        parts = ["сеть: " + ", ".join(_NETWORKS.get(x, x) for x in networks)]
        purposes = segment.get("target_purposes") or []
        if purposes:
            parts.append("назначение: " + ", ".join(TARGET_PURPOSES.get(x, x) for x in purposes))
        tags = segment.get("target_tags") or []
        if tags:
            parts.append("теги: " + ", ".join(TARGET_TAGS.get(x, x) for x in tags))
        if (segment.get("countries") or segment.get("regions")):
            parts.append(
                "международные площадки: "
                + ("включены" if segment.get("include_global_targets") else "не включены")
            )
        return base + "\n📣 " + "; ".join(parts)

    async def _show_segment_builder(self, chat_id: int, uid: int, p: dict) -> None:
        segment = p.setdefault("segment", {})
        channels = p.setdefault("channels", {"dm": True, "targets": False})
        if channels.get("targets") and not segment.get("target_networks"):
            segment["target_networks"] = ["commission"]
        users_count, targets_count = await self._estimate_segment(segment, channels)
        p["estimate"] = {"users": users_count, "targets": targets_count}
        await self.state_set(uid, "segment:builder", p)

        rows = [
            [("🌍 География", "seg:geo"), ("🎂 Возраст", "seg:age")],
            [("👤 Статус", "seg:status"), ("✨ Интересы", "seg:interest")],
            [("✅ Только активные" if segment.get("active_only") else "▫️ Только активные", "seg:active")],
            [
                ("✅ 👤 Личные" if channels.get("dm") else "▫️ 👤 Личные", "seg:ch:dm"),
                ("✅ 📣 Площадки" if channels.get("targets") else "▫️ 📣 Площадки", "seg:ch:targets"),
            ],
        ]
        if channels.get("targets"):
            rows.append([("⚙️ Фильтры площадок", "seg:tf")])
        rows += [
            [(f"👥 Проверить аудиторию · {users_count + targets_count}", "seg:estimate")],
            [("✍️ Написать сообщение", "seg:compose")],
            [("✖️ Отмена", "seg:cancel")],
        ]

        extra = ""
        if channels.get("targets"):
            matched = await self._matching_targets(segment)
            if matched:
                names = ", ".join(html.escape(str(x.get("title") or "")) for x in matched[:3])
                extra = f"\n\n📣 Подходят площадки: <b>{targets_count}</b> · {names}"
                if len(matched) > 3:
                    extra += f" и ещё {len(matched) - 3}"
            else:
                extra = "\n\n📣 Подходящих подтверждённых площадок сейчас нет. Личная рассылка при этом продолжит работать."

        await self.bot.send_message(
            chat_id,
            "<b>🎯 Новая точная рассылка</b>\n\n"
            + self._segment_summary(p)
            + f"\n\n👤 Участники: <b>{users_count}</b> · 📣 Площадки: <b>{targets_count}</b>"
            + extra
            + "\n\nСначала настрой аудиторию. Перед отправкой будет отдельный контрольный экран — случайной массовой отправки не будет.",
            reply_markup=_kb(rows),
        )

    async def _show_target_filters(self, c: CallbackQuery, p: dict) -> None:
        segment = p.setdefault("segment", {})
        networks = set(segment.get("target_networks") or ["commission"])
        purposes = set(segment.get("target_purposes") or [])
        tags = set(segment.get("target_tags") or [])
        narrowed_geo = bool(segment.get("countries") or segment.get("regions"))

        rows = [
            [
                (("✅ " if key in networks else "▫️ ") + label, f"seg:tn:{key}")
                for key, label in _NETWORKS.items()
            ],
            [("— Для каких публикаций —", "seg:nop")],
        ]
        purpose_items = list(TARGET_PURPOSES.items())
        for i in range(0, len(purpose_items), 2):
            rows.append(
                [
                    (("✅ " if key in purposes else "▫️ ") + label, f"seg:tp:{key}")
                    for key, label in purpose_items[i : i + 2]
                ]
            )
        rows.append([("— Теги площадок —", "seg:nop")])
        tag_items = list(TARGET_TAGS.items())
        for i in range(0, len(tag_items), 2):
            rows.append(
                [
                    (("✅ " if key in tags else "▫️ ") + label, f"seg:tt:{key}")
                    for key, label in tag_items[i : i + 2]
                ]
            )
        if narrowed_geo:
            rows.append(
                [
                    (
                        ("✅ " if segment.get("include_global_targets") else "▫️ ")
                        + "🌍 Международные площадки",
                        "seg:tglo",
                    )
                ]
            )
        rows.append([("Готово →", "seg:back")])
        await self._edit_or_send(
            c,
            "<b>Фильтры чатов и каналов</b>\n\n"
            "По умолчанию используются только площадки Комиссии. МДС и партнёрские площадки нужно включить явно. "
            "Пустой список назначения/тегов означает «любые».",
            _kb(rows),
        )

    async def _show_targets(self, c: CallbackQuery) -> None:
        user = await self.ensure_user(c.from_user)
        if user["role"] not in {"admin", "owner"}:
            return
        await self.state_clear(user["telegram_id"])
        targets = await self.fetch(
            "SELECT * FROM targets ORDER BY CASE status WHEN 'pending' THEN 0 WHEN 'approved' THEN 1 ELSE 2 END, updated_at DESC LIMIT 80"
        )
        pending = sum(1 for t in targets if t["status"] == "pending")
        approved = sum(1 for t in targets if t["status"] == "approved" and t["bot_can_post"])
        blocked = sum(1 for t in targets if not t["bot_can_post"])
        buttons = []
        for target in targets:
            icon = "🟡" if target["status"] == "pending" else "🟢" if target["status"] == "approved" and target["bot_can_post"] else "🔴"
            buttons.append([(f"{icon} {str(target['title'])[:44]}", f"tg:open:{target['chat_id']}")])
        buttons += [[("🔄 Обновить", "tg:list"), ("➕ Как подключить", "tg:guide")], [("⬅️ Управление", "menu")]]
        text = (
            "<b>📣 Площадки рассылки</b>\n\n"
            f"🟢 Готово: <b>{approved}</b> · 🟡 Настроить: <b>{pending}</b> · 🔴 Нет прав: <b>{blocked}</b>\n\n"
        )
        if not targets:
            text += (
                "Пока ни одного чата или канала не обнаружено. Добавь <b>@MVKSRS_bot</b> администратором в нужную площадку, затем нажми «Обновить». "
                "Личные рассылки участникам работают независимо от этого."
            )
        else:
            text += "Сначала настрой 🟡 площадки. В рассылку попадают только 🟢 подтверждённые площадки с правом публикации."
        await self._edit_or_send(c, text, _kb(buttons))

    async def _show_target_card(self, c: CallbackQuery, target_id: int) -> None:
        target = await self.fetchrow("SELECT * FROM targets WHERE chat_id=$1", target_id)
        if not target:
            return await c.message.answer("Площадка больше не найдена. Обнови список.")
        tags = _json_list(target["tags"])
        scope = target["geography_scope"] or "country"
        if scope == "global":
            geo = "🌍 Международная"
            geo_ok = True
        elif scope == "region":
            geo = REGION_LABELS.get(target["region_code"], "регион не выбран")
            geo_ok = bool(target["region_code"])
        else:
            code = target["country_code"]
            geo = _country_label(code) if code in WORLD_COUNTRIES else "страна не выбрана"
            geo_ok = bool(code)
        network_ok = target["network"] in _NETWORKS
        purpose_ok = target["purpose"] in TARGET_PURPOSES
        rights_ok = bool(target["bot_can_post"])
        ready = network_ok and geo_ok and purpose_ok and rights_ok
        checklist = (
            f"{'✅' if rights_ok else '❌'} право публикации\n"
            f"{'✅' if network_ok else '❌'} сеть\n"
            f"{'✅' if geo_ok else '❌'} география\n"
            f"{'✅' if purpose_ok else '❌'} назначение"
        )
        text = (
            f"<b>{html.escape(str(target['title']))}</b>\n\n"
            f"Статус: <b>{'готова 🟢' if target['status']=='approved' and ready else 'нужна настройка 🟡'}</b>\n"
            f"Сеть: {_NETWORKS.get(target['network'], target['network'])}\n"
            f"География: {geo}\n"
            f"Назначение: {TARGET_PURPOSES.get(target['purpose'], target['purpose'])}\n"
            f"Теги: {', '.join(TARGET_TAGS.get(x, x) for x in tags) or '—'}\n\n"
            f"<b>Проверка готовности</b>\n{checklist}"
        )
        rows = [
            [("1️⃣ Сеть", f"tg:nets:{target_id}"), ("2️⃣ География", f"tg:geo:{target_id}")],
            [("3️⃣ Назначение", f"tg:purpose:{target_id}"), ("4️⃣ Теги", f"tg:tags:{target_id}")],
        ]
        if ready:
            rows.append([("✅ Подтвердить и включить", f"tg:approve:{target_id}")])
        else:
            rows.append([("⚠️ Сначала завершить настройку", "seg:nop")])
        rows.append([("⬅️ К площадкам", "tg:list")])
        await self._edit_or_send(c, text, _kb(rows))

    def _target_country_page(self, target_id: int, region: str, page: int):
        codes = sorted(REGION_COUNTRIES.get(region, []), key=lambda code: WORLD_COUNTRIES[code])
        total = max(1, (len(codes) + _COUNTRY_PAGE - 1) // _COUNTRY_PAGE)
        page = max(0, min(page, total - 1))
        chunk = codes[page * _COUNTRY_PAGE : (page + 1) * _COUNTRY_PAGE]
        rows = []
        buttons = [(_country_label(code), f"tg:c:{target_id}:{code}") for code in chunk]
        for i in range(0, len(buttons), 2):
            rows.append(buttons[i : i + 2])
        nav = []
        if page > 0:
            nav.append(("◀️", f"tg:cp:{target_id}:{region}:{page-1}"))
        nav.append((f"{page+1}/{total}", "seg:nop"))
        if page < total - 1:
            nav.append(("▶️", f"tg:cp:{target_id}:{region}:{page+1}"))
        rows.append(nav)
        rows.append([("⬅️ К регионам", f"tg:gc:{target_id}")])
        return _kb(rows)

    def _register_handlers(self):
        r = self.router

        @r.callback_query(F.data == "seg:nop")
        async def noop(c: CallbackQuery):
            await c.answer()

        @r.callback_query(F.data == "seg:tf")
        async def segment_target_filters(c: CallbackQuery):
            await c.answer()
            st = await self.state_get(c.from_user.id)
            if not st:
                return
            await self._show_target_filters(c, dict(st["payload"] or {}))

        @r.callback_query(F.data.startswith("seg:tn:"))
        async def segment_target_network(c: CallbackQuery):
            await c.answer()
            key = c.data.split(":", 2)[2]
            if key not in _NETWORKS:
                return
            st = await self.state_get(c.from_user.id)
            if not st:
                return
            p = dict(st["payload"] or {})
            segment = p.setdefault("segment", {})
            selected = list(segment.get("target_networks") or ["commission"])
            if key in selected and len(selected) == 1:
                return await c.answer("Оставь хотя бы одну сеть", show_alert=False)
            segment["target_networks"] = [x for x in selected if x != key] if key in selected else selected + [key]
            await self.state_set(c.from_user.id, "segment:builder", p)
            await self._show_target_filters(c, p)

        @r.callback_query(F.data.startswith("seg:tp:"))
        async def segment_target_purpose(c: CallbackQuery):
            await c.answer()
            key = c.data.split(":", 2)[2]
            if key not in TARGET_PURPOSES:
                return
            st = await self.state_get(c.from_user.id)
            if not st:
                return
            p = dict(st["payload"] or {})
            segment = p.setdefault("segment", {})
            selected = list(segment.get("target_purposes") or [])
            segment["target_purposes"] = [x for x in selected if x != key] if key in selected else selected + [key]
            await self.state_set(c.from_user.id, "segment:builder", p)
            await self._show_target_filters(c, p)

        @r.callback_query(F.data.startswith("seg:tt:"))
        async def segment_target_tag(c: CallbackQuery):
            await c.answer()
            key = c.data.split(":", 2)[2]
            if key not in TARGET_TAGS:
                return
            st = await self.state_get(c.from_user.id)
            if not st:
                return
            p = dict(st["payload"] or {})
            segment = p.setdefault("segment", {})
            selected = list(segment.get("target_tags") or [])
            segment["target_tags"] = [x for x in selected if x != key] if key in selected else selected + [key]
            await self.state_set(c.from_user.id, "segment:builder", p)
            await self._show_target_filters(c, p)

        @r.callback_query(F.data == "seg:tglo")
        async def segment_global_targets(c: CallbackQuery):
            await c.answer()
            st = await self.state_get(c.from_user.id)
            if not st:
                return
            p = dict(st["payload"] or {})
            segment = p.setdefault("segment", {})
            segment["include_global_targets"] = not bool(segment.get("include_global_targets"))
            await self.state_set(c.from_user.id, "segment:builder", p)
            await self._show_target_filters(c, p)

        @r.callback_query(F.data == "seg:ch:targets")
        async def segment_targets_toggle(c: CallbackQuery):
            await c.answer()
            st = await self.state_get(c.from_user.id)
            if not st:
                return
            p = dict(st["payload"] or {})
            channels = p.setdefault("channels", {"dm": True, "targets": False})
            channels["targets"] = not bool(channels.get("targets"))
            if channels["targets"]:
                p.setdefault("segment", {}).setdefault("target_networks", ["commission"])
            await self._show_segment_builder(c.message.chat.id, c.from_user.id, p)

        @r.callback_query(F.data == "tg:list")
        async def target_list(c: CallbackQuery):
            await c.answer()
            await self._show_targets(c)

        @r.callback_query(F.data.startswith("tg:open:"))
        async def target_open(c: CallbackQuery):
            await c.answer()
            try:
                target_id = int(c.data.split(":", 2)[2])
            except Exception:
                return
            await self._show_target_card(c, target_id)

        @r.callback_query(F.data.startswith("tg:cr:"))
        async def target_country_region(c: CallbackQuery):
            await c.answer()
            try:
                _, _, tid, region = c.data.split(":", 3)
                target_id = int(tid)
            except Exception:
                return
            if region not in REGION_COUNTRIES:
                return
            await self._edit_or_send(
                c,
                f"<b>{html.escape(REGION_LABELS[region])}</b>\nВыбери страну:",
                self._target_country_page(target_id, region, 0),
            )

        @r.callback_query(F.data.startswith("tg:cp:"))
        async def target_country_page(c: CallbackQuery):
            await c.answer()
            try:
                _, _, tid, region, page = c.data.split(":", 4)
                target_id = int(tid)
                page_num = int(page)
            except Exception:
                return
            if region not in REGION_COUNTRIES:
                return
            await self._edit_or_send(
                c,
                f"<b>{html.escape(REGION_LABELS[region])}</b>\nВыбери страну:",
                self._target_country_page(target_id, region, page_num),
            )

        super()._register_handlers()

    async def run(self):
        """Single-poller startup that survives Render rolling deploy overlap."""
        await self.init_db()
        assert self.pool is not None

        # Render briefly runs old and new instances together. Give the old
        # instance time to drain before touching Telegram getUpdates.
        grace = max(0, int(os.getenv("COMMISSION_ROLLOUT_GRACE_SECONDS", "15") or 15))
        if grace:
            await asyncio.sleep(grace)

        lock_conn = await self.pool.acquire()
        scheduler_task = None
        lock_held = False
        try:
            while True:
                lock_held = bool(
                    await lock_conn.fetchval("SELECT pg_try_advisory_lock($1::bigint)", _SINGLETON_LOCK)
                )
                if lock_held:
                    break
                log.info("Commission poller lock is held by another instance; waiting")
                await asyncio.sleep(2)

            await self.bot.set_my_description(
                "МОЛОДЁЖЬ ВКСРС — единый цифровой центр Комиссии по взаимодействию с молодёжью. Мероприятия и возможности, регистрация, персональные напоминания, списки участников и работа команды — в одном боте."
            )
            await self.bot.set_my_short_description("Мероприятия • регистрация • команда • аналитика")
            await self.bot.delete_webhook(drop_pending_updates=False)
            scheduler_task = asyncio.create_task(self.reminders_loop())
            log.info("Commission singleton poller lock acquired; starting polling")
            await self.dp.start_polling(
                self.bot,
                allowed_updates=self.dp.resolve_used_update_types(),
            )
        finally:
            if scheduler_task is not None:
                scheduler_task.cancel()
                try:
                    await scheduler_task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    log.exception("Commission scheduler shutdown error")
            if lock_held:
                try:
                    await lock_conn.execute("SELECT pg_advisory_unlock($1::bigint)", _SINGLETON_LOCK)
                except Exception:
                    log.exception("Could not release Commission poller lock")
            try:
                await self.pool.release(lock_conn)
            except Exception:
                pass
            if self.pool:
                await self.pool.close()
            await self.bot.session.close()


async def run_commission_bot_hardened(database_url: str) -> None:
    token = os.getenv("COMMISSION_BOT_TOKEN", "").strip()
    if not token:
        log.info("COMMISSION_BOT_TOKEN not set; commission bot disabled")
        return
    bootstrap = os.getenv("COMMISSION_BOOTSTRAP_CODE", "").strip()
    app = CommissionBotHardened(database_url, token, bootstrap)
    await app.run()
