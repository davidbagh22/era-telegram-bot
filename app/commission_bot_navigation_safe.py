from __future__ import annotations

import logging
import os

from app.commission_bot_navigation import CommissionBotNavigation

log = logging.getLogger(__name__)


class CommissionBotNavigationSafe(CommissionBotNavigation):
    async def _go_back(self, chat_id: int, uid: int) -> None:
        st = await self.state_get(uid)
        if not st or not str(st["state"]).startswith("b:"):
            user = await self.fetchrow("SELECT * FROM users WHERE telegram_id=$1", uid)
            if user:
                await self.send_menu(chat_id, user, "Вы уже в начале.")
            else:
                await self.bot.send_message(chat_id, "Нажмите /start, чтобы открыть меню.")
            return
        await super()._go_back(chat_id, uid)


async def run_commission_bot_navigation_safe(database_url: str) -> None:
    token = os.getenv("COMMISSION_BOT_TOKEN", "").strip()
    if not token:
        log.info("COMMISSION_BOT_TOKEN not set; commission bot disabled")
        return
    bootstrap = os.getenv("COMMISSION_BOOTSTRAP_CODE", "").strip()
    app = CommissionBotNavigationSafe(database_url, token, bootstrap)
    await app.run()
