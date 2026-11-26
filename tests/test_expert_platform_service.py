from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import BigInteger, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.expert_models import (
    ExpertInvite,
    ExpertInviteState,
    ExpertProfile,
    ExpertProfileStatus,
    ExpertSuggestion,
)
from app.database.models import User
from app.services import expert_platform_service as experts
from app.services.expert_platform_service import ExpertPlatformError
from app.utils.constants import ApplicationStatus


class ExpertPlatformServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _user(self, session, telegram_id: int, *, role: str = "participant") -> User:
        user = User(
            telegram_id=telegram_id,
            first_name="User",
            last_name=str(telegram_id),
            phone=f"+374{telegram_id:08d}",
            city="Yerevan",
            education_work="University",
            occupation="Student",
            motivation="Grow",
            available_time="Evenings",
            desired_path="participant",
            personal_data_consent=True,
            is_channel_subscribed=True,
            application_status=ApplicationStatus.APPROVED,
            role=role,
        )
        session.add(user)
        await session.flush()
        return user

    async def test_invite_lifecycle_create_open_claim_without_era_user(self) -> None:
        async with self.session_factory() as session:
            admin = await self._user(session, 900001, role="admin")
            created = await experts.create_invite(
                session, admin=admin, display_name="Анна Эксперт", mark_sent=True
            )
            self.assertEqual(created.invite.state, ExpertInviteState.SENT)
            self.assertEqual(created.profile.status, ExpertProfileStatus.DRAFT)
            self.assertNotEqual(created.token, created.invite.token_hash)

            opened = await experts.mark_invite_opened(session, token=created.token)
            self.assertEqual(opened.state, ExpertInviteState.OPENED)

            # Claim with a Telegram id that has no ERA membership row.
            invite, profile = await experts.claim_invite(
                session, token=created.token, telegram_id=42424242
            )
            self.assertEqual(invite.state, ExpertInviteState.CLAIMED)
            self.assertEqual(invite.claimed_telegram_id, 42424242)
            self.assertEqual(profile.claimed_telegram_id, 42424242)
            self.assertIsNone(profile.user_id)
            self.assertEqual(profile.status, ExpertProfileStatus.DRAFT)

            # Same claimant can re-enter; other telegram cannot.
            again, _ = await experts.claim_invite(
                session, token=created.token, telegram_id=42424242
            )
            self.assertEqual(again.id, invite.id)
            with self.assertRaisesRegex(ExpertPlatformError, "invite_unavailable"):
                await experts.claim_invite(
                    session, token=created.token, telegram_id=99999999
                )

    async def test_claimed_telegram_id_columns_are_bigint_and_hold_64_bit_ids(self) -> None:
        self.assertIsInstance(ExpertProfile.__table__.c.claimed_telegram_id.type, BigInteger)
        self.assertIsInstance(ExpertInvite.__table__.c.claimed_telegram_id.type, BigInteger)
        big_id = 5_000_000_001
        async with self.session_factory() as session:
            admin = await self._user(session, 900010, role="admin")
            created = await experts.create_invite(session, admin=admin, display_name="Большой ID")
            invite, profile = await experts.claim_invite(
                session, token=created.token, telegram_id=big_id
            )
            await session.commit()
            self.assertEqual(invite.claimed_telegram_id, big_id)
            self.assertEqual(profile.claimed_telegram_id, big_id)
        async with self.session_factory() as session:
            stored = await session.scalar(
                select(ExpertProfile.claimed_telegram_id).where(ExpertProfile.id == profile.id)
            )
            self.assertEqual(stored, big_id)

    async def test_second_claimant_cannot_overwrite_first_even_with_stale_read(self) -> None:
        async with self.session_factory() as session:
            admin = await self._user(session, 900011, role="admin")
            created = await experts.create_invite(session, admin=admin, display_name="Гонка")
            await session.commit()
            stale = await session.get(ExpertInvite, created.invite.id)
            stale_state = stale.state
            token = created.token
            profile_id = created.profile.id

        async with self.session_factory() as first:
            await experts.claim_invite(first, token=token, telegram_id=1001)
            await first.commit()

        async with self.session_factory() as second:
            # `stale` above was read while the invite was still CREATED; the
            # conditional UPDATE must still reject this second claimant.
            with self.assertRaisesRegex(ExpertPlatformError, "invite_unavailable"):
                await experts.claim_invite(second, token=token, telegram_id=2002)
            await second.rollback()

        self.assertEqual(stale_state, ExpertInviteState.CREATED)
        async with self.session_factory() as session:
            invite = await session.scalar(select(ExpertInvite).where(ExpertInvite.id == created.invite.id))
            profile = await session.get(ExpertProfile, profile_id)
            self.assertEqual(invite.state, ExpertInviteState.CLAIMED)
            self.assertEqual(invite.claimed_telegram_id, 1001)
            self.assertEqual(profile.claimed_telegram_id, 1001)

    async def test_concurrent_claims_have_exactly_one_winner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            url = "sqlite+aiosqlite:///" + os.path.join(tmp, "experts.db")
            engine = create_async_engine(url)
            try:
                async with engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
                factory = async_sessionmaker(engine, expire_on_commit=False)
                async with factory() as session:
                    admin = await self._user(session, 900012, role="admin")
                    created = await experts.create_invite(session, admin=admin, display_name="Параллель")
                    await session.commit()
                    token, invite_id, profile_id = created.token, created.invite.id, created.profile.id

                async def attempt(tg_id: int):
                    async with factory() as session:
                        try:
                            await experts.claim_invite(session, token=token, telegram_id=tg_id)
                            await session.commit()
                            return tg_id
                        except ExpertPlatformError as exc:
                            await session.rollback()
                            return str(exc)

                results = await asyncio.gather(*(attempt(t) for t in (3001, 3002, 3003)))
                winners = [r for r in results if isinstance(r, int)]
                self.assertEqual(len(winners), 1)
                self.assertEqual(results.count("invite_unavailable"), 2)

                async with factory() as session:
                    invite = await session.get(ExpertInvite, invite_id)
                    profile = await session.get(ExpertProfile, profile_id)
                    self.assertEqual(invite.claimed_telegram_id, winners[0])
                    self.assertEqual(profile.claimed_telegram_id, winners[0])
            finally:
                await engine.dispose()

    async def test_revoke_after_claim_is_rejected_and_claim_is_preserved(self) -> None:
        async with self.session_factory() as session:
            admin = await self._user(session, 900013, role="admin")
            created = await experts.create_invite(session, admin=admin, display_name="Claimed")
            await experts.claim_invite(session, token=created.token, telegram_id=4004)
            with self.assertRaisesRegex(ExpertPlatformError, "invite_already_claimed"):
                await experts.revoke_invite(session, invite_id=created.invite.id, admin=admin)
            self.assertEqual(created.invite.state, ExpertInviteState.CLAIMED)


    async def test_expired_and_revoked_invites_are_unavailable(self) -> None:
        async with self.session_factory() as session:
            admin = await self._user(session, 900002, role="admin")
            created = await experts.create_invite(
                session, admin=admin, display_name="Иван", ttl_hours=1
            )
            created.invite.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            await session.flush()
            with self.assertRaisesRegex(ExpertPlatformError, "invite_unavailable"):
                await experts.claim_invite(
                    session, token=created.token, telegram_id=111
                )
            self.assertEqual(created.invite.state, ExpertInviteState.EXPIRED)

            fresh = await experts.create_invite(
                session, admin=admin, display_name="Мария"
            )
            await experts.revoke_invite(session, invite_id=fresh.invite.id, admin=admin)
            with self.assertRaisesRegex(ExpertPlatformError, "invite_unavailable"):
                await experts.claim_invite(
                    session, token=fresh.token, telegram_id=111
                )

    async def test_published_list_excludes_drafts(self) -> None:
        async with self.session_factory() as session:
            admin = await self._user(session, 900003, role="admin")
            draft = await experts.create_invite(
                session, admin=admin, display_name="Черновик"
            )
            published = await experts.create_invite(
                session, admin=admin, display_name="Публичный"
            )
            await experts.publish_expert_profile(
                session, profile_id=published.profile.id, admin=admin
            )
            listed = await experts.list_published_experts(session)
            names = [item.display_name for item in listed]
            self.assertEqual(names, ["Публичный"])
            self.assertIsNone(
                await experts.get_published_expert(session, draft.profile.id)
            )
            found = await experts.get_published_expert(session, published.profile.id)
            self.assertIsNotNone(found)
            public = experts.serialize_published_expert(found)
            self.assertNotIn("claimed_telegram_id", public)
            self.assertNotIn("user_id", public)

    async def test_suggestion_omits_contact_and_rate_limits(self) -> None:
        async with self.session_factory() as session:
            nominator = await self._user(session, 800001)
            suggestion = await experts.suggest_expert(
                session,
                nominator=nominator,
                expert_name="Профессор",
                field="Образование",
                why_interesting="Сильные лекции",
                contact_private="secret@example.com",
                consent_given=True,
            )
            ack = experts.serialize_suggestion_ack(suggestion)
            self.assertNotIn("contact_private", ack)
            self.assertEqual(ack["expert_name"], "Профессор")
            stored = await session.get(ExpertSuggestion, suggestion.id)
            self.assertEqual(stored.contact_private, "secret@example.com")

            now = datetime.now(timezone.utc)
            for index in range(experts.SUGGESTION_RATE_LIMIT - 1):
                await experts.suggest_expert(
                    session,
                    nominator=nominator,
                    expert_name=f"Expert {index}",
                    field="Наука",
                    why_interesting="Полезен",
                    contact_private=f"c{index}@example.com",
                    consent_given=True,
                    now=now,
                )
            with self.assertRaisesRegex(ExpertPlatformError, "suggestion_rate_limited"):
                await experts.suggest_expert(
                    session,
                    nominator=nominator,
                    expert_name="Too many",
                    field="Наука",
                    why_interesting="Полезен",
                    contact_private="limit@example.com",
                    consent_given=True,
                    now=now,
                )


if __name__ == "__main__":
    unittest.main()
