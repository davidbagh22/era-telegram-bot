from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import PointTransaction, PortfolioItem, Task, User
from app.database.partners import Partner, PartnerInitiative, PartnerOfferApplication
from app.services.activity_metrics_service import get_metric, increment_metric
from app.services.activity_scoring_service import score_task_completion
from app.services.opportunity_service import decide_offer_application, evaluate_eligibility
from app.services.points_service import total_points
from app.services.progression_service import promote_participation_status
from app.utils.constants import ParticipationStatus, Role


class ProgressionAndRecognitionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _user(self, session, telegram_id: int, **overrides) -> User:
        data = {
            "telegram_id": telegram_id,
            "first_name": f"U{telegram_id}",
            "role": Role.PARTICIPANT,
            "participation_status": ParticipationStatus.NEW_MEMBER,
        }
        data.update(overrides)
        user = User(**data)
        session.add(user)
        await session.flush()
        return user

    async def test_points_alone_never_promote_rank(self) -> None:
        async with self.session_factory() as session:
            user = await self._user(session, 1)
            session.add(
                PointTransaction(
                    user_id=user.id,
                    points=9000,
                    reason="legacy points",
                    source_type="test",
                    idempotency_key="points-only",
                )
            )
            await session.flush()
            changed = await promote_participation_status(session, user_id=user.id)
            self.assertIsNone(changed)
            self.assertEqual(user.participation_status, ParticipationStatus.NEW_MEMBER)

    async def test_verified_activity_promotes_using_existing_status_enum(self) -> None:
        async with self.session_factory() as session:
            user = await self._user(session, 1)
            await increment_metric(
                session, user_id=user.id, metric_key="events_attended", delta=1
            )
            await promote_participation_status(session, user_id=user.id)
            self.assertEqual(
                user.participation_status, ParticipationStatus.INVOLVED_MEMBER
            )

    async def test_task_completion_is_idempotent_and_updates_metrics(self) -> None:
        async with self.session_factory() as session:
            admin = await self._user(session, 1)
            participant = await self._user(session, 2)
            task = Task(
                title="Media task",
                description="Make a reel",
                creator_id=admin.id,
                assignee_id=participant.id,
                deadline=datetime.now().astimezone() + timedelta(days=1),
                points=100,
                reward_json={"counts_toward": ["media"]},
            )
            session.add(task)
            await session.flush()

            first = await score_task_completion(
                session,
                task,
                participant,
                submission_id=10,
                approved_by_id=admin.id,
            )
            second = await score_task_completion(
                session,
                task,
                participant,
                submission_id=10,
                approved_by_id=admin.id,
            )
            self.assertEqual(first.id, second.id)
            self.assertEqual(await total_points(session, participant.id), 100)
            self.assertEqual(
                await get_metric(session, user_id=participant.id, metric_key="media_activities"),
                1,
            )
            self.assertEqual(
                await get_metric(session, user_id=participant.id, metric_key="tasks_completed"),
                1,
            )

    async def test_role_multiplier_only_for_role_scoped_task(self) -> None:
        async with self.session_factory() as session:
            admin = await self._user(session, 1)
            leader = await self._user(session, 2, role=Role.LEADER)
            ordinary = Task(
                title="Ordinary",
                description="d",
                creator_id=admin.id,
                assignee_id=leader.id,
                deadline=datetime.now().astimezone() + timedelta(days=1),
                points=100,
                reward_json={},
            )
            scoped = Task(
                title="Leadership duty",
                description="d",
                creator_id=admin.id,
                assignee_id=leader.id,
                deadline=datetime.now().astimezone() + timedelta(days=1),
                points=100,
                reward_json={
                    "role_scoped": True,
                    "counts_toward": ["leadership"],
                },
            )
            session.add_all([ordinary, scoped])
            await session.flush()
            a = await score_task_completion(
                session,
                ordinary,
                leader,
                submission_id=1,
                approved_by_id=admin.id,
            )
            b = await score_task_completion(
                session,
                scoped,
                leader,
                submission_id=2,
                approved_by_id=admin.id,
            )
            self.assertEqual(a.points, 100)
            self.assertEqual(b.points, 110)

    async def test_8000_points_without_volunteer_hours_is_not_eligible(self) -> None:
        async with self.session_factory() as session:
            user = await self._user(
                session,
                1,
                participation_status=ParticipationStatus.COMMUNITY_LEADER,
            )
            session.add(
                PointTransaction(
                    user_id=user.id,
                    points=8000,
                    reason="test",
                    source_type="test",
                    idempotency_key="8k",
                )
            )
            partner = Partner(name="Association", description="d")
            session.add(partner)
            await session.flush()
            offer = PartnerInitiative(
                partner_id=partner.id,
                title="Volunteer certificate",
                description="d",
                point_cost=2500,
                opportunity_type="certificate",
                min_rank=ParticipationStatus.ACTIVE_MEMBER,
                eligibility_json={"required_metrics": {"volunteer_hours": 20}},
            )
            session.add(offer)
            await session.flush()
            result = await evaluate_eligibility(session, offer, user)
            self.assertFalse(result.eligible)
            self.assertIn("часов волонтёрства", result.missing)

    async def test_recognition_approval_never_spends_points(self) -> None:
        async with self.session_factory() as session:
            admin = await self._user(session, 1)
            user = await self._user(
                session,
                2,
                participation_status=ParticipationStatus.ACTIVE_MEMBER,
            )
            session.add(
                PointTransaction(
                    user_id=user.id,
                    points=3000,
                    reason="earned",
                    source_type="test",
                    idempotency_key="earned",
                )
            )
            partner = Partner(name="ERA", description="d")
            session.add(partner)
            await session.flush()
            offer = PartnerInitiative(
                partner_id=partner.id,
                title="Active member",
                description="d",
                point_cost=1500,
                opportunity_type="certificate",
                min_rank=ParticipationStatus.ACTIVE_MEMBER,
                default_award_wording="For contribution",
            )
            session.add(offer)
            await session.flush()
            application = PartnerOfferApplication(
                initiative_id=offer.id,
                user_id=user.id,
                status="requested",
            )
            session.add(application)
            await session.flush()

            before = await total_points(session, user.id)
            result = await decide_offer_application(
                session,
                application,
                offer,
                user,
                action="approve",
                actor=admin,
            )
            after = await total_points(session, user.id)
            self.assertEqual(result.points_charged, 0)
            self.assertEqual(before, after)
            self.assertEqual(application.status, "approved")

    async def test_partner_document_requires_partner_review(self) -> None:
        async with self.session_factory() as session:
            admin = await self._user(session, 1)
            user = await self._user(
                session,
                2,
                participation_status=ParticipationStatus.ACTIVE_MEMBER,
            )
            partner = Partner(name="Partner", description="d")
            session.add(partner)
            await session.flush()
            offer = PartnerInitiative(
                partner_id=partner.id,
                title="Partner document",
                description="d",
                point_cost=0,
                opportunity_type="certificate",
                partner_review_required=True,
            )
            session.add(offer)
            await session.flush()
            application = PartnerOfferApplication(
                initiative_id=offer.id,
                user_id=user.id,
                status="requested",
            )
            session.add(application)
            await session.flush()
            await decide_offer_application(
                session,
                application,
                offer,
                user,
                action="approve",
                actor=admin,
            )
            self.assertEqual(application.status, "partner_review")

    async def test_issue_adds_existing_portfolio_item_once(self) -> None:
        async with self.session_factory() as session:
            admin = await self._user(session, 1)
            user = await self._user(
                session,
                2,
                participation_status=ParticipationStatus.ACTIVE_MEMBER,
            )
            partner = Partner(name="ERA", description="d")
            session.add(partner)
            await session.flush()
            offer = PartnerInitiative(
                partner_id=partner.id,
                title="Certificate X",
                description="d",
                point_cost=0,
                opportunity_type="certificate",
            )
            session.add(offer)
            await session.flush()
            application = PartnerOfferApplication(
                initiative_id=offer.id,
                user_id=user.id,
                status="approved",
                award_wording="Verified contribution",
            )
            session.add(application)
            await session.flush()

            await decide_offer_application(
                session,
                application,
                offer,
                user,
                action="issue",
                actor=admin,
            )
            first_item_id = application.portfolio_item_id
            await decide_offer_application(
                session,
                application,
                offer,
                user,
                action="issue",
                actor=admin,
            )
            items = list(
                (
                    await session.scalars(
                        select(PortfolioItem).where(
                            PortfolioItem.user_id == user.id,
                            PortfolioItem.title == offer.title,
                        )
                    )
                ).all()
            )
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].id, first_item_id)


if __name__ == "__main__":
    unittest.main()
