"""Shared media knowledge catalogue; edits preserve records and use the audit log."""
from hashlib import sha256
import json
from urllib.parse import urlsplit

from sqlalchemy import func, select

from app.database.media_models import MediaLibraryItem
from app.database.models import AuditLog, Direction, User
from app.services import media_service
from app.services.audit_service import audit

CATEGORIES = {"photo": "Фото и съёмка", "editing": "Монтаж", "journalism": "Журналистика и интервью",
    "texts": "Тексты", "design": "Дизайн", "short_video": "Сторис и короткие видео", "standards": "Стандарты ЭРА",
    "publishing": "Инструкции публикации", "logos": "Логотипы", "canva": "Шаблоны Canva", "video": "Видео",
    "fonts_visual": "Шрифты и визуал", "guides": "Инструкции", "examples": "Примеры", "partner_materials": "Материалы партнёров", "archive": "Архив"}
ACTIONS = ("media.library_created", "media.library_updated")


async def require_manager(session, user, settings):
    await session.scalar(select(User.id).where(User.id == user.id).with_for_update(key_share=True))
    await session.scalar(select(Direction.id).where(Direction.name == "Медиа").with_for_update())
    actor = await session.scalar(select(User).where(User.id == user.id).execution_options(populate_existing=True))
    if not await media_service.can_manage_media(session, actor, settings):
        raise PermissionError("Редактирование базы знаний доступно руководителю медиа и председателю")
    return actor


async def revision(session, ident):
    return int(await session.scalar(select(func.max(AuditLog.id)).where(AuditLog.action.in_(ACTIONS),
        AuditLog.entity_type == "media_library", AuditLog.entity_id == ident)) or 0)


async def item_out(session, item, *, revision_value=None):
    return {"id": item.id, "kind": item.kind, "category": item.category, "title": item.title,
        "description": item.description, "url": item.url, "destination_type": item.destination_type,
        "is_active": item.is_active, "pinned": item.sort_order < 100,
        "revision": await revision(session, item.id) if revision_value is None else revision_value}


async def list_items_out(session, *, include_archived=False):
    """Return the catalogue with revisions in two queries, not one query per item."""
    items = await list_items(session, include_archived=include_archived)
    if not items:
        return []
    latest = (select(AuditLog.entity_id, func.max(AuditLog.id))
        .join(MediaLibraryItem, MediaLibraryItem.id == AuditLog.entity_id)
        .where(AuditLog.action.in_(ACTIONS), AuditLog.entity_type == "media_library")
        .group_by(AuditLog.entity_id))
    if not include_archived:
        latest = latest.where(MediaLibraryItem.is_active.is_(True))
    revisions = {ident: int(value) for ident, value in (await session.execute(latest)).all()}
    return [await item_out(session, item, revision_value=revisions.get(item.id, 0)) for item in items]


def validate(values):
    title = str(values.get("title", "")).strip()
    if not 2 <= len(title) <= 255:
        raise ValueError("Введите название от 2 до 255 символов")
    category = values.get("category", "archive")
    if category not in CATEGORIES:
        raise ValueError("Выберите категорию базы знаний")
    kind = values.get("kind", "link")
    if kind not in {"text", "link", "file", "photo", "video", "document", "template", "guide", "brand_asset"}:
        raise ValueError("Неизвестный вид материала")
    url = str(values.get("url") or "").strip()
    destination = values.get("destination_type", "external_url")
    if destination == "internal_route":
        if url != "media/guide":
            raise ValueError("Неизвестная страница приложения")
    elif url:
        # urlsplit and .port can raise ValueError for malformed IPv6 hosts,
        # non-numeric ports and out-of-range ports. Normalize those failures
        # to the same user-facing validation error as other unsafe links.
        try:
            parsed = urlsplit(url)
            valid_port = parsed.port in (None, 443)
        except ValueError as exc:
            raise ValueError("Укажите HTTPS-ссылку на материал") from exc
        # Backslashes are interpreted as path separators by some clients,
        # but not by urlsplit; never accept a link with ambiguous authority.
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or "\\" in url or any(c.isspace() for c in url) or not valid_port):
            raise ValueError("Укажите HTTPS-ссылку на материал")
    elif kind != "text":
        raise ValueError("Добавьте ссылку на материал")
    description = (values.get("description") or "").strip()
    if kind == "text" and not description:
        raise ValueError("Добавьте текст инструкции")
    return {"title": title, "kind": kind, "category": category, "url": url,
        "description": description or None, "destination_type": destination,
        "sort_order": 0 if values.get("pinned", False) else 100, "is_active": bool(values.get("is_active", True))}


async def create_item(session, actor, settings, values, request_key):
    await require_manager(session, actor, settings)
    clean = validate(values)
    fingerprint = sha256(json.dumps(clean, sort_keys=True).encode()).hexdigest()
    existing = await session.scalar(select(AuditLog).where(AuditLog.action == ACTIONS[0], AuditLog.actor_id == actor.id,
        AuditLog.new_value["request_key"].as_string() == request_key))
    if existing:
        if existing.new_value.get("fingerprint") != fingerprint:
            raise ValueError("Этот запрос уже использован для другого материала")
        return await session.get(MediaLibraryItem, existing.entity_id)
    item = MediaLibraryItem(**clean)
    session.add(item)
    await session.flush()
    await audit(session, actor_id=actor.id, action=ACTIONS[0], entity_type="media_library", entity_id=item.id,
        new_value={"request_key": request_key, "fingerprint": fingerprint})
    return item


async def update_item(session, actor, settings, ident, values, expected_revision):
    await require_manager(session, actor, settings)
    item = await session.scalar(select(MediaLibraryItem).where(MediaLibraryItem.id == ident).with_for_update()
        .execution_options(populate_existing=True))
    if item is None:
        raise LookupError("Материал базы знаний не найден")
    if await revision(session, ident) != expected_revision:
        raise ValueError("Материал уже изменён. Обновите базу знаний")
    before = {key: getattr(item, key) for key in ("title", "description", "url", "kind", "category", "destination_type", "is_active")}
    clean = validate({**before, "pinned": item.sort_order < 100, **values})
    for key, value in clean.items():
        setattr(item, key, value)
    await audit(session, actor_id=actor.id, action=ACTIONS[1], entity_type="media_library", entity_id=ident,
        old_value=before, new_value=clean)
    await session.flush()
    return item


async def list_items(session, *, include_archived=False):
    query = select(MediaLibraryItem)
    if not include_archived:
        query = query.where(MediaLibraryItem.is_active.is_(True))
    return list((await session.scalars(query.order_by(MediaLibraryItem.sort_order, MediaLibraryItem.id))).all())
