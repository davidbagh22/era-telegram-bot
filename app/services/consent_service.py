"""Consent audit trail for the approved ERA registration policy.

`User.personal_data_consent` remains the fast boolean used by existing
application logic. `ConsentLog` is the audit trail that records which
version of the actual user-visible policy was accepted and when.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ConsentLog
from app.services.consent_policy import CONSENT_POLICY_VERSION

CURRENT_POLICY_VERSION = CONSENT_POLICY_VERSION


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
