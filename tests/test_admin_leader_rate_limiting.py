from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import HTTPException

from app.api.v1 import admin as admin_api
from app.api.v1 import leader as leader_api
from app.api.v1.admin import (
    ADMIN_ACTION_RATE_LIMIT,
    enforce_admin_action_rate_limit,
)
from app.api.v1.leader import (
    LEADER_ACTION_RATE_LIMIT,
    enforce_leader_action_rate_limit,
)


def _request(redis) -> SimpleNamespace:
    dispatcher = SimpleNamespace(storage=SimpleNamespace(redis=redis))
    app = SimpleNamespace(state=SimpleNamespace(dispatcher=dispatcher))
    return SimpleNamespace(app=app, client=SimpleNamespace(host="1.2.3.4"), headers={})


class AdminActionRateLimitTests(unittest.IsolatedAsyncioTestCase):
    """Covers docs/PRODUCTION_READINESS_AUDIT.md finding #11: decide-endpoints
    in Admin/Leader Mode had no rate limiting — a stolen/leaked admin or
    leader token could otherwise spam approve/reject/decide unbounded."""

    async def test_under_limit_is_allowed(self) -> None:
        redis = SimpleNamespace(incr=AsyncMock(return_value=1), expire=AsyncMock())
        await enforce_admin_action_rate_limit(_request(redis))
        redis.expire.assert_awaited_once()

    async def test_over_limit_raises_429(self) -> None:
        redis = SimpleNamespace(
            incr=AsyncMock(return_value=ADMIN_ACTION_RATE_LIMIT + 1), expire=AsyncMock()
        )
        with self.assertRaises(HTTPException) as ctx:
            await enforce_admin_action_rate_limit(_request(redis))
        self.assertEqual(ctx.exception.status_code, 429)

    async def test_uses_its_own_key_prefix(self) -> None:
        redis = SimpleNamespace(incr=AsyncMock(return_value=1), expire=AsyncMock())
        await enforce_admin_action_rate_limit(_request(redis))
        called_key = redis.incr.call_args[0][0]
        self.assertIn("admin_action", called_key)


class LeaderActionRateLimitTests(unittest.IsolatedAsyncioTestCase):
    async def test_under_limit_is_allowed(self) -> None:
        redis = SimpleNamespace(incr=AsyncMock(return_value=1), expire=AsyncMock())
        await enforce_leader_action_rate_limit(_request(redis))
        redis.expire.assert_awaited_once()

    async def test_over_limit_raises_429(self) -> None:
        redis = SimpleNamespace(
            incr=AsyncMock(return_value=LEADER_ACTION_RATE_LIMIT + 1), expire=AsyncMock()
        )
        with self.assertRaises(HTTPException) as ctx:
            await enforce_leader_action_rate_limit(_request(redis))
        self.assertEqual(ctx.exception.status_code, 429)

    async def test_uses_its_own_key_prefix(self) -> None:
        redis = SimpleNamespace(incr=AsyncMock(return_value=1), expire=AsyncMock())
        await enforce_leader_action_rate_limit(_request(redis))
        called_key = redis.incr.call_args[0][0]
        self.assertIn("leader_action", called_key)


class RateLimitDependencyWiringTests(unittest.TestCase):
    """Confirms the dependency is actually attached to every POST route, not
    just that the function itself works — a route that forgets to declare
    it would otherwise pass every other test silently."""

    def test_every_admin_post_route_has_rate_limiting(self) -> None:
        post_routes = [r for r in admin_api.router.routes if r.methods and "POST" in r.methods]
        # 7 original decide/approve/reject routes + 6 People routes (PR 24:
        # role, block, archive, permission toggle, points, badge award) + 12
        # routes from PR 25 (4 team-post: prepare/edit/reject/publish; 2
        # event attendance/points; 3 partner CRUD; 3 offer CRUD) + 4 Offices
        # routes from PR 26 (create, delete, assign, remove assignment) + 4
        # Auction routes from PR 27 (create, confirm-winner, deliver, cancel) + 5
        # Survey routes from PR 29 (monthly template, create, edit, archive, send) + 5
        # Reward/Redemption routes from PR 31 (create reward, disable reward,
        # answer/exchange/reject redemption) + 3 Event Activity routes from
        # PR 32 (create, send, decide submission) + 1 data-deletion-request
        # fulfill route + 5 admin-tools routes (goals: create + decide,
        # organization contacts: create + archive, chat greetings: toggle —
        # see app/services/admin_goals_service.py, admin_contacts_service.py,
        # admin_greetings_service.py) + 2 broadcast routes (personal message,
        # chat — see app/services/admin_broadcast_service.py) + 1 maintenance
        # reset route (gated separately by require_maintenance_access, but
        # still rate-limited like every other mutation — see
        # app/services/maintenance_service.py) + 1 chat health-check route
        # (2026-08 master spec section 30 — Telegram API calls are worth
        # rate-limiting same as everything else here even though it's
        # read-only, see app/services/chat_registry_service.py) + 1 chat FAQ
        # publish route (2026-08 master spec, P5 — see
        # app/services/chat_faq_service.py).
        self.assertEqual(len(post_routes), 57, "expected 57 admin mutation routes")
        for route in post_routes:
            deps = [d.call for d in route.dependant.dependencies]
            self.assertIn(
                enforce_admin_action_rate_limit,
                deps,
                f"{route.path} is missing enforce_admin_action_rate_limit",
            )

    def test_every_leader_post_route_has_rate_limiting(self) -> None:
        post_routes = [r for r in leader_api.router.routes if r.methods and "POST" in r.methods]
        # 3 original (create assigned task, create open task, decide
        # application) + 1 Event Activity route from PR 32 (decide
        # submission) + 1 task-delivery retry route (2026-08 master spec
        # section 31-33 -- see app/services/leader_service.py).
        self.assertEqual(len(post_routes), 5, "expected 5 leader create/decide routes")
        for route in post_routes:
            deps = [d.call for d in route.dependant.dependencies]
            self.assertIn(
                enforce_leader_action_rate_limit,
                deps,
                f"{route.path} is missing enforce_leader_action_rate_limit",
            )


if __name__ == "__main__":
    unittest.main()
