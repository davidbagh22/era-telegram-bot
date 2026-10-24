"""Media invitation intent survives registration restarts without a second user system."""
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import AppSetting, Direction, User, UserDirection
from app.services.audit_service import audit
from app.services.media_service import MEDIA_DIRECTION_NAME, media_config
from app.utils.constants import ApplicationStatus


def intent_key(telegram_id: int) -> str:
    return f"media-join:{telegram_id}"


async def request_join(session: AsyncSession, telegram_id: int, user: User | None) -> str:
    if user is not None and (user.telegram_id != telegram_id or user.is_blocked or user.is_archived):
        raise ValueError("media_join_forbidden")
    if user is not None:
        user = await session.scalar(select(User).where(User.id == user.id).with_for_update()
                                    .execution_options(populate_existing=True))
        if user is None or user.telegram_id != telegram_id or user.is_blocked or user.is_archived:
            raise ValueError("media_join_forbidden")
    if not (await media_config(session)).get("join_enabled", True):
        raise ValueError("media_invitation_disabled")
    row = await session.scalar(select(AppSetting).where(AppSetting.key == intent_key(telegram_id)))
    if row is None:
        try:
            async with session.begin_nested():
                session.add(AppSetting(key=intent_key(telegram_id), value={"status": "requested"}))
                await session.flush()
        except IntegrityError:
            pass  # Another identical update already persisted the same intent.
    elif isinstance(row.value, dict) and row.value.get("status") == "joined":
        row.value = {"status": "requested"}
    if user is None or user.application_status not in {ApplicationStatus.APPROVED, ApplicationStatus.PENDING}:
        return "registration_required"
    return await complete_join(session, user)


async def complete_join(session: AsyncSession, user: User) -> str:
    """Same registration transaction; unique membership and user lock serialize retries."""
    await session.flush()
    user = await session.scalar(select(User).where(User.id == user.id).with_for_update()
                                .execution_options(populate_existing=True))
    if user is None or user.is_blocked or user.is_archived:
        return "forbidden"
    if user.application_status not in {ApplicationStatus.APPROVED, ApplicationStatus.PENDING}:
        return "registration_required"
    intent = await session.scalar(select(AppSetting).where(AppSetting.key == intent_key(user.telegram_id)).with_for_update())
    if intent is None:
        return "not_requested"
    direction = await session.scalar(select(Direction).where(Direction.name == MEDIA_DIRECTION_NAME).with_for_update())
    if direction is None:
        raise ValueError("media_direction_missing")
    if not (await media_config(session)).get("join_enabled", True):
        return "disabled"
    membership = await session.scalar(select(UserDirection).where(
        UserDirection.user_id == user.id, UserDirection.direction_id == direction.id))
    if isinstance(intent.value, dict) and intent.value.get("status") == "joined":
        return "already_joined" if membership and membership.status == "approved" else "not_requested"
    changed = membership is None or membership.status != "approved"
    if membership is None:
        session.add(UserDirection(user_id=user.id, direction_id=direction.id, status="approved"))
    else:
        membership.status = "approved"
    intent.value = {"status": "joined", "direction_id": direction.id}
    if changed:
        await audit(session, actor_id=user.id, action="media.member_joined", entity_type="direction",
                    entity_id=direction.id, new_value={"user_id": user.id, "source": "media_join"})
    await session.flush()
    return "joined" if changed else "already_joined"


async def send_welcome(bot, settings, user: User) -> None:
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
    from app.services.notification_service import safe_send_once
    from app.utils.deep_links import miniapp_path_url, miniapp_tasks_url
    rows = []
    if settings.effective_miniapp_url:
        rows.append([InlineKeyboardButton(text="Открыть медиаотдел", web_app=WebAppInfo(
            url=miniapp_path_url(settings.effective_miniapp_url, "media")))])
    rows.append([InlineKeyboardButton(text="Чат медиа", url=settings.media_chat_url)])
    if settings.effective_miniapp_url:
        rows.append([InlineKeyboardButton(text="Мои задания", web_app=WebAppInfo(
            url=miniapp_tasks_url(settings.effective_miniapp_url)))])
    text = "Вы добавлены в медиаотдел ЭРА. Другие членства сохранены.\nВ Telegram-чат можно вступить отдельно по кнопке ниже."
    if user.application_status != ApplicationStatus.APPROVED:
        text += "\nДоступ к рабочим разделам откроется после одобрения регистрации ЭРА."
    await safe_send_once(bot, settings, user.telegram_id, text, delivery_key=f"media:welcome:{user.id}",
                         notification_type="media_join", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
