"""Full-admin anniversary #669 activation and status (owner-authorized)."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.database.models import User
from app.services.authorization_service import is_full_admin
from app.services.system_health_service import current_commit_sha
from app.utils import texts

router = Router(name="anniversary_activation")


def _factory(session: AsyncSession):
    return async_sessionmaker(session.bind, expire_on_commit=False)


@router.message(Command("anniversary2026_status"))
async def anniversary_status_command(
    message: Message, user: User | None, settings: Settings, session: AsyncSession
) -> None:
    if not is_full_admin(user, settings, message.from_user.id):
        await message.answer(texts.NO_ACCESS)
        return
    from app.services.anniversary_campaign_service import campaign_snapshot

    snap = await campaign_snapshot(_factory(session))
    if not snap.get("prepared"):
        await message.answer("Годовщина 2026: ещё не подготовлена (ACTIVE_KEY / кампания выкл.).")
        return
    active = snap.get("active") or {}
    await message.answer(
        "Годовщина 2026\n"
        f"event_id: {snap.get('event_id')}\n"
        f"status: {snap.get('status')}\n"
        f"active: {active.get('mode') or 'нет'}\n"
        f"release: {(active.get('release_sha') or '—')[:12]}\n"
        f"receipts: {len(snap.get('receipts') or [])}\n"
        f"bot_visible: {snap.get('bot_visible')} · miniapp: {snap.get('miniapp_visible')}"
    )


@router.message(Command("activate_anniversary2026"))
async def activate_anniversary_preview(
    message: Message, user: User | None, settings: Settings
) -> None:
    if not is_full_admin(user, settings, message.from_user.id):
        await message.answer(texts.NO_ACCESS)
        return
    sha = (current_commit_sha() or "").strip().lower()
    if len(sha) < 40:
        await message.answer("Нет RENDER_GIT_COMMIT — активация на этом процессе недоступна.")
        return
    sha40 = sha[:40]
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Активировать публикацию годовщины",
                    callback_data=f"admin:anniversary2026:activate:{sha40[:16]}",
                )
            ]
        ]
    )
    await message.answer(
        "Активация кампании «ЭРА — 1 ГОД»\n\n"
        f"Release SHA: {sha40[:12]}…\n"
        "Будет подготовлено мероприятие и включён publish (канал @era_leaders1 + тема объявлений).\n"
        "Планировщик отправит начальный пост и будущие напоминания без повторов.\n"
        "Продолжайте только если это намеренная публикация в прод.",
        reply_markup=markup,
    )


@router.callback_query(F.data.regexp(r"^admin:anniversary2026:activate:[0-9a-f]{16}$"))
async def activate_anniversary_confirm(
    call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession
) -> None:
    if not is_full_admin(user, settings, call.from_user.id):
        await call.answer(texts.NO_ACCESS, show_alert=True)
        return
    prefix = call.data.rsplit(":", 1)[-1]
    sha = (current_commit_sha() or "").strip().lower()
    if len(sha) < 40 or not sha.startswith(prefix):
        await call.answer("Release сменился. Снова /activate_anniversary2026.", show_alert=True)
        return
    from app.services.anniversary_campaign_service import activate_publication

    try:
        snap = await activate_publication(
            call.bot, settings, _factory(session), sha[:40]
        )
    except ValueError as exc:
        await call.answer(str(exc)[:180], show_alert=True)
        return
    await call.answer()
    active = snap.get("active") or {}
    await call.message.answer(
        "✅ Годовщина активирована.\n"
        f"event_id: {snap.get('event_id')}\n"
        f"mode: {active.get('mode')}\n"
        f"SHA: {(active.get('release_sha') or sha)[:12]}…\n"
        "Доставку выполняет планировщик (без повторной отправки уже сохранённых ключей)."
    )
