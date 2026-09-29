from __future__ import annotations

from app.commission_bot_plus_base import CommissionBotPlus, _role_label


async def run_commission_bot_plus(database_url: str) -> None:
    from app.commission_bot_analytics import run_commission_bot_analytics

    await run_commission_bot_analytics(database_url)
