from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import PointTransaction, User
from app.database.partners import Partner, PartnerInitiative, PartnerOfferApplication
from app.services import opportunity_service


class OpportunityServiceTests(unittest.IsolatedAsyncioTestCase):
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
        )
        defaults.update(overrides)
        user = User(**defaults)
        session.add(user)
        await session.flush()
        return user

    async def _grant_points(self, session, user_id: int, points: int, key: str) -> None:
        session.add(
            PointTransaction(
                user_id=user_id,
                points=points,
                reason="test",
                approved_by=user_id,
                source_type="test",
                idempotency_key=key,
            )
        )
        await session.flush()

    def _partner(self) -> Partner:
        return Partner(name="Acme", description="d")

    def _offer(self, *, partner_id: int, **overrides) -> PartnerInitiative:
        defaults = dict(title="Forum", description="d", point_cost=50)
        defaults.update(overrides)
        return PartnerInitiative(partner_id=partner_id, **defaults)

    async def test_list_active_offers_excludes_inactive_and_expired(self) -> None:
        async with self.session_factory() as session:
            partner = self._partner()
            session.add(partner)
            await session.flush()
            active = self._offer(partner_id=partner.id)
            inactive = self._offer(partner_id=partner.id, is_active=False)
            expired = self._offer(
                partner_id=partner.id,
                expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            )
            session.add_all([active, inactive, expired])
            await session.flush()

            rows = await opportunity_service.list_active_offers(session)
            self.assertEqual([offer.id for offer, _ in rows], [active.id])

    async def test_remaining_slots_none_when_unlimited(self) -> None:
        async with self.session_factory() as session:
            partner = self._partner()
            session.add(partner)
            await session.flush()
            offer = self._offer(partner_id=partner.id, quantity=None)
            session.add(offer)
            await session.flush()
            self.assertIsNone(await opportunity_service.remaining_slots(session, offer))

    async def test_remaining_slots_counts_active_applications(self) -> None:
        async with self.session_factory() as session:
            partner = self._partner()
            session.add(partner)
            await session.flush()
            offer = self._offer(partner_id=partner.id, quantity=2)
            session.add(offer)
            await session.flush()
            user1 = await self._make_user(session, telegram_id=1)
            user2 = await self._make_user(session, telegram_id=2)
            session.add_all(
                [
                    PartnerOfferApplication(initiative_id=offer.id, user_id=user1.id, status="approved"),
                    PartnerOfferApplication(initiative_id=offer.id, user_id=user2.id, status="rejected"),
                ]
            )
            await session.flush()

            slots = await opportunity_service.remaining_slots(session, offer)
            self.assertEqual(slots, 1)

    async def test_apply_to_offer_success(self) -> None:
        async with self.session_factory() as session:
            partner = self._partner()
            session.add(partner)
            await session.flush()
            offer = self._offer(partner_id=partner.id, point_cost=10)
            session.add(offer)
            await session.flush()
            user = await self._make_user(session)
            await self._grant_points(session, user.id, 20, "k1")

            application, error = await opportunity_service.apply_to_offer(session, offer, user)
            self.assertIsNone(error)
            self.assertEqual(application.status, "pending")

    async def test_apply_to_offer_insufficient_points(self) -> None:
        async with self.session_factory() as session:
            partner = self._partner()
            session.add(partner)
            await session.flush()
            offer = self._offer(partner_id=partner.id, point_cost=100)
            session.add(offer)
            await session.flush()
            user = await self._make_user(session)

            application, error = await opportunity_service.apply_to_offer(session, offer, user)
            self.assertIsNone(application)
            self.assertEqual(error, "insufficient_points")

    async def test_apply_to_offer_already_applied(self) -> None:
        async with self.session_factory() as session:
            partner = self._partner()
            session.add(partner)
            await session.flush()
            offer = self._offer(partner_id=partner.id, point_cost=0)
            session.add(offer)
            await session.flush()
            user = await self._make_user(session)
            session.add(
                PartnerOfferApplication(initiative_id=offer.id, user_id=user.id, status="pending")
            )
            await session.flush()

            application, error = await opportunity_service.apply_to_offer(session, offer, user)
            self.assertIsNone(application)
            self.assertEqual(error, "already_applied")

    async def test_apply_to_offer_no_slots(self) -> None:
        async with self.session_factory() as session:
            partner = self._partner()
            session.add(partner)
            await session.flush()
            offer = self._offer(partner_id=partner.id, point_cost=0, quantity=1)
            session.add(offer)
            await session.flush()
            other_user = await self._make_user(session, telegram_id=2)
            session.add(
                PartnerOfferApplication(
                    initiative_id=offer.id, user_id=other_user.id, status="approved"
                )
            )
            await session.flush()
            user = await self._make_user(session, telegram_id=1)

            application, error = await opportunity_service.apply_to_offer(session, offer, user)
            self.assertIsNone(application)
            self.assertEqual(error, "no_slots")

    async def test_apply_to_offer_unavailable(self) -> None:
        async with self.session_factory() as session:
            partner = self._partner()
            session.add(partner)
            await session.flush()
            offer = self._offer(partner_id=partner.id, is_archived=True)
            session.add(offer)
            await session.flush()
            user = await self._make_user(session)

            application, error = await opportunity_service.apply_to_offer(session, offer, user)
            self.assertIsNone(application)
            self.assertEqual(error, "offer_unavailable")

    async def test_rejected_application_can_be_reapplied(self) -> None:
        async with self.session_factory() as session:
            partner = self._partner()
            session.add(partner)
            await session.flush()
            offer = self._offer(partner_id=partner.id, point_cost=0)
            session.add(offer)
            await session.flush()
            user = await self._make_user(session)
            session.add(
                PartnerOfferApplication(
                    initiative_id=offer.id,
                    user_id=user.id,
                    status="rejected",
                    admin_comment="no",
                )
            )
            await session.flush()

            application, error = await opportunity_service.apply_to_offer(session, offer, user)
            self.assertIsNone(error)
            self.assertEqual(application.status, "pending")
            self.assertIsNone(application.admin_comment)

    async def test_save_and_unsave_offer(self) -> None:
        async with self.session_factory() as session:
            partner = self._partner()
            session.add(partner)
            await session.flush()
            offer = self._offer(partner_id=partner.id)
            session.add(offer)
            await session.flush()
            user = await self._make_user(session)

            self.assertFalse(await opportunity_service.is_saved(session, offer.id, user.id))
            await opportunity_service.save_offer(session, offer.id, user.id)
            self.assertTrue(await opportunity_service.is_saved(session, offer.id, user.id))

            saved = await opportunity_service.list_saved_offers(session, user)
            self.assertEqual([o.id for o, _ in saved], [offer.id])

            await opportunity_service.unsave_offer(session, offer.id, user.id)
            self.assertFalse(await opportunity_service.is_saved(session, offer.id, user.id))

    async def test_save_offer_is_idempotent(self) -> None:
        async with self.session_factory() as session:
            partner = self._partner()
            session.add(partner)
            await session.flush()
            offer = self._offer(partner_id=partner.id)
            session.add(offer)
            await session.flush()
            user = await self._make_user(session)

            await opportunity_service.save_offer(session, offer.id, user.id)
            await opportunity_service.save_offer(session, offer.id, user.id)
            saved = await opportunity_service.list_saved_offers(session, user)
            self.assertEqual(len(saved), 1)

    async def test_recommended_offers_excludes_unaffordable_and_full(self) -> None:
        async with self.session_factory() as session:
            partner = self._partner()
            session.add(partner)
            await session.flush()
            affordable = self._offer(partner_id=partner.id, title="Cheap", point_cost=5)
            expensive = self._offer(partner_id=partner.id, title="Expensive", point_cost=500)
            full = self._offer(partner_id=partner.id, title="Full", point_cost=0, quantity=1)
            session.add_all([affordable, expensive, full])
            await session.flush()
            other_user = await self._make_user(session, telegram_id=2)
            session.add(
                PartnerOfferApplication(initiative_id=full.id, user_id=other_user.id, status="approved")
            )
            user = await self._make_user(session, telegram_id=1)
            await self._grant_points(session, user.id, 10, "k1")
            await session.flush()

            recommended = await opportunity_service.recommended_offers(session, user)
            titles = {item.offer.title for item in recommended}
            self.assertEqual(titles, {"Cheap"})
            self.assertTrue(any("баланс" in reason for reason in recommended[0].reasons))

    async def test_recommended_offers_excludes_already_applied(self) -> None:
        async with self.session_factory() as session:
            partner = self._partner()
            session.add(partner)
            await session.flush()
            offer = self._offer(partner_id=partner.id, point_cost=0)
            session.add(offer)
            await session.flush()
            user = await self._make_user(session)
            session.add(
                PartnerOfferApplication(initiative_id=offer.id, user_id=user.id, status="pending")
            )
            await session.flush()

            recommended = await opportunity_service.recommended_offers(session, user)
            self.assertEqual(recommended, [])

    async def test_decide_offer_application_approve_deducts_points_once(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, telegram_id=1)
            participant = await self._make_user(session, telegram_id=2)
            await self._grant_points(session, participant.id, 100, "k1")
            partner = self._partner()
            session.add(partner)
            await session.flush()
            offer = self._offer(partner_id=partner.id, point_cost=30)
            session.add(offer)
            await session.flush()
            application = PartnerOfferApplication(
                initiative_id=offer.id, user_id=participant.id, status="pending"
            )
            session.add(application)
            await session.flush()

            result = await opportunity_service.decide_offer_application(
                session, application, offer, participant, action="approve", actor=admin
            )

            self.assertEqual(application.status, "approved")
            self.assertEqual(result.points_charged, 30)
            self.assertIn("одобрена", result.participant_notice)

            second = await opportunity_service.decide_offer_application(
                session, application, offer, participant, action="approve", actor=admin
            )
            self.assertEqual(second.points_charged, 0)
            self.assertIsNone(second.participant_notice)

    async def test_decide_offer_application_insufficient_balance_leaves_pending(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, telegram_id=1)
            participant = await self._make_user(session, telegram_id=2)
            partner = self._partner()
            session.add(partner)
            await session.flush()
            offer = self._offer(partner_id=partner.id, point_cost=50)
            session.add(offer)
            await session.flush()
            application = PartnerOfferApplication(
                initiative_id=offer.id, user_id=participant.id, status="pending"
            )
            session.add(application)
            await session.flush()

            result = await opportunity_service.decide_offer_application(
                session, application, offer, participant, action="approve", actor=admin
            )

            self.assertEqual(application.status, "pending")
            self.assertEqual(result.points_charged, 0)
            self.assertIn("недостаточно", result.admin_notice)

    async def test_decide_offer_application_reject(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, telegram_id=1)
            participant = await self._make_user(session, telegram_id=2)
            partner = self._partner()
            session.add(partner)
            await session.flush()
            offer = self._offer(partner_id=partner.id, point_cost=10)
            session.add(offer)
            await session.flush()
            application = PartnerOfferApplication(
                initiative_id=offer.id, user_id=participant.id, status="pending"
            )
            session.add(application)
            await session.flush()

            result = await opportunity_service.decide_offer_application(
                session, application, offer, participant, action="reject", actor=admin
            )

            self.assertEqual(application.status, "rejected")
            self.assertIn("отклонена", result.participant_notice)

    async def test_decide_offer_application_unknown_action_raises(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, telegram_id=1)
            participant = await self._make_user(session, telegram_id=2)
            partner = self._partner()
            session.add(partner)
            await session.flush()
            offer = self._offer(partner_id=partner.id)
            session.add(offer)
            await session.flush()
            application = PartnerOfferApplication(
                initiative_id=offer.id, user_id=participant.id, status="pending"
            )
            session.add(application)
            await session.flush()

            with self.assertRaises(ValueError):
                await opportunity_service.decide_offer_application(
                    session, application, offer, participant, action="nope", actor=admin
                )

    async def test_list_pending_offer_applications_filters_by_status(self) -> None:
        async with self.session_factory() as session:
            participant_a = await self._make_user(session, telegram_id=2)
            participant_b = await self._make_user(session, telegram_id=3)
            partner = self._partner()
            session.add(partner)
            await session.flush()
            offer = self._offer(partner_id=partner.id)
            session.add(offer)
            await session.flush()
            pending = PartnerOfferApplication(
                initiative_id=offer.id, user_id=participant_a.id, status="pending"
            )
            approved = PartnerOfferApplication(
                initiative_id=offer.id, user_id=participant_b.id, status="approved"
            )
            session.add_all([pending, approved])
            await session.flush()

            rows = await opportunity_service.list_pending_offer_applications(session)
            self.assertEqual([a.id for a in rows], [pending.id])

    # -- admin catalog CRUD: mirrors app/handlers/admin/partners_admin.py and
    # the create/list/toggle/archive half of partner_offers_block16.py -----

    async def test_create_and_list_partners(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 555)
            partner = await opportunity_service.create_partner(
                session, name="Acme", description="d", source_url=None, created_by_id=admin.id
            )
            self.assertIsNotNone(partner.id)

            rows = await opportunity_service.list_partners(session)
            self.assertEqual([p.id for p in rows], [partner.id])

    async def test_archived_partner_excluded_by_default(self) -> None:
        async with self.session_factory() as session:
            admin = await self._make_user(session, 555)
            partner = await opportunity_service.create_partner(
                session, name="Acme", description="d", source_url=None, created_by_id=admin.id
            )
            opportunity_service.archive_partner(partner)
            await session.flush()

            self.assertEqual(await opportunity_service.list_partners(session), [])
            self.assertEqual(
                [p.id for p in await opportunity_service.list_partners(session, include_archived=True)],
                [partner.id],
            )
            self.assertFalse(partner.is_active)

    async def test_set_partner_active_toggles_flag(self) -> None:
        partner = self._partner()
        opportunity_service.set_partner_active(partner, False)
        self.assertFalse(partner.is_active)
        opportunity_service.set_partner_active(partner, True)
        self.assertTrue(partner.is_active)

    async def test_create_and_list_offers_admin(self) -> None:
        async with self.session_factory() as session:
            partner = self._partner()
            session.add(partner)
            await session.flush()

            offer = await opportunity_service.create_offer(
                session,
                partner_id=partner.id,
                title="Сертификат",
                description="d",
                point_cost=50,
                quantity=10,
                expires_at=None,
                instruction="После одобрения",
                source_url=None,
            )
            self.assertTrue(offer.is_active)
            self.assertFalse(offer.is_archived)

            rows = await opportunity_service.list_offers_admin(session)
            self.assertEqual([(o.id, p.id) for o, p in rows], [(offer.id, partner.id)])

    async def test_get_offer_with_partner(self) -> None:
        async with self.session_factory() as session:
            partner = self._partner()
            session.add(partner)
            await session.flush()
            offer = self._offer(partner_id=partner.id)
            session.add(offer)
            await session.flush()

            row = await opportunity_service.get_offer_with_partner(session, offer.id)
            self.assertIsNotNone(row)
            found_offer, found_partner = row
            self.assertEqual(found_offer.id, offer.id)
            self.assertEqual(found_partner.id, partner.id)

            self.assertIsNone(await opportunity_service.get_offer_with_partner(session, 999999))

    async def test_offer_active_and_archive_toggles(self) -> None:
        offer = self._offer(partner_id=1)
        opportunity_service.set_offer_active(offer, False)
        self.assertFalse(offer.is_active)
        opportunity_service.archive_offer(offer)
        self.assertTrue(offer.is_archived)
        self.assertFalse(offer.is_active)

    async def test_list_offers_admin_excludes_archived_by_default(self) -> None:
        async with self.session_factory() as session:
            partner = self._partner()
            session.add(partner)
            await session.flush()
            visible = self._offer(partner_id=partner.id)
            archived = self._offer(partner_id=partner.id, is_archived=True)
            session.add_all([visible, archived])
            await session.flush()

            rows = await opportunity_service.list_offers_admin(session)
            self.assertEqual([o.id for o, _ in rows], [visible.id])

            rows_all = await opportunity_service.list_offers_admin(session, include_archived=True)
            self.assertEqual({o.id for o, _ in rows_all}, {visible.id, archived.id})

    async def test_list_all_offers_includes_inactive_and_expired(self) -> None:
        # DELTA ToR §16 "Закрыто" state -- list_active_offers alone would
        # never have anything for that filter to show.
        async with self.session_factory() as session:
            partner = self._partner()
            session.add(partner)
            await session.flush()
            active = self._offer(partner_id=partner.id)
            inactive = self._offer(partner_id=partner.id, is_active=False)
            expired = self._offer(
                partner_id=partner.id,
                expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            )
            session.add_all([active, inactive, expired])
            await session.flush()

            active_only = await opportunity_service.list_active_offers(session)
            self.assertEqual({o.id for o, _ in active_only}, {active.id})

            all_offers = await opportunity_service.list_all_offers(session)
            self.assertEqual({o.id for o, _ in all_offers}, {active.id, inactive.id, expired.id})

    async def test_list_offer_facets_excludes_issuers_with_no_active_offers(self) -> None:
        # DELTA ToR §18-19: a legacy Partner row with zero offers (like the
        # old "КСОРС Армении" seed row) must never show up as a filter
        # choice -- facets are derived from what's actually in the active
        # catalog, not from every Partner row that ever existed.
        async with self.session_factory() as session:
            live_partner = Partner(name="Живой партнёр", description="d")
            dead_partner = Partner(name="Мёртвый партнёр", description="d")
            session.add_all([live_partner, dead_partner])
            await session.flush()
            session.add(
                self._offer(
                    partner_id=live_partner.id,
                    opportunity_type="certificate",
                    category="projects",
                )
            )
            await session.flush()

            facets = await opportunity_service.list_offer_facets(session)
            self.assertEqual(facets["issuers"], ["Живой партнёр"])
            self.assertIn("certificate", facets["types"])
            self.assertEqual(facets["categories"], ["projects"])


if __name__ == "__main__":
    unittest.main()
