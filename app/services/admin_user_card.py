from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Badge, PointTransaction, PortfolioItem, User, UserBadge
from app.database.socials import SocialLink, SocialProfile
from app.keyboards.admin import admin_user_actions, application_actions
from app.services.minors_service import is_minor
from app.services.notification_service import (
    admin_notification_recipients,
    safe_answer_photo,
    safe_send,
    safe_send_photo,
)
from app.utils.constants import (
    APPLICATION_STATUS_LABELS,
    PERMISSION_LABELS,
    ROLE_LABELS,
    STATUS_LABELS,
)
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
    profile = await session.scalar(
        select(SocialProfile).where(SocialProfile.user_id == user_id)
    )
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
            select(func.count())
            .select_from(PortfolioItem)
            .where(PortfolioItem.user_id == target.id)
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
    reply_markup: InlineKeyboardMarkup,
    miniapp_url: str,
    user_id: int,
) -> InlineKeyboardMarkup:
    if not miniapp_url:
        return reply_markup
    url = miniapp_path_url(
        miniapp_url,
        "admin",
        {"adminSection": "applications", "applicationId": user_id},
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📲 Открыть заявку в приложении",
                    web_app=WebAppInfo(url=url),
                )
            ],
            *reply_markup.inline_keyboard,
        ]
    )


async def build_admin_user_card(
    session: AsyncSession,
    target: User,
    *,
    mode: str = "profile",
) -> AdminUserCard:
    photo_file_id, social_text = await _socials(session, target.id)
    points, portfolio_count, badge_names = await _activity_summary(session, target)

    base = [
        ("Имя", _name(target)),
        ("Telegram", _telegram(target)),
        ("Дата рождения", _date_text(getattr(target, "birth_date", None))),
        ("Возраст", str(target.age) if target.age else None),
        # Informational only — see app/services/minors_service.py. Does not
        # gate or restrict anything; the platform owner has not yet made a
        # decision on minors handling (docs/PRODUCTION_READINESS_AUDIT.md
        # finding #17).
        ("Несовершеннолетний (по анкете)", _minor_label(target.age)),
        ("Город", target.city),
        ("Телефон", target.phone),
        ("Email", target.email),
    ]
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
                    ("Согласие на обработку данных", "получено" if target.personal_data_consent else "не получено"),
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

    photo_note = "" if photo_file_id else "\nФото: не загружено"
    text = (
        f"{title}{photo_note}\n\n"
        + _lines("Профиль", base)
        + "\n\n"
        + _lines("ЭРА", structure)
        + "\n\n"
        + _lines("Активность", activity)
        + extra
    )
    return AdminUserCard(text=text, photo_file_id=photo_file_id, reply_markup=reply_markup)


async def send_admin_user_card(
    message: Message,
    session: AsyncSession,
    target: User,
    *,
    mode: str = "profile",
) -> None:
    card = await build_admin_user_card(session, target, mode=mode)
    if card.photo_file_id:
        await safe_answer_photo(message, card.photo_file_id, caption="Фото участника")
    await message.answer(card.text, reply_markup=card.reply_markup)


async def send_admin_application_cards(
    bot: Bot,
    settings: Settings,
    session: AsyncSession,
    target: User,
) -> tuple[int, int]:
    card = await build_admin_user_card(session, target, mode="application")
    reply_markup = _application_miniapp_markup(
        card.reply_markup,
        settings.effective_miniapp_url,
        target.id,
    )
    recipients = await admin_notification_recipients(settings)
    sent = failed = 0
    for chat_id in recipients:
        if card.photo_file_id:
            await safe_send_photo(
                bot,
                chat_id,
                card.photo_file_id,
                caption=f"🆕 Новая заявка #{target.id}\n{_name(target)}",
            )
        if await safe_send(bot, chat_id, card.text, reply_markup):
            sent += 1
        else:
            failed += 1
    if not recipients:
        logger.error("Application card was not sent: no admin recipients found")
    return sent, failed
