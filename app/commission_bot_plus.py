from __future__ import annotations

from app.commission_bot_plus_base import CommissionBotPlus, _role_label


async def run_commission_bot_plus(database_url: str) -> None:
    from app.commission_bot_hardened import run_commission_bot_hardened

    await run_commission_bot_hardened(database_url)
