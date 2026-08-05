from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import HTTPException

from app.api.rate_limit import enforce_rate_limit


def _request(redis=None, client_host: str = "1.2.3.4", forwarded: str | None = None):
    dispatcher = SimpleNamespace(storage=SimpleNamespace(redis=redis)) if redis is not None else None
    app = SimpleNamespace(state=SimpleNamespace(dispatcher=dispatcher))
    headers = {"x-forwarded-for": forwarded} if forwarded else {}
    return SimpleNamespace(
        app=app,
        client=SimpleNamespace(host=client_host),
        headers=headers,
    )


class RateLimitTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_redis_available_does_not_block(self) -> None:
        request = _request(redis=None)
        await enforce_rate_limit(request, key_prefix="test", limit=1, window_seconds=60)

    async def test_under_limit_is_allowed(self) -> None:
        redis = SimpleNamespace(incr=AsyncMock(return_value=1), expire=AsyncMock())
        request = _request(redis=redis)
        await enforce_rate_limit(request, key_prefix="test", limit=5, window_seconds=60)
        redis.expire.assert_awaited_once()

    async def test_over_limit_raises_429(self) -> None:
        redis = SimpleNamespace(incr=AsyncMock(return_value=6), expire=AsyncMock())
        request = _request(redis=redis)
        with self.assertRaises(HTTPException) as ctx:
            await enforce_rate_limit(request, key_prefix="test", limit=5, window_seconds=60)
        self.assertEqual(ctx.exception.status_code, 429)

    async def test_redis_error_fails_open(self) -> None:
        redis = SimpleNamespace(incr=AsyncMock(side_effect=RuntimeError("down")), expire=AsyncMock())
        request = _request(redis=redis)
        await enforce_rate_limit(request, key_prefix="test", limit=1, window_seconds=60)

    async def test_uses_forwarded_for_header_when_present(self) -> None:
        redis = SimpleNamespace(incr=AsyncMock(return_value=1), expire=AsyncMock())
        request = _request(redis=redis, client_host="10.0.0.1", forwarded="203.0.113.5, 10.0.0.1")
        await enforce_rate_limit(request, key_prefix="test", limit=5, window_seconds=60)
        called_key = redis.incr.call_args[0][0]
        self.assertIn("203.0.113.5", called_key)


if __name__ == "__main__":
    unittest.main()
