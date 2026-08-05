from __future__ import annotations

import time

from fastapi import HTTPException, Request


async def enforce_rate_limit(
    request: Request, *, key_prefix: str, limit: int, window_seconds: int
) -> None:
    """A minimal Redis-backed fixed-window rate limiter.

    Reuses the same Redis instance the bot's aiogram FSM storage already
    depends on (see app/bot.py) — no new infrastructure to run or secure.
    Fails open (lets the request through) if Redis is unreachable, since an
    outage of the limiter itself should not take down the Mini App; the
    endpoints this protects still have their own authorization checks.
    """
    dispatcher = getattr(request.app.state, "dispatcher", None)
    redis = getattr(getattr(dispatcher, "storage", None), "redis", None)
    if redis is None:
        return

    client_ip = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()

    bucket = int(time.time() // window_seconds)
    key = f"era:ratelimit:{key_prefix}:{client_ip}:{bucket}"
    try:
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, window_seconds)
    except Exception:
        return

    if count > limit:
        raise HTTPException(status_code=429, detail="rate_limited")
