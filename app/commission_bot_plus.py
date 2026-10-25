from __future__ import annotations

from app.commission_bot_plus_base import CommissionBotPlus, ROLE_LABELS, _role_label


async def run_commission_bot_plus(database_url: str) -> None:
    from app.commission_bot_simple_ux import run_commission_bot_simple_ux

    await run_commission_bot_simple_ux(database_url)
