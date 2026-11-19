"""Regression: no unpublished chapters, private membership or silent opt-ins."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.deps import get_current_user, get_session, get_settings
from app.api.v1.leisure import router
from app.utils.constants import ApplicationStatus


def client_for(**overrides):
    user = SimpleNamespace(id=1, telegram_id=101, is_blocked=False, is_archived=False,
                           application_status=ApplicationStatus.APPROVED, book_club_subscribed=False)
    for key, value in overrides.items():
        setattr(user, key, value)
    session = SimpleNamespace(commit=AsyncMock())
    settings = SimpleNamespace(feature_games="OFF", feature_tester_ids={101}, bot_username="ERA_1bot")
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app), user, session, settings


def test_catalog_and_detail_share_readable_archive_boundary():
    client, user, session, _ = client_for()
    with patch("app.api.v1.leisure.last_readable_issue_number", return_value=3):
        catalog = client.get("/api/v1/literature")
        assert catalog.status_code == 200
        assert [i["number"] for i in catalog.json()["items"]] == [3, 2, 1]
        assert client.get("/api/v1/literature/3").json()["summary"]
        for number in [0, -1, 4, 49]:
            assert client.get("/api/v1/literature/" + str(number)).status_code == 404
    assert not user.book_club_subscribed
    session.commit.assert_not_awaited()


def test_pending_blocked_and_archived_users_cannot_read_or_subscribe():
    for denied in [dict(application_status=ApplicationStatus.PENDING), dict(is_blocked=True), dict(is_archived=True)]:
        client, _, session, _ = client_for(**denied)
        assert client.get("/api/v1/literature").status_code == 403
        assert client.get("/api/v1/literature/1").status_code == 403
        assert client.patch("/api/v1/literature-subscription", json={"subscribed": True}).status_code == 403
        session.commit.assert_not_awaited()


def test_explicit_subscription_is_idempotent_and_preserves_unsubscribe():
    client, user, session, _ = client_for()
    for choice in [True, True, False]:
        response = client.patch("/api/v1/literature-subscription", json={"subscribed": choice})
        assert response.json() == {"subscribed": choice}
        assert user.book_club_subscribed == choice
    assert session.commit.await_count == 3


def test_games_rollout_and_real_bot_launch_remain_gated():
    client, _, _, settings = client_for()
    assert client.get("/api/v1/leisure/games").json() == {"enabled": False, "launch_url": None, "items": []}
    settings.feature_games = "TESTERS"
    response = client.get("/api/v1/leisure/games").json()
    assert response["enabled"] and response["items"]
    assert response["launch_url"] == "https://t.me/ERA_1bot?start=games"
    settings.feature_tester_ids = {999}
    assert not client.get("/api/v1/leisure/games").json()["enabled"]
