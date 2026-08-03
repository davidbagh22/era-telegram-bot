from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import User
from app.keyboards.participant import main_menu
from app.services.application_review_service import approve_application
from app.services.chat_access_service import sync_user_chat_access
from app.services.notification_service import safe_send
from app.utils import texts
from app.utils.constants import Role

router = Router(name="admin_approval_bonus_fix")


def _admin_ok(user: User | None, settings: Settings, telegram_id: int) -> bool:
    return bool(
        telegram_id in settings.admin_ids
        or (user and user.role == Role.ADMIN and not user.is_blocked and not user.is_archived)
        or (
            user
            and not user.is_blocked
            and not user.is_archived
            and any(grant.is_active and grant.permission == "applications.review" for grant in (getattr(user, "permission_grants", None) or []))
        )
    )


@router.callback_query(F.data.startswith("admin:approve_user:"))
async def approve_user_with_100_points(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    bot: Bot,
) -> None:
    await call.answer()
    if not _admin_ok(user, settings, call.from_user.id):
        await call.message.answer(texts.NO_ACCESS)
        return
    target = await session.get(User, int(call.data.rsplit(":", 1)[-1]))
    if target is None:
        return
    result = await approve_application(session, target, actor_id=user.id if user else None)
    if result.code == "already_approved":
        await call.message.answer("Эта заявка уже одобрена — повторное уведомление участнику не отправлено")
        return
    if result.code == "already_rejected":
        await call.message.answer("Эта заявка уже отклонена — повторно одобрить её нельзя")
        return
    await call.message.answer(f"Заявка одобрена ✅\n\n{target.first_name} получил доступ к функциям участника")
    await safe_send(bot, target.telegram_id, texts.APPLICATION_APPROVED, main_menu(settings.era_channel_url, miniapp_url=settings.miniapp_url))
    await safe_send(bot, target.telegram_id, "Перед стартом — короткие правила сообщества\n\n" + texts.CHAT_RULES)
    await sync_user_chat_access(bot, settings, session, target)
