from __future__ import annotations

import unittest
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import (
    Event,
    EventRegistration,
    PointTransaction,
    PortfolioItem,
    Project,
    Task,
    User,
)
from app.database.partners import Partner, PartnerInitiative, PartnerOfferApplication
from app.services.home_service import build_home_snapshot
from app.utils.constants import ParticipationStatus, ProjectStatus, RegistrationStatus, TaskStatus


class HomeServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _make_user(self, session, telegram_id: int = 1, **overrides) -> User:
        defaults = dict(
            telegram_id=telegram_id,
            first_name="Dev",
            last_name=None,
            phone="+10000000000",
            city="City",
            education_work="Work",
            occupation="Occupation",
            motivation="Motivation",
            available_time="Evenings",
            desired_path="participant",
            personal_data_consent=True,
            is_channel_subscribed=True,
            participation_status=ParticipationStatus.NEW_MEMBER,
        )
        defaults.update(overrides)
        user = User(**defaults)
        session.add(user)
        await session.flush()
        return user

    async def test_active_task_takes_priority_over_everything_else(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            task = Task(
                title="Submit report",
                description="d",
                assignee_id=user.id,
                creator_id=user.id,
                deadline=datetime.now(timezone.utc) + timedelta(days=1),
                points=10,
                status=TaskStatus.IN_PROGRESS,
            )
            session.add(task)
            await session.flush()

            snapshot = await build_home_snapshot(session, user)

            self.assertIsNotNone(snapshot.next_step)
            self.assertEqual(snapshot.next_step.kind, "task")
            # DELTA ToR §6: next_step must carry a real, actionable target.
            self.assertEqual(snapshot.next_step.entity_id, task.id)
            self.assertEqual(snapshot.next_step.route, f"/tasks/{task.id}")
            self.assertIsNotNone(snapshot.active_task)
            self.assertEqual(snapshot.active_task.id, task.id)
            self.assertIsNone(snapshot.nearest_event)

    async def test_nearest_registered_event_when_no_active_task(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            event = Event(
                title="Meetup",
                description="d",
                event_date=date.today() + timedelta(days=3),
                event_time=time(18, 0),
                location="HQ",
                format="offline",
                created_by=user.id,
            )
            session.add(event)
            await session.flush()
            session.add(
                EventRegistration(
                    event_id=event.id, user_id=user.id, status=RegistrationStatus.REGISTERED
                )
            )
            await session.flush()

            snapshot = await build_home_snapshot(session, user)

            self.assertEqual(snapshot.next_step.kind, "event")
            self.assertEqual(snapshot.next_step.entity_id, event.id)
            self.assertEqual(snapshot.next_step.route, f"/events/{event.id}")
            self.assertIsNotNone(snapshot.nearest_event)
            self.assertEqual(snapshot.nearest_event.id, event.id)

    async def test_past_event_registration_is_ignored(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            event = Event(
                title="Old meetup",
                description="d",
                event_date=date.today() - timedelta(days=3),
                event_time=time(18, 0),
                location="HQ",
                format="offline",
                created_by=user.id,
            )
            session.add(event)
            await session.flush()
            session.add(
                EventRegistration(
                    event_id=event.id, user_id=user.id, status=RegistrationStatus.ATTENDED
                )
            )
            await session.flush()

            snapshot = await build_home_snapshot(session, user)
            self.assertIsNone(snapshot.nearest_event)

    async def test_draft_project_is_next_step_when_no_task_or_event(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            project = Project(
                author_id=user.id,
                title="New Idea",
                short_description="d",
                status=ProjectStatus.DRAFT,
            )
            session.add(project)
            await session.flush()

            snapshot = await build_home_snapshot(session, user)

            self.assertEqual(snapshot.next_step.kind, "project")
            self.assertIn("оставшиеся блоки", snapshot.next_step.description)
            self.assertEqual(snapshot.next_step.entity_id, project.id)
            self.assertEqual(snapshot.next_step.route, f"/projects/{project.id}")
            self.assertEqual(snapshot.active_project.id, project.id)

    async def test_needs_revision_project_has_different_hint(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            project = Project(
                author_id=user.id,
                title="Reworked Idea",
                short_description="d",
                status=ProjectStatus.NEEDS_REVISION,
            )
            session.add(project)
            await session.flush()

            snapshot = await build_home_snapshot(session, user)
            self.assertIn("доработку", snapshot.next_step.description)

    async def test_growth_nudge_when_nothing_actionable_and_not_leader(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(
                session, participation_status=ParticipationStatus.ACTIVE_MEMBER
            )
            snapshot = await build_home_snapshot(session, user)
            self.assertEqual(snapshot.next_step.kind, "growth")
            self.assertEqual(snapshot.growth.level, "active")
            # No single entity backs a growth nudge -- the frontend falls
            # back to its "growth" kind handler (opens the Vector screen).
            self.assertIsNone(snapshot.next_step.entity_id)
            self.assertEqual(snapshot.next_step.route, "/development")

    async def test_opportunity_suggested_for_leader_with_nothing_else(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(
                session, participation_status=ParticipationStatus.COMMUNITY_LEADER
            )
            partner = Partner(name="Acme", description="d")
            session.add(partner)
            await session.flush()
            initiative = PartnerInitiative(
                partner_id=partner.id,
                title="Forum",
                description="d",
                point_cost=50,
            )
            session.add(initiative)
            await session.flush()

            snapshot = await build_home_snapshot(session, user)

            self.assertEqual(snapshot.next_step.kind, "opportunity")
            self.assertEqual(snapshot.next_step.entity_id, initiative.id)
            self.assertEqual(snapshot.next_step.route, f"/opportunities/{initiative.id}")
            self.assertEqual(len(snapshot.opportunities), 1)
            self.assertEqual(snapshot.opportunities[0].id, initiative.id)

    async def test_leader_with_nothing_actionable_has_no_next_step(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(
                session, participation_status=ParticipationStatus.COMMUNITY_LEADER
            )
            snapshot = await build_home_snapshot(session, user)
            self.assertIsNone(snapshot.next_step)

    async def test_applied_opportunities_are_excluded(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(
                session, participation_status=ParticipationStatus.COMMUNITY_LEADER
            )
            partner = Partner(name="Acme", description="d")
            session.add(partner)
            await session.flush()
            initiative = PartnerInitiative(
                partner_id=partner.id, title="Forum", description="d", point_cost=50
            )
            session.add(initiative)
            await session.flush()
            session.add(
                PartnerOfferApplication(initiative_id=initiative.id, user_id=user.id)
            )
            await session.flush()

            snapshot = await build_home_snapshot(session, user)
            self.assertEqual(snapshot.opportunities, [])

    async def test_expired_opportunities_are_excluded(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(
                session, participation_status=ParticipationStatus.COMMUNITY_LEADER
            )
            partner = Partner(name="Acme", description="d")
            session.add(partner)
            await session.flush()
            initiative = PartnerInitiative(
                partner_id=partner.id,
                title="Expired Forum",
                description="d",
                point_cost=50,
                expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            )
            session.add(initiative)
            await session.flush()

            snapshot = await build_home_snapshot(session, user)
            self.assertEqual(snapshot.opportunities, [])

    async def test_points_balance_sums_transactions(self) -> None:
        async with self.session_factory() as session:
            user = await self._make_user(session)
            session.add_all(
                [
                    PointTransaction(
                        user_id=user.id,
                        points=10,
                        reason="a",
                        approved_by=user.id,
                        source_type="test",
                        source_id=1,
                        idempotency_key="k1",
                    ),
                    PointTransaction(
                        user_id=user.id,
                        points=-3,
                        reason="b",
                        approved_by=user.id,
                        source_type="test",
                        source_id=2,
                        idempotency_key="k2",
                    ),
                ]
            )
            await session.flush()

            snapshot = await build_home_snapshot(session, user)
            self.assertEqual(snapshot.points_balance, 7)

    async def test_activity_stats_reuse_user_stats_not_a_second_query(self) -> None:
        # PR 38: Home's "Моя активность" section reuses
        # app/repositories/users.py::user_stats() — the same numbers
        # Profile's stat grid shows — rather than a separate computation,
        # so the two screens can never disagree.
        async with self.session_factory() as session:
            user = await self._make_user(session)
            session.add(
                PointTransaction(
                    user_id=user.id,
                    points=25,
                    reason="a",
                    approved_by=user.id,
                    source_type="test",
                    source_id=1,
                    idempotency_key="k1",
                )
            )
            session.add(
                Project(author_id=user.id, title="Idea", short_description="d", status=ProjectStatus.DRAFT)
            )
            session.add(
                Task(
                    title="Done task",
                    description="d",
                    assignee_id=user.id,
                    creator_id=user.id,
                    deadline=datetime.now(timezone.utc) + timedelta(days=1),
                    points=5,
                    status=TaskStatus.COMPLETED,
                )
            )
            session.add(PortfolioItem(user_id=user.id, title="Item", item_type="badge"))
            await session.flush()

            snapshot = await build_home_snapshot(session, user)

            self.assertEqual(snapshot.activity.points, 25)
            self.assertEqual(snapshot.activity.projects, 1)
            self.assertEqual(snapshot.activity.completed_tasks, 1)
            self.assertEqual(snapshot.activity.portfolio_items, 1)
            # points_balance stays in sync with activity.points (same
            # underlying user_stats() call, not two separate queries that
            # could drift).
            self.assertEqual(snapshot.points_balance, snapshot.activity.points)


if __name__ == "__main__":
    unittest.main()
