from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.expert_models import (
    ExpertInviteState,
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
