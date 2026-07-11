from __future__ import annotations

from datetime import datetime
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
from app.utils.validators import (
    calculate_age,
    clean_text,
    normalize_email,
    normalize_phone,
    parse_birth_date,
)

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

TEXT_FIELDS = {
    "first_name": ("Имя", "first_name", 100, "Отправьте новое имя"),
    "last_name": ("Фамилия", "last_name", 100, "Отправьте новую фамилию"),
    "city": ("Город", "city", 100, "Отправьте город"),
    "education_work": (
        "Учёба / работа",
        "education_work",
        255,
        "Напишите, где Вы учитесь или работаете",
    ),
    "occupation": (
        "Занятость",
        "occupation",
        1000,
        "Напишите, чем Вы сейчас занимаетесь",
    ),
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
        now = datetime.now().astimezone()
        profile = SocialProfile(user_id=user_id, created_at=now, updated_at=now)
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


async def _done(message: Message) -> None:
    await message.answer("Данные обновлены.", reply_markup=profile_settings_keyboard())


@router.callback_query(F.data == "profile:settings")
async def settings_menu(call: CallbackQuery, user: User | None) -> None:
    if not await _guard(call, user):
        return
    await call.message.answer(
        "✏️ Изменить данные\n\nВыберите поле, которое хотите обновить",
        reply_markup=profile_settings_keyboard(),
    )


@router.callback_query(F.data.startswith("profile:edit:"))
async def text_field_start(call: CallbackQuery, user: User | None, state: FSMContext) -> None:
    if not await _guard(call, user):
        return
    key = call.data.rsplit(":", 1)[-1]
    config = TEXT_FIELDS.get(key)
    if config is None:
        await call.message.answer("Это поле пока нельзя изменить здесь")
        return
    label, attr, max_length, prompt = config
    current = getattr(user, attr, None) or "не указано"
    await state.set_state(ProfileSettingsStates.text_value)
    await state.update_data(profile_field=key)
    await call.message.answer(
        f"{label}\n\nСейчас: {current}\n\n{prompt}\n\n/cancel — отменить"
    )


@router.message(ProfileSettingsStates.text_value)
async def text_field_save(
    message: Message,
    user: User | None,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if not await _guard(message, user):
        return
    data = await state.get_data()
    key = data.get("profile_field")
    config = TEXT_FIELDS.get(key)
    if config is None:
        await state.clear()
        await message.answer("Не удалось определить поле. Откройте редактирование заново")
        return
    _, attr, max_length, _ = config
    value = clean_text(message.text or "", max_length)
    if not value:
        await message.answer("Поле не может быть пустым. Напишите значение текстом")
        return
    setattr(user, attr, value)
    await session.flush()
    await state.clear()
    await _done(message)


@router.callback_query(F.data == "profile:birth_date")
async def birth_date_start(call: CallbackQuery, user: User | None, state: FSMContext) -> None:
    if not await _guard(call, user):
        return
    current = getattr(user, "birth_date", None)
    current_text = current.strftime("%d.%m.%Y") if current else "не указана"
    await state.set_state(ProfileSettingsStates.birth_date)
    await call.message.answer(
        f"Дата рождения\n\nСейчас: {current_text}\n\nОтправьте дату в формате ДД.ММ.ГГГГ\n\n/cancel — отменить"
    )


@router.message(ProfileSettingsStates.birth_date)
async def birth_date_save(
    message: Message,
    user: User | None,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if not await _guard(message, user):
        return
    value = parse_birth_date(message.text or "")
    if value is None:
        await message.answer("Дата не подходит. Пример правильного формата: 17.09.2003")
        return
    user.birth_date = value
    user.age = calculate_age(value)
    await session.flush()
    await state.clear()
    await _done(message)


@router.callback_query(F.data == "profile:phone")
async def phone_start(call: CallbackQuery, user: User | None, state: FSMContext) -> None:
    if not await _guard(call, user):
        return
    await state.set_state(ProfileSettingsStates.phone)
    await call.message.answer(
        f"Телефон\n\nСейчас: {user.phone or 'не указан'}\n\nОтправьте номер телефона\n\n/cancel — отменить"
    )


@router.message(ProfileSettingsStates.phone)
async def phone_save(
    message: Message,
    user: User | None,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if not await _guard(message, user):
        return
    raw = message.contact.phone_number if message.contact else (message.text or "")
    phone = normalize_phone(raw)
    if phone is None:
        await message.answer("Телефон выглядит некорректно. Пример: +37499123456")
        return
    user.phone = phone
    await session.flush()
    await state.clear()
    await _done(message)


@router.callback_query(F.data == "profile:email")
async def email_start(call: CallbackQuery, user: User | None, state: FSMContext) -> None:
    if not await _guard(call, user):
        return
    await state.set_state(ProfileSettingsStates.email)
    await call.message.answer(
        f"Email\n\nСейчас: {user.email or 'не указан'}\n\nОтправьте новый email\n\n/cancel — отменить"
    )


@router.message(ProfileSettingsStates.email)
@router.message(ProfileSettingsStates.contact_email)
async def email_save(
    message: Message,
    user: User | None,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if not await _guard(message, user):
        return
    email = normalize_email(message.text or "")
    if email is None:
        await message.answer("Почта выглядит некорректно. Пример: name@example.com")
        return
    user.email = email
    profile = await _profile(session, user.id)
    profile.contact_email = email
    profile.updated_at = datetime.now().astimezone()
    await session.flush()
    await state.clear()
    await _done(message)


@router.callback_query(F.data == "profile:photo")
async def photo_menu(
    call: CallbackQuery,
    user: User | None,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if not await _guard(call, user):
        return
    profile = await _profile(session, user.id)
    status = "Фото добавлено" if profile.photo_file_id else "Фото пока не добавлено"
    await state.set_state(ProfileSettingsStates.photo)
    await call.message.answer(
        f"🖼 Фото профиля\n\n{status}\n\nОтправьте новое фото одним сообщением\n\n/cancel — отменить"
    )


@router.message(ProfileSettingsStates.photo, F.photo)
async def photo_save(
    message: Message,
    user: User | None,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if not await _guard(message, user):
        return
    profile = await _profile(session, user.id)
    profile.photo_file_id = message.photo[-1].file_id
    profile.updated_at = datetime.now().astimezone()
    await session.flush()
    await state.clear()
    await _done(message)


@router.message(ProfileSettingsStates.photo)
async def photo_required(message: Message, user: User | None) -> None:
    if not await _guard(message, user):
        return
    await message.answer("Фото обязательно. Отправьте изображение одним сообщением")


@router.message(F.text == "/remove_photo")
async def photo_remove(message: Message, user: User | None, state: FSMContext) -> None:
    if not await _guard(message, user):
        return
    await state.clear()
    await message.answer(
        "Фото профиля обязательно. Его можно заменить новым фото, но нельзя удалить полностью",
        reply_markup=profile_settings_keyboard(),
    )


@router.callback_query(F.data == "profile:socials")
async def socials_menu(
    call: CallbackQuery,
    user: User | None,
    session: AsyncSession,
    state: FSMContext,
) -> None:
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
        text = "🔗 Соцсети\n\n" + "\n".join(
            f"• {link.platform}: {link.url}" for link in links
        )
    else:
        text = "🔗 Соцсети\n\nСсылок пока нет. Добавьте хотя бы одну соцсеть"
    await state.set_state(ProfileSettingsStates.social_url)
    await call.message.answer(
        text
        + "\n\nОтправьте новую ссылку на Telegram, Instagram, LinkedIn или сайт\n\n/cancel — отменить"
    )


@router.message(F.text == "/add_social")
async def social_start(message: Message, user: User | None, state: FSMContext) -> None:
    if not await _guard(message, user):
        return
    await state.set_state(ProfileSettingsStates.social_url)
    await message.answer("Отправьте ссылку на соцсеть или сайт. Например: t.me/username или instagram.com/name")


@router.message(ProfileSettingsStates.social_url)
async def social_save(
    message: Message,
    user: User | None,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if not await _guard(message, user):
        return
    url = _normalize_url(message.text or "")
    if url is None:
        await message.answer("Ссылка выглядит некорректно. Пример: instagram.com/name или t.me/username")
        return
    exists = await session.scalar(
        select(SocialLink).where(SocialLink.user_id == user.id, SocialLink.url == url)
    )
    now = datetime.now().astimezone()
    if exists:
        exists.is_active = True
        exists.platform = _platform_from_url(url)
        exists.updated_at = now
    else:
        session.add(
            SocialLink(
                user_id=user.id,
                url=url,
                platform=_platform_from_url(url),
                created_at=now,
                updated_at=now,
            )
        )
    await session.flush()
    await state.clear()
    await _done(message)


@router.message(F.text == "/cancel")
async def cancel_profile_settings(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=profile_settings_keyboard())
