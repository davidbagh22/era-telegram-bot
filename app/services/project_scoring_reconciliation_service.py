from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Project, ProjectMember, ProjectMilestone
from app.services.activity_scoring_service import (
    score_project_completion,
    score_project_contribution,
    score_project_milestone,
)

logger = logging.getLogger(__name__)


async def reconcile_project_scoring(session: AsyncSession, *, limit: int = 300) -> int:
    """Idempotently reconcile verified project facts into the scoring engine.

    Project workspace is an older, large subsystem with several independent
    confirmation paths. Rather than duplicate scoring calls in each path, this
    reconciler consumes their durable verified state. It also safely backfills
    historical confirmed facts because every award has its own idempotency key.
    """
    processed = 0

    members = list(
        (
            await session.scalars(
                select(ProjectMember)
                .where(ProjectMember.contribution_status == "confirmed")
                .order_by(ProjectMember.id)
                .limit(limit)
            )
        ).all()
    )
    for member in members:
        project = await session.get(Project, member.project_id)
        if project is None:
            continue
        await score_project_contribution(
            session,
            project,
            member,
            approved_by_id=member.contribution_confirmed_by,
        )
        processed += 1

    milestones = list(
        (
            await session.scalars(
                select(ProjectMilestone)
                .where(
                    ProjectMilestone.status == "completed",
                    ProjectMilestone.responsible_id.is_not(None),
                )
                .order_by(ProjectMilestone.id)
                .limit(limit)
            )
        ).all()
    )
    for milestone in milestones:
        project = await session.get(Project, milestone.project_id)
        if project is None:
            continue
        await score_project_milestone(
            session,
            project,
            milestone,
            approved_by_id=milestone.completed_by,
        )
        processed += 1

    completed_projects = list(
        (
            await session.scalars(
                select(Project)
                .where(Project.status == "completed")
                .order_by(Project.id)
                .limit(limit)
            )
        ).all()
    )
    for project in completed_projects:
        # Project has no generic ``approved_by`` field. The author is the
        # durable accountable actor available on every project and is used
        # only for audit attribution; scoring eligibility still comes from
        # verified members/milestones and the completed project state.
        await score_project_completion(
            session,
            project,
            approved_by_id=project.author_id,
        )
        processed += 1

    await session.flush()
    return processed


async def reconcile_project_scoring_job(session_factory) -> None:
    try:
        async with session_factory() as session:
            await reconcile_project_scoring(session)
            await session.commit()
    except Exception:
        logger.exception("project scoring reconciliation failed")
