from __future__ import annotations

from urllib.parse import urlparse

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User
from app.database.socials import SocialLink, SocialProfile
from app.keyboards.participant import profile_settings_keyboard
from app.states.profile_settings import ProfileSettingsStates
from app.utils import texts
from app.utils.constants import ApplicationStatus
from app.utils.validators import normalize_email

router = Router(name="profile_settings")

PLATFORMS = {
    "t.me": "Telegram",
    "telegram.me": "Telegram",
    "instagram.com": "Instagram",
    "vk.com": "VK",
    "linkedin.com": "LinkedIn",
    "facebook.com": "Facebook",
    "tiktok.com": "TikTok",
    "youtube.com": "YouTube",
    "youtu.be": "YouTube",
}


async def _guard(call: CallbackQuery | Message, user: User | None) -> bool:
    if isinstance(call, CallbackQuery):
        await call.answer()
    if user is None or user.application_status != ApplicationStatus.APPROVED:
        target = call.message if isinstance(call, CallbackQuery) else call
        await target.answer(texts.APPLICATION_PENDING)
        return False
    if user.is_blocked or user.is_archived:
        target = call.message if isinstance(call, CallbackQuery) else call
        await target.answer(texts.BLOCKED)
        return False
    return True


async def _profile(session: AsyncSession, user_id: int) -> SocialProfile:
    profile = await session.scalar(select(SocialProfile).where(SocialProfile.user_id == user_id))
    if profile is None:
        profile = SocialProfile(user_id=user_id)
        session.add(profile)
        await session.flush()
    return profile


def _platform_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    for domain, platform in PLATFORMS.items():
        if host == domain or host.endswith("." + domain):
            return platform
    return "Сайт"


def _normalize_url(value: str) -> str | None:
    value = " ".join((value or "").split()).strip()
    if not value or len(value) > 500:
        return None
    if "://" not in value:
        value = "https://" + value
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or "." not in parsed.netloc:
        return None
    return value


@router.callback_query(F.data == "profile:settings")
async def settings_menu(call: CallbackQuery, user: User | None) -> None:
    if not await _guard(call, user):
        return
    await call.message.answer(
        "⚙️ Настройки профиля\n\nЗдесь можно обновить фото, соцсети и контактный email.",
        reply_markup=profile_settings_keyboard(),
    )


@router.callback_query(F.data == "profile:photo")
async def photo_menu(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    if not await _guard(call, user):
        return
    profile = await _profile(session, user.id)
    status = "Фото добавлено." if profile.photo_file_id else "Фото пока не добавлено."
    await call.message.answer(
        f"🖼 Фото профиля\n\n{status}\n\nОтправьте новое фото одним сообщением или используйте команды ниже."
    )
    await call.message.answer("Команды: /remove_photo — удалить фото, /cancel — отменить")


@router.callback_query(F.data == "profile:email")
async def email_start(call: CallbackQuery, user: User | None, state: FSMContext) -> None:
    if not await _guard(call, user):
        return
    await state.set_state(ProfileSettingsStates.contact_email)
    await call.message.answer("Отправьте новый email для профиля. Формат будет проверен автоматически.\n\n/cancel — отменить")


@router.message(ProfileSettingsStates.contact_email)
async def email_save(message: Message, user: User | None, session: AsyncSession, state: FSMContext) -> None:
    if not await _guard(message, user):
        return
    email = normalize_email(message.text or "")
    if email is None:
        await message.answer("Почта выглядит некорректно. Пример: name@example.com")
        return
    profile = await _profile(session, user.id)
    profile.contact_email = email
    await session.flush()
    await state.clear()
    await message.answer("Email обновлён ✅", reply_markup=profile_settings_keyboard())


@router.message(F.photo)
async def photo_save(message: Message, user: User | None, session: AsyncSession) -> None:
    if not await _guard(message, user):
        return
    profile = await _profile(session, user.id)
    profile.photo_file_id = message.photo[-1].file_id
    await session.flush()
    await message.answer("Фото профиля обновлено ✅")


@router.message(F.text == "/remove_photo")
async def photo_remove(message: Message, user: User | None, session: AsyncSession) -> None:
    if not await _guard(message, user):
        return
    profile = await _profile(session, user.id)
    profile.photo_file_id = None
    await session.flush()
    await message.answer("Фото удалено.")


@router.callback_query(F.data == "profile:socials")
async def socials_menu(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    if not await _guard(call, user):
        return
    links = (
        await session.scalars(
            select(SocialLink)
            .where(SocialLink.user_id == user.id, SocialLink.is_active.is_(True))
            .order_by(SocialLink.created_at.desc())
        )
    ).all()
    if links:
        text = "🔗 Соцсети\n\n" + "\n".join(f"• {link.platform}: {link.url}" for link in links)
    else:
        text = "🔗 Соцсети\n\nСсылок пока нет. Отправьте ссылку сообщением, чтобы добавить."
    await call.message.answer(text + "\n\n/add_social — добавить ссылку")


@router.message(F.text == "/add_social")
async def social_start(message: Message, user: User | None, state: FSMContext) -> None:
    if not await _guard(message, user):
        return
    await state.set_state(ProfileSettingsStates.social_url)
    await message.answer("Отправьте ссылку на соцсеть или сайт. Например: t.me/username или instagram.com/name")


@router.message(ProfileSettingsStates.social_url)
async def social_save(message: Message, user: User | None, session: AsyncSession, state: FSMContext) -> None:
    if not await _guard(message, user):
        return
    url = _normalize_url(message.text or "")
    if url is None:
        await message.answer("Ссылка выглядит некорректно. Отправьте полный адрес или коротко: instagram.com/name")
        return
    exists = await session.scalar(
        select(SocialLink).where(SocialLink.user_id == user.id, SocialLink.url == url)
    )
    if exists:
        exists.is_active = True
        exists.platform = _platform_from_url(url)
    else:
        session.add(SocialLink(user_id=user.id, url=url, platform=_platform_from_url(url)))
    await session.flush()
    await state.clear()
    await message.answer("Ссылка добавлена ✅")


@router.message(F.text == "/cancel")
async def cancel_profile_settings(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Действие отменено.")
