from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
from sqlalchemy import func, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Badge, PointTransaction, PortfolioItem, User, UserBadge
from app.database.socials import SocialLink, SocialProfile
from app.keyboards.admin import admin_user_actions, application_actions
from app.services.minors_service import is_minor
from app.services.notification_service import notify_admins_once, safe_answer_photo
from app.utils.constants import APPLICATION_STATUS_LABELS, PERMISSION_LABELS, ROLE_LABELS, STATUS_LABELS
from app.utils.deep_links import miniapp_path_url

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AdminUserCard:
    text: str
    photo_file_id: str | None
    reply_markup: InlineKeyboardMarkup


def _label(mapping: dict, value: object, fallback: str = "не указан") -> str:
    if value is None:
        return fallback
    try:
        return mapping.get(type(next(iter(mapping)))(value), str(value))
    except Exception:
        return mapping.get(value, str(value))


def _name(user: User) -> str:
    return f"{user.first_name} {user.last_name or ''}".strip()


def _telegram(user: User) -> str:
    return f"@{user.username}" if user.username else str(user.telegram_id)


def _date_text(value: date | None) -> str:
    return value.strftime("%d.%m.%Y") if value else "не указана"


def _created_at_text(user: User) -> str:
    value = getattr(user, "created_at", None)
    return value.strftime("%d.%m.%Y %H:%M") if value else "не указана"


def _minor_label(age: int | None) -> str | None:
    minor = is_minor(age)
    if minor is None:
        return None
    return "да" if minor else "нет"


def _lines(title: str, rows: list[tuple[str, str | None]]) -> str:
    visible = [f"{label}: {value or 'не указано'}" for label, value in rows]
    return title + "\n" + "\n".join(visible)


async def _socials(session: AsyncSession, user_id: int) -> tuple[str | None, str]:
    profile = await session.scalar(select(SocialProfile).where(SocialProfile.user_id == user_id))
    links = (
        await session.scalars(
            select(SocialLink)
            .where(SocialLink.user_id == user_id, SocialLink.is_active.is_(True))
            .order_by(SocialLink.platform, SocialLink.url)
        )
    ).all()
    social_text = "\n".join(f"{link.platform}: {link.url}" for link in links)
    return (profile.photo_file_id if profile else None), social_text or "не указаны"


async def _activity_summary(session: AsyncSession, target: User) -> tuple[int, int, str]:
    points = int(
        await session.scalar(
            select(func.coalesce(func.sum(PointTransaction.points), 0)).where(
                PointTransaction.user_id == target.id
            )
        )
        or 0
    )
    portfolio_count = int(
        await session.scalar(
            select(func.count()).select_from(PortfolioItem).where(PortfolioItem.user_id == target.id)
        )
        or 0
    )
    badges = (
        await session.scalars(
            select(Badge)
            .join(UserBadge, UserBadge.badge_id == Badge.id)
            .where(UserBadge.user_id == target.id)
            .order_by(Badge.name)
        )
    ).all()
    badge_names = ", ".join(badge.name for badge in badges) or "пока нет"
    return points, portfolio_count, badge_names


def _departments(target: User) -> str:
    return ", ".join(link.department.name for link in target.departments) or "не выбраны"


def _directions(target: User) -> str:
    return ", ".join(link.direction.name for link in target.directions) or "не выбраны"


def _permissions(target: User) -> str:
    active = [
        grant.permission
        for grant in (getattr(target, "permission_grants", None) or [])
        if grant.is_active
    ]
    return ", ".join(PERMISSION_LABELS.get(item, item) for item in sorted(active)) or "нет отдельных прав"


def _application_miniapp_markup(
    reply_markup: InlineKeyboardMarkup, miniapp_url: str, user_id: int
) -> InlineKeyboardMarkup:
    if not miniapp_url:
        return reply_markup
    url = miniapp_path_url(
        miniapp_url, "admin", {"adminSection": "applications", "applicationId": user_id}
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📲 Открыть заявку в приложении", web_app=WebAppInfo(url=url)
                )
            ],
            *reply_markup.inline_keyboard,
        ]
    )


def _automatic_application_markup(miniapp_url: str, user_id: int) -> InlineKeyboardMarkup | None:
    """Open the full application in the bot or the existing Admin UI."""
    rows = [[InlineKeyboardButton(text="📥 Открыть заявку в боте", callback_data=f"admin:application:{user_id}")]]
    if not miniapp_url:
        return InlineKeyboardMarkup(inline_keyboard=rows)
    url = miniapp_path_url(
        miniapp_url, "admin", {"adminSection": "applications", "applicationId": user_id}
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[*rows,
            [InlineKeyboardButton(text="Открыть в управлении ЭРА", web_app=WebAppInfo(url=url))]
        ]
    )


async def build_admin_user_card(
    session: AsyncSession, target: User, *, mode: str = "profile"
) -> AdminUserCard:
    # Registration creates a User in this same session. selectin relationships
    # are not populated merely by INSERT/commit, and reading them synchronously
    # below would issue async IO outside greenlet_spawn. Reload only unloaded
    # attributes, under await, without replacing pending in-memory edits.
    state = inspect(target)
    if state.persistent:
        required = {"departments", "directions", "permission_grants", "created_at"}
        missing = sorted(required & state.unloaded)
        if missing:
            await session.refresh(target, attribute_names=missing)
    photo_file_id, social_text = await _socials(session, target.id)
    points, portfolio_count, badge_names = await _activity_summary(session, target)
    base = [
        ("Имя", _name(target)),
        ("Telegram", _telegram(target)),
    ]
    if getattr(target, "birth_date", None):
        base.append(("Дата рождения", _date_text(target.birth_date)))
    base.extend(
        [
            ("Возраст", str(target.age) if target.age else None),
            ("Несовершеннолетний (по анкете)", _minor_label(target.age)),
            ("Страна", getattr(target, "country", None)),
            ("Регион / город", getattr(target, "region", None) or target.city),
            ("Email", target.email),
        ]
    )
    if target.phone:
        base.append(("Телефон", target.phone))
    structure = [
        ("Роль", _label(ROLE_LABELS, target.role)),
        ("Статус", _label(STATUS_LABELS, target.participation_status)),
        ("Заявка", _label(APPLICATION_STATUS_LABELS, target.application_status)),
        ("Блокировка", "да" if target.is_blocked else "нет"),
        ("Архив", "да" if target.is_archived else "нет"),
        ("Департаменты", _departments(target)),
        ("Направления", _directions(target)),
    ]
    activity = [
        ("Баланс", f"{points} баллов"),
        ("Портфолио", str(portfolio_count)),
        ("Знаки", badge_names),
        ("Права", _permissions(target)),
    ]
    if mode == "application":
        title = f"📝 Заявка #{target.id}"
        skills = ", ".join(getattr(target, "skills", None) or []) or "не указаны"
        extra = (
            "\n\n"
            + _lines(
                "Что важно для решения",
                [
                    ("Учёба / работа", target.education_work),
                    ("Занятие", target.occupation),
                    ("Навыки", skills),
                    ("Опыт", getattr(target, "experience", None)),
                    ("Доступное время", target.available_time),
                    ("Желаемый путь", target.desired_path),
                    (
                        "Согласие на обработку данных",
                        "получено" if target.personal_data_consent else "не получено",
                    ),
                    ("Дата подачи", _created_at_text(target)),
                ],
            )
            + f"\n\nСоцсети\n{social_text}"
            + f"\n\nМотивация\n{target.motivation or 'не указана'}"
        )
        reply_markup = application_actions(target.id)
    else:
        title = f"👤 Участник #{target.id}"
        extra = f"\n\nСоцсети\n{social_text}"
        reply_markup = admin_user_actions(target.id)
    text = (
        f"{title}\n\n"
        + _lines("Профиль", base)
        + "\n\n"
        + _lines("ЭРА", structure)
        + "\n\n"
        + _lines("Активность", activity)
        + extra
    )
    return AdminUserCard(text=text, photo_file_id=photo_file_id, reply_markup=reply_markup)


async def send_admin_user_card(
    message: Message, session: AsyncSession, target: User, *, mode: str = "profile",
    review_version: int | None = None,
) -> None:
    card = await build_admin_user_card(session, target, mode=mode)
    markup = card.reply_markup
    if review_version is not None and mode == "application":
        from app.utils.constants import ApplicationStatus
        markup = (
            application_actions(target.id, review_version=review_version)
            if target.application_status in {ApplicationStatus.PENDING, ApplicationStatus.NEEDS_INFO}
            else InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="← Заявки", callback_data="admin:applications")]])
        )
    if card.photo_file_id:
        if not await safe_answer_photo(message, card.photo_file_id, caption="Фото участника"):
            await message.answer('Фото недоступно в Telegram. Участник может загрузить его заново в настройках профиля.')
    # Questionnaire values are plain text, never Telegram markup. Long answers
    # are split so a valid application cannot become unreadable at 4096 chars.
    chunks = [card.text[index:index+2000] for index in range(0, len(card.text), 2000)]
    for index, chunk in enumerate(chunks):
        await message.answer(chunk, parse_mode=None,
                             reply_markup=markup if index == len(chunks)-1 else None)


async def send_admin_application_cards(
    bot: Bot, settings: Settings, session: AsyncSession, target: User,
    *, notification_revision: int | None = None,
) -> tuple[int, int]:
    """Post-commit, idempotent new-registration notice for administrators."""
    card = await build_admin_user_card(session, target, mode="application")
    reply_markup = _automatic_application_markup(settings.effective_miniapp_url, target.id)
    # Telegram photo captions are limited to 1024 characters. Keep the full
    # questionnaire available through the existing guarded application action.
    limit = 900 if card.photo_file_id else 1800
    encoded = card.text.encode('utf-16-le')
    summary = card.text if len(encoded) <= limit*2 else (
        encoded[:(limit-80)*2].decode('utf-16-le', errors='ignore')
        + "\n\nПолная анкета — по кнопке ниже."
    )
    sent, failed, duplicates = await notify_admins_once(
        bot,
        settings,
        summary,
        delivery_key=f"admin:registration:{target.id}:submitted" + (f":{notification_revision}" if notification_revision is not None else ""),
        notification_type="registration_submitted",
        reply_markup=reply_markup,
        **({'photo': card.photo_file_id} if card.photo_file_id else {}),
        parse_mode='',
    )
    if sent == 0 and duplicates == 0:
        logger.error("Application card delivery failed for all recipients user_id=%s", target.id)
        raise RuntimeError("application_card_delivery_failed")
    if failed:
        logger.warning(
            "Application card delivery partially failed user_id=%s failed=%s", target.id, failed
        )
    return sent, failed
