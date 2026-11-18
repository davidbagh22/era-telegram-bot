from __future__ import annotations

from collections.abc import Iterable
from typing import Any


WELCOME_START = """Добро пожаловать в ЭРА.

Здесь собираются встречи, задачи, проекты и идеи — с баллами, портфолио, рейтингом и новыми возможностями.

Начните с регистрации: откроем личный кабинет и подскажем первый шаг."""

MAIN_MENU = """🔥 ЭРА

События, проекты, задания и возможности — в одном месте.

Выберите раздел."""

LEGACY_KEYBOARD_CLEARED = "Обновили ЭРА — теперь всё через кнопки в сообщениях и Mini App, старое меню внизу больше не нужно."

MAIN_INLINE_MENU = """🔥 <b>ЭРА</b>

События, проекты, задания и возможности — в одном месте.

<b>Выберите раздел.</b>"""

CABINET_EMPTY_HINT = """Пока здесь пусто.

После первого мероприятия, задачи или проекта в кабинете появится Ваша активность."""

EVENTS_LIST_HEADER = """Афиша ЭРА

Выберите событие. Участие попадёт в Ваш путь, баллы и портфолио."""

EVENTS_EMPTY = """В афише пока нет событий.

Можно открыть задачи, выбрать направление или предложить идею проекта."""

TASKS_MENU = """Мои задачи

Задачи — быстрый способ включиться в работу ЭРА. Выберите, что посмотреть."""

TASKS_EMPTY_ACTIVE = """Активных задач пока нет.

Загляните в афишу или предложите свою идею — новые задачи появятся здесь."""

TASKS_EMPTY_ARCHIVE = """Архив задач пока пустой.

Здесь появятся завершённые задачи, которые Вы сдали."""

OPPORTUNITIES_MENU = """Возможности

Ваш баланс: {balance} баллов.

Баллы начисляются за участие и результат. Их можно обменивать на партнёрские предложения, награды и специальные форматы ЭРА."""

REWARDS_MENU = """Возможности за баллы

Ваш баланс: {balance} баллов.

Каталог показывает, на что можно обменять баллы: награды, партнёрские предложения и специальные форматы."""

REWARDS_EMPTY = """Каталог пока пустой.

Продолжайте участвовать и копить баллы — новые предложения появятся здесь."""

CONTACT_MENU = """Связь

Можно задать вопрос, найти команду, открыть правила или перейти к департаментам."""

CONTACT_CALLBACK = """Связь

Выберите, что нужно: вопрос, команда, правила или информация о боте."""

TEAM_MENU = """Команда ЭРА

Здесь видно, кто ведёт направления, где чаты и куда подключаться."""

ANALYTICS_EMPTY = """Аналитика пока пустая.

Как только появятся участники, события, задачи и цели, здесь будет сводка по ЭРА."""


def profile_missing_fields(user: Any) -> list[str]:
    checks = (
        ("возраст", getattr(user, "age", None)),
        ("город", getattr(user, "city", None)),
        ("учёба / работа", getattr(user, "education_work", None)),
        ("email", getattr(user, "email", None)),
        ("телефон", getattr(user, "phone", None)),
    )
    return [label for label, value in checks if not value]


def profile_empty_hint(user: Any) -> str:
    missing = profile_missing_fields(user)
    if not missing:
        return ""
    visible = ", ".join(missing[:3])
    tail = " и ещё" if len(missing) > 3 else ""
    return (
        "\n\nМожно дополнить профиль: "
        f"{visible}{tail}. Это поможет с портфолио, документами и подходящими возможностями."
    )


def journey_intro(name: str, has_activity: bool) -> str:
    if has_activity:
        return f"{name}, здесь собраны Ваше участие, задачи, проекты, баллы и достижения."
    return f"{name}, кабинет только открыт. Первое действие в ЭРА уже появится здесь."


def cabinet_home_text(name: str, status: str, points: int, place: int | str) -> str:
    """Shared cabinet root copy for reply-keyboard and cabinet:open."""
    return (
        f"👤 Ваш путь в ЭРА\n\n"
        f"{name}, данные, задачи, портфолио и баллы — здесь.\n\n"
        f"Статус: {status}\n"
        f"Баланс: {points} баллов\n"
        f"Место в рейтинге: {place}\n\n"
        "Выберите следующий шаг."
    )


def rating_text(rows: Iterable[tuple[str, int]], current_place: int | str, points: int) -> str:
    top = "\n".join(
        f"{index}. {name} — {score}"
        for index, (name, score) in enumerate(rows, 1)
    )
    if not top:
        top = "Рейтинг пока пустой. Он появится после первых подтверждённых действий."
    return f"""Рейтинг ЭРА

Ваше место: {current_place}
Ваши баллы: {points}

Топ участников:
{top}

Рейтинг показывает тех, кто участвует, помогает и берёт ответственность."""


def analytics_summary(
    *,
    users: int,
    approved: int,
    pending: int,
    events: int,
    projects: int,
    contacts: int,
    goals: int,
) -> str:
    base = (
        "Аналитика ЭРА\n\n"
        f"Участников в базе: {users}\n"
        f"Одобрены: {approved}\n"
        f"Новые заявки: {pending}\n"
        f"Мероприятий: {events}\n"
        f"Проектов: {projects}\n"
        f"Организаций в базе: {contacts}\n"
        f"Целей месяца: {goals}"
    )
    if not any((users, events, projects, contacts, goals)):
        return f"{base}\n\n{ANALYTICS_EMPTY}"
    return f"{base}\n\nМожно скачать всю книгу или только нужный раздел."
