from __future__ import annotations

import logging

from app.services.office_management_service import reconcile_all_vacancies

logger = logging.getLogger(__name__)


async def reconcile_vacancies_job(session_factory) -> dict[str, int]:
    """Idempotently align public vacancy visibility with Office capacity.

    Office/UserOffice remain the source of truth. The job never creates,
    deletes or reassigns offices; it only reconciles application_enabled for
    offices with an explicit max_holders capacity.
    """
    async with session_factory() as session:
        result = await reconcile_all_vacancies(session)
        await session.commit()
    logger.info(
        "Vacancy reconciliation complete opened=%s closed=%s unchanged=%s total=%s",
        result["opened"],
        result["closed"],
        result["unchanged"],
        result["total"],
    )
    return result
