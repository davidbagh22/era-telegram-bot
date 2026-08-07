"""Consent audit trail — technical foundation, not a policy decision.

`CURRENT_POLICY_VERSION` is a placeholder string, not real policy text.
Nothing in this module writes, validates, or enforces policy content —
that requires real text from the platform owner (see
docs/DATA_INVENTORY.md section 5, docs/PRODUCTION_READINESS_AUDIT.md
finding #16). This only makes sure that whenever a real policy exists,
switching this one constant is enough to start recording consent against
it, with every past record still showing which version it was actually
given under.

`User.personal_data_consent` (bare bool) remains the field the app
actually checks anywhere — `record_consent()` is purely additive
logging, called alongside it, not a replacement.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ConsentLog

CURRENT_POLICY_VERSION = "unset-v1"


async def record_consent(
    session: AsyncSession,
    *,
    user_id: int,
    consent_type: str,
    granted: bool,
    source: str,
    policy_version: str = CURRENT_POLICY_VERSION,
) -> ConsentLog:
    entry = ConsentLog(
        user_id=user_id,
        consent_type=consent_type,
        policy_version=policy_version,
        granted=granted,
        source=source,
    )
    session.add(entry)
    await session.flush()
    return entry


async def latest_consent(
    session: AsyncSession, *, user_id: int, consent_type: str
) -> ConsentLog | None:
    return await session.scalar(
        select(ConsentLog)
        .where(ConsentLog.user_id == user_id, ConsentLog.consent_type == consent_type)
        .order_by(ConsentLog.created_at.desc(), ConsentLog.id.desc())
        .limit(1)
    )
