"""Google Calendar sync for published ERA events (#664).

Disabled until credentials exist. Never invents attendees or sends invites.
Durable per-event AppSetting outbox (`google_calendar:event:{id}`) so edits,
cancellations and transient API failures retry independently of Telegram
announcement delivery.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx
import jwt
from sqlalchemy import select

from app.database.event_experience import EventExperience
from app.database.models import AppSetting, Event
from app.services.google_calendar_payload import build_calendar_payload
from app.utils.constants import EventStatus

logger = logging.getLogger(__name__)
SETTING_PREFIX = "google_calendar:event:"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/calendar"
API = "https://www.googleapis.com/calendar/v3"
SYNCABLE = {EventStatus.PUBLISHED, EventStatus.REGISTRATION_OPEN, EventStatus.CANCELLED}
MAX_ATTEMPTS = 8


def sync_enabled(settings) -> bool:
    return bool(
        getattr(settings, "google_calendar_sync_enabled", False)
        and str(getattr(settings, "google_calendar_id", "") or "").strip()
        and str(getattr(settings, "google_calendar_service_account_json", "") or "").strip()
    )


def _setting_key(event_id: int) -> str:
    return f"{SETTING_PREFIX}{event_id}"


def _load_sa(settings) -> dict[str, Any]:
    raw = str(settings.google_calendar_service_account_json or "").strip()
    data = json.loads(raw)
    if not isinstance(data, dict) or not data.get("client_email") or not data.get("private_key"):
        raise ValueError("google_calendar_service_account_invalid")
    return data


async def _access_token(settings, client: httpx.AsyncClient) -> str:
    sa = _load_sa(settings)
    now = int(time.time())
    assertion = jwt.encode(
        {
            "iss": sa["client_email"],
            "scope": SCOPE,
            "aud": TOKEN_URL,
            "iat": now,
            "exp": now + 3600,
        },
        sa["private_key"],
        algorithm="RS256",
    )
    response = await client.post(
        TOKEN_URL,
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        },
        timeout=30.0,
    )
    response.raise_for_status()
    token = response.json().get("access_token")
    if not isinstance(token, str) or not token:
        raise ValueError("google_calendar_token_missing")
    return token


def _payload_for(event, experience) -> dict[str, Any] | None:
    # Never invent a duration — payload builder and ICS omit unknown ends.
    end_time = getattr(experience, "end_time", None) if experience is not None else None
    if end_time is None:
        return None
    try:
        body = build_calendar_payload(event, end_time=end_time)
    except ValueError:
        return None
    if event.status == EventStatus.CANCELLED:
        body["status"] = "cancelled"
    return body


async def enqueue_calendar_sync(session, event_id: int) -> None:
    """Mark an event for calendar sync. Safe when sync is still OFF (later recovery)."""
    if not isinstance(event_id, int) or isinstance(event_id, bool) or event_id <= 0:
        return
    key = _setting_key(event_id)
    row = await session.scalar(select(AppSetting).where(AppSetting.key == key))
    value = dict(row.value) if row is not None and isinstance(row.value, dict) else {}
    value.update({
        "era_event_id": event_id,
        "sync_status": "pending",
        "queued_at": datetime.now(timezone.utc).isoformat(),
    })
    value.pop("last_error", None)
    if row is None:
        session.add(AppSetting(key=key, value=value))
    else:
        row.value = value
    await session.flush()


async def sync_published_event(session, settings, event, experience) -> str | None:
    """Insert or patch one calendar entry. Raises on transport/API failure for retry."""
    if not sync_enabled(settings) or event is None:
        return None
    if event.status not in SYNCABLE:
        return None
    body = _payload_for(event, experience)
    if body is None:
        # Missing end_time is not a transient failure — leave pending for a later edit.
        return None
    calendar_id = str(settings.google_calendar_id).strip()
    key = _setting_key(event.id)
    row = await session.scalar(select(AppSetting).where(AppSetting.key == key))
    existing_id = None
    attempts = 0
    if isinstance(getattr(row, "value", None), dict):
        existing_id = row.value.get("google_event_id")
        if not isinstance(existing_id, str) or not existing_id:
            existing_id = None
        try:
            attempts = int(row.value.get("attempts") or 0)
        except (TypeError, ValueError):
            attempts = 0
    async with httpx.AsyncClient() as client:
        token = await _access_token(settings, client)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        if existing_id:
            response = await client.patch(
                f"{API}/calendars/{calendar_id}/events/{existing_id}",
                headers=headers,
                json=body,
                params={"sendUpdates": "none"},
                timeout=30.0,
            )
        else:
            response = await client.post(
                f"{API}/calendars/{calendar_id}/events",
                headers=headers,
                json=body,
                params={"sendUpdates": "none"},
                timeout=30.0,
            )
        response.raise_for_status()
        google_id = response.json().get("id")
        if not isinstance(google_id, str) or not google_id:
            raise ValueError("google_calendar_event_id_missing")
    payload = {
        "google_event_id": google_id,
        "calendar_id": calendar_id,
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "era_event_id": event.id,
        "sync_status": "synced",
        "attempts": attempts,
    }
    if row is None:
        session.add(AppSetting(key=key, value=payload))
    else:
        row.value = payload
    await session.flush()
    return google_id


async def _mark_failure(session, event_id: int, error: Exception) -> None:
    key = _setting_key(event_id)
    row = await session.scalar(select(AppSetting).where(AppSetting.key == key))
    value = dict(row.value) if row is not None and isinstance(row.value, dict) else {"era_event_id": event_id}
    try:
        attempts = int(value.get("attempts") or 0) + 1
    except (TypeError, ValueError):
        attempts = 1
    value.update({
        "sync_status": "failed" if attempts >= MAX_ATTEMPTS else "pending",
        "attempts": attempts,
        "last_error": str(error)[:300],
        "failed_at": datetime.now(timezone.utc).isoformat(),
    })
    if row is None:
        session.add(AppSetting(key=key, value=value))
    else:
        row.value = value
    await session.flush()


async def process_pending_calendar_syncs(settings, session_factory) -> None:
    """Independent of Telegram announcements: retry pending calendar exports."""
    if not sync_enabled(settings):
        return
    async with session_factory() as session:
        rows = list((await session.scalars(
            select(AppSetting).where(AppSetting.key.like(f"{SETTING_PREFIX}%"))
        )).all())
        pending_ids: list[int] = []
        for row in rows:
            if not isinstance(row.value, dict) or row.value.get("sync_status") != "pending":
                continue
            try:
                event_id = int(row.value.get("era_event_id") or row.key.rsplit(":", 1)[-1])
            except (TypeError, ValueError):
                continue
            if event_id > 0:
                pending_ids.append(event_id)
        for event_id in pending_ids[:40]:
            event = await session.get(Event, event_id)
            experience = await session.get(EventExperience, event_id)
            if event is None or event.status not in SYNCABLE:
                continue
            try:
                await sync_published_event(session, settings, event, experience)
                await session.commit()
            except Exception as exc:
                await session.rollback()
                try:
                    async with session_factory() as fail_session:
                        await _mark_failure(fail_session, event_id, exc)
                        await fail_session.commit()
                except Exception:
                    logger.exception("GOOGLE_CALENDAR_664 failure ledger failed event_id=%s", event_id)
                logger.exception("GOOGLE_CALENDAR_664 sync failed event_id=%s", event_id)
