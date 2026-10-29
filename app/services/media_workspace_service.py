"""ERA/KSOORS calendar on the existing media content records, no parallel store."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.database.media_models import MediaContentItem
from app.database.models import Direction, User
from app.services import media_service
from app.services.audit_service import audit
from app.services.media_pipeline_service import can_transition
from app.utils.constants import ApplicationStatus

AREAS = {
    "era": {"title": "ЭРА", "platforms": {"telegram": "https://t.me/era_leaders1", "instagram": "https://www.instagram.com/era_leaders"}, "topic_url": "https://t.me/c/2970786578/1434"},
    "ksoors": {"title": "КСООРС", "platforms": {"telegram": "https://t.me/ksoors_arm", "instagram": "https://www.instagram.com/ksoors_arm", "facebook": "https://www.facebook.com/share/17Xm3jbF9h/"}, "topic_url": "https://t.me/c/2970786578/1433"},
}
PLATFORMS = {"telegram", "instagram", "facebook", "tiktok", "youtube", "website"}
# Telegram uses these paths for invitations, sharing and other actions, not public posts.
TELEGRAM_RESERVED_PATHS = {"joinchat", "share", "boost", "addstickers", "addemoji", "login", "proxy", "socks", "bg", "setlanguage", "invoice", "confirmphone", "iv", "s", "c"}


async def require_access(session, user, settings, *, write=False, area=None):
    if write:
        # Match membership/assignment's User -> Direction ordering. NO KEY
        # UPDATE still serializes access changes without blocking FK checks.
        await session.scalar(select(User.id).where(User.id == user.id).with_for_update(key_share=True))
        await session.scalar(select(Direction.id).where(Direction.name == "Медиа").with_for_update())
    from app.services.media_scope_service import can_edit_calendar
    # Refresh the identity on every operation, including an unfinished form.
    current = await session.scalar(select(User).where(User.id == user.id).execution_options(populate_existing=True))
    level = await media_service.media_access_level(session, current, settings)
    if not media_service.can_use_media_hub(level) or (write and not await can_edit_calendar(session, current, settings, area)):
        raise PermissionError("Доступ к календарю медиаотдела закрыт. Проверьте полномочия и обновите страницу.")


def area_of(item):
    return (item.metadata_json or {}).get("media_area", "era")


def item_out(item):
    data = item.metadata_json or {}
    scheduled_at = item.scheduled_at
    if scheduled_at is not None and scheduled_at.tzinfo is None:
        scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
    return {"id": item.id, "area": area_of(item), "title": item.title or item.rubric or "Материал",
        "body": item.body or "", "platform": data.get("platform", "telegram"), "status": item.status,
        "scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
        "responsible_id": data.get("responsible_id"), "materials": data.get("materials", ""),
        "publication_url": data.get("publication_url"), "publication_evidence": data.get("publication_evidence"),
        "revision": data.get("workspace_revision", 0)}


async def calendar(session, area, *, before_id: int | None = None, status_group: str = "all"):
    query = select(MediaContentItem).where(func.coalesce(
        MediaContentItem.metadata_json["media_area"].as_string(), "era") == area)
    # Filter before pagination: a long history of published posts must not hide open tasks.
    if status_group == "active":
        query = query.where(MediaContentItem.status.notin_(("published", "skipped")))
    elif status_group == "published":
        query = query.where(MediaContentItem.status == "published")
    elif status_group != "all":
        raise ValueError("Неизвестный фильтр календаря")
    if before_id is not None:
        query = query.where(MediaContentItem.id < before_id)
    rows = (await session.scalars(query.order_by(MediaContentItem.id.desc()).limit(100))).all()
    return [item_out(item) for item in rows]


async def _validate_responsible(session, user_id):
    if user_id is None:
        return
    user = await session.get(User, user_id)
    if (user is None or user.is_blocked or user.is_archived or user.application_status != ApplicationStatus.APPROVED
            or (await media_service._media_membership_status(session, user.id)) != "approved"):
        raise ValueError("Выберите действующего участника медиаотдела")


def _publication_url(value, platform):
    # urlsplit and its lazy .port property can raise ValueError for malformed
    # IPv6 hosts, non-numeric ports or out-of-range ports. Normalize the
    # resulting validation detail instead of exposing parser internals.
    detail = "Нужна HTTPS-ссылка на опубликованный материал выбранной платформы"
    try:
        parsed = urlsplit(value or "")
        port = parsed.port
    except ValueError:
        raise ValueError(detail) from None
    hosts = {"telegram": {"t.me"}, "instagram": {"instagram.com", "www.instagram.com"},
        "facebook": {"facebook.com", "www.facebook.com", "fb.watch"},
        "youtube": {"youtube.com", "www.youtube.com", "youtu.be"},
        "tiktok": {"tiktok.com", "www.tiktok.com", "vm.tiktok.com"}}
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or port not in (None, 443) or parsed.hostname not in hosts.get(platform, set())
            or not parsed.path.strip("/")):
        raise ValueError("Нужна HTTPS-ссылка на опубликованный материал выбранной платформы")
    if platform == "telegram":
        parts = parsed.path.strip("/").split("/")
        # A channel post is /channel/message_id. Private supergroup posts
        # may be /c/chat_id/message_id or forum /c/chat_id/topic_id/message_id.
        # A channel link (/c/chat_id), an extra path component, or message 0
        # is not evidence that the scheduled material was published.
        is_public_post = (
            len(parts) == 2 and parts[0].lower() not in TELEGRAM_RESERVED_PATHS
            and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{4,31}", parts[0]) is not None
            and parts[1].isascii() and parts[1].isdecimal()
            and int(parts[1]) > 0
        )
        is_private_post = (
            len(parts) in (3, 4) and parts[0] == "c"
            and all(part.isascii() and part.isdecimal() and int(part) > 0 for part in parts[1:])
        )
        if not (is_public_post or is_private_post):
            raise ValueError("Укажите прямую ссылку на сообщение Telegram, а не на канал или тему")
    return value


async def create_entry(session, user, settings, area, values, request_key):
    if area not in AREAS:
        raise ValueError("Неизвестное направление")
    await require_access(session, user, settings, write=True, area=area)
    await _validate_responsible(session, values.get("responsible_id"))
    fingerprint = hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()
    key = f"workspace:{user.id}:{request_key}"
    existing = await session.scalar(select(MediaContentItem).where(MediaContentItem.source_key == key))
    if existing:
        if area_of(existing) != area or (existing.metadata_json or {}).get("request_hash") != fingerprint:
            raise ValueError("Ключ запроса уже использован для другого материала")
        return existing
    item = MediaContentItem(source_kind="media_workspace", source_key=key, kind="text", title=values["title"],
        body=values.get("body", ""), scheduled_at=values.get("scheduled_at"), status="planned", created_by=user.id,
        metadata_json={"media_area": area, "platform": values["platform"], "responsible_id": values.get("responsible_id"),
            "materials": values.get("materials", ""), "workspace_revision": 0, "request_hash": fingerprint})
    try:
        async with session.begin_nested():
            session.add(item)
            await session.flush()
    except IntegrityError:
        existing = await session.scalar(select(MediaContentItem).where(MediaContentItem.source_key == key))
        if existing and area_of(existing) == area and (existing.metadata_json or {}).get("request_hash") == fingerprint:
            return existing
        raise ValueError("Повторный запрос не совпадает с исходным") from None
    await audit(session, actor_id=user.id, action="media.calendar_created", entity_type="media_content", entity_id=item.id,
        new_value={"area": area, "status": item.status})
    return item


async def update_entry(session, user, settings, area, item_id, values, revision):
    await require_access(session, user, settings, write=True, area=area)
    item = await session.scalar(select(MediaContentItem).where(MediaContentItem.id == item_id)
        .with_for_update().execution_options(populate_existing=True))
    if item is None or area_of(item) != area:
        raise LookupError("Материал не найден в выбранном направлении")
    data = dict(item.metadata_json or {})
    if data.get("workspace_revision", 0) != revision:
        raise ValueError("Материал уже изменён. Обновите календарь")
    if item.status in {"published", "skipped"}:
        raise ValueError("Завершённый материал нельзя изменять")
    if "responsible_id" in values:
        await _validate_responsible(session, values["responsible_id"])
    target = values.get("status") or item.status
    if not can_transition(item.status, target):
        raise ValueError("Этот переход статуса недоступен")
    if target == "published":
        url = _publication_url(values.get("publication_url"), data.get("platform", "telegram"))
        data.update(publication_url=url, publication_evidence="manager_confirmed_link")
        item.published_at = datetime.now(timezone.utc)
    old_status = item.status
    for field in ("title", "body", "scheduled_at"):
        if field in values:
            setattr(item, field, values[field])
    for field in ("responsible_id", "materials"):
        if field in values:
            data[field] = values[field]
    data["workspace_revision"] = revision + 1
    item.metadata_json = data
    item.status = target
    await audit(session, actor_id=user.id, action="media.calendar_updated", entity_type="media_content", entity_id=item.id,
        old_value={"status": old_status, "revision": revision},
        new_value={"area": area, "status": target, "revision": revision + 1, "evidence": data.get("publication_evidence")})
    await session.flush()
    return item
