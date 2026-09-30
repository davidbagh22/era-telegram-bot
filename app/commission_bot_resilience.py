from __future__ import annotations

import logging
import os

from aiogram import F
from aiogram.dispatcher.event.bases import SkipHandler

from app.commission_bot_online_only import CommissionBotOnlineOnly

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


class CommissionBotResilient(CommissionBotOnlineOnly):
    def _register_handlers(self):
        r = self.router

        @r.callback_query(F.data.in_(TOP_LEVEL_CALLBACKS))
        async def clear_stale_state_before_navigation(c):
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

        super()._register_handlers()


async def run_commission_bot_resilient(database_url: str) -> None:
    token = os.getenv("COMMISSION_BOT_TOKEN", "").strip()
    if not token:
        log.info("COMMISSION_BOT_TOKEN not set; commission bot disabled")
        return
    bootstrap = os.getenv("COMMISSION_BOOTSTRAP_CODE", "").strip()
    app = CommissionBotResilient(database_url, token, bootstrap)
    await app.run()
