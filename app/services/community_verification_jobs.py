from __future__ import annotations

from app.services.community_verification_service import complete_due_campaigns


async def complete_verification_campaigns_job(session_factory) -> None:
    """Finish expired campaigns without deleting or archiving anyone."""
    async with session_factory() as session:
        await complete_due_campaigns(session)
        await session.commit()
