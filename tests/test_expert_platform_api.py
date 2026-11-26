from __future__ import annotations

import hashlib
import hmac
import json
import time
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_current_user, get_session, get_settings
from app.api.v1.router import api_router
from app.config import Settings
from app.database.base import Base
from app.database.models import User
from app.services import expert_platform_service as experts
from app.services.feature_flags import Feature, visible_features
from app.utils.constants import ApplicationStatus


BOT_TOKEN = "1234567890:test-token-for-experts"


def _settings(**overrides) -> Settings:
    defaults = dict(
        bot_token=BOT_TOKEN,
        miniapp_auth_secret="test-secret",
        experts_platform_enabled=True,
        admin_ids=[555],
        dev_auth_enabled=False,
    )
    defaults.update(overrides)
    return Settings(**defaults)


def _init_data(telegram_id: int, bot_token: str = BOT_TOKEN) -> str:
    user = json.dumps(
        {"id": telegram_id, "first_name": "Guest", "username": "guest"},
        separators=(",", ":"),
    )
    pairs = {
        "auth_date": str(int(time.time())),
        "user": user,
        "query_id": "AAE",
    }
    check_string = "\n".join(f"{key}={value}" for key, value in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
    return "&".join(f"{key}={value}" for key, value in pairs.items())


class ExpertPlatformApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

        async with self.session_factory() as session:
            self.admin = User(
                telegram_id=555,
                first_name="Admin",
                last_name="ERA",
                phone="+37400000001",
                city="Yerevan",
                education_work="ERA",
                occupation="Admin",
                motivation="Lead",
                available_time="Any",
                desired_path="admin",
                personal_data_consent=True,
                is_channel_subscribed=True,
                application_status=ApplicationStatus.APPROVED,
                role="admin",
            )
            self.participant = User(
                telegram_id=777,
                first_name="Участник",
                last_name="ЭРА",
                phone="+37400000002",
                city="Yerevan",
                education_work="University",
                occupation="Student",
                motivation="Grow",
                available_time="Evenings",
                desired_path="participant",
                personal_data_consent=True,
                is_channel_subscribed=True,
                application_status=ApplicationStatus.APPROVED,
                role="participant",
            )
            session.add_all([self.admin, self.participant])
            await session.commit()
            await session.refresh(self.admin)
            await session.refresh(self.participant)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    def _app(self, user: User | None, *, enabled: bool = True) -> FastAPI:
        app = FastAPI()
        app.include_router(api_router)
        session_factory = self.session_factory

        async def _session_override():
            async with session_factory() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        if user is not None:
            app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = _session_override
        app.dependency_overrides[get_settings] = lambda: _settings(
            experts_platform_enabled=enabled
        )
        return app

    def test_flag_off_returns_404_for_list_and_admin_invite(self) -> None:
        client = TestClient(self._app(self.participant, enabled=False))
        self.assertEqual(client.get("/api/v1/experts").status_code, 404)
        admin_client = TestClient(self._app(self.admin, enabled=False))
        response = admin_client.post(
            "/api/v1/experts/invites",
            json={"display_name": "Hidden"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "feature_unavailable")

    async def test_list_requires_auth_and_hides_drafts(self) -> None:
        async with self.session_factory() as session:
            admin = await session.get(User, self.admin.id)
            draft = await experts.create_invite(
                session, admin=admin, display_name="Черновик"
            )
            published = await experts.create_invite(
                session, admin=admin, display_name="На виду"
            )
            await experts.publish_expert_profile(
                session, profile_id=published.profile.id, admin=admin
            )
            await session.commit()
            draft_id = draft.profile.id

        bare = TestClient(self._app(None, enabled=True))
        self.assertEqual(bare.get("/api/v1/experts").status_code, 401)

        client = TestClient(self._app(self.participant, enabled=True))
        response = client.get("/api/v1/experts")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["display_name"], "На виду")
        self.assertNotIn("contact_private", body[0])

        draft_response = client.get(f"/api/v1/experts/{draft_id}")
        self.assertEqual(draft_response.status_code, 404)

    def test_create_invite_requires_admin(self) -> None:
        client = TestClient(self._app(self.participant, enabled=True))
        response = client.post(
            "/api/v1/experts/invites",
            json={"display_name": "Нельзя"},
        )
        self.assertEqual(response.status_code, 403)

        admin_client = TestClient(self._app(self.admin, enabled=True))
        created = admin_client.post(
            "/api/v1/experts/invites",
            json={"display_name": "Доктор Наук", "purpose": "profile"},
        )
        self.assertEqual(created.status_code, 200)
        payload = created.json()
        self.assertEqual(payload["profile_status"], "draft")
        self.assertEqual(payload["state"], "CREATED")
        self.assertTrue(payload["token"])

    def test_claim_via_init_data_without_membership(self) -> None:
        admin_client = TestClient(self._app(self.admin, enabled=True))
        created = admin_client.post(
            "/api/v1/experts/invites",
            json={"display_name": "Гость-эксперт", "mark_sent": True},
        ).json()

        client = TestClient(self._app(None, enabled=True))
        guest_telegram_id = 31337000
        response = client.post(
            "/api/v1/experts/invites/claim",
            json={
                "token": created["token"],
                "initData": _init_data(guest_telegram_id),
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["state"], "CLAIMED")
        self.assertEqual(body["claimed_telegram_id"], guest_telegram_id)
        self.assertFalse(body["era_membership_required"])
        self.assertEqual(body["profile_status"], "draft")

    def test_suggestion_response_never_leaks_contact(self) -> None:
        client = TestClient(self._app(self.participant, enabled=True))
        response = client.post(
            "/api/v1/experts/suggestions",
            json={
                "expert_name": "Кандидат",
                "field": "Культура",
                "why_interesting": "Сильный практик",
                "contact_private": "hidden-phone-+37499111222",
                "consent_given": True,
                "links": "https://example.com/cv",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        serialized = json.dumps(body)
        self.assertNotIn("hidden-phone", serialized)
        self.assertNotIn("contact_private", body)
        self.assertEqual(body["expert_name"], "Кандидат")
        self.assertEqual(body["status"], "pending")

        denied = client.post(
            "/api/v1/experts/suggestions",
            json={
                "expert_name": "Без согласия",
                "field": "Наука",
                "why_interesting": "x",
                "contact_private": "secret",
                "consent_given": False,
            },
        )
        self.assertEqual(denied.status_code, 403)


class ExpertPlatformFlagDefaultTests(unittest.TestCase):
    def test_experts_platform_defaults_off(self) -> None:
        settings = Settings(bot_token=BOT_TOKEN)
        self.assertFalse(settings.experts_platform_enabled)

    def test_visible_features_include_experts_boolean(self) -> None:
        off = visible_features(_settings(experts_platform_enabled=False), 1)
        on = visible_features(_settings(experts_platform_enabled=True), 1)
        self.assertIn(Feature.EXPERTS.value, off)
        self.assertFalse(off["experts"])
        self.assertTrue(on["experts"])


if __name__ == "__main__":
    unittest.main()
