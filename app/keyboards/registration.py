from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


DEPARTMENT_OPTIONS = {
    "internal": "Внутренние связи",
    "external": "Внешние связи",
    "both": "Оба департамента",
    "unsure": "Пока не знаю",
}

DIRECTION_OPTIONS = {
    "leadership": "Лидерство",
    "culture": "Культура",
    "interactive": "Интерактив",
    "international": "Международное направление",
    "media": "Медиа",
    "social": "Социальные инициативы",
    "participate": "Пока хочу просто участвовать",
}


def department_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=f"reg:dept:{key}")]
            for key, label in DEPARTMENT_OPTIONS.items()
        ]
    )


def directions_keyboard(
    scope: str, selected: set[str] | None = None
) -> InlineKeyboardMarkup:
    selected = selected or set()
    if scope == "internal":
        keys = ["leadership", "culture", "interactive"]
    elif scope == "external":
        keys = ["international", "media", "social"]
    elif scope == "both":
        keys = [
            "leadership",
            "culture",
            "interactive",
            "international",
            "media",
            "social",
        ]
    else:
        keys = [
            "leadership",
            "media",
            "culture",
            "interactive",
            "social",
            "international",
            "participate",
        ]
    builder = InlineKeyboardBuilder()
    for key in keys:
        mark = "✓ " if key in selected else ""
        builder.button(
            text=mark + DIRECTION_OPTIONS[key], callback_data=f"reg:dir:{key}"
        )
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="Продолжить", callback_data="reg:dir:done"))
    return builder.as_markup()


def time_keyboard() -> InlineKeyboardMarkup:
    values = (
        ("1–2 часа в неделю", "1-2"),
        ("3–5 часов в неделю", "3-5"),
        ("1 час в день", "daily1"),
        ("Несколько часов в день", "daily_more"),
        ("Готов активно включаться", "active"),
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=f"reg:time:{key}")]
            for label, key in values
        ]
    )


def desired_path_keyboard() -> InlineKeyboardMarkup:
    values = (
        "Просто участником",
        "Хочу быть активнее",
        "Хочу помогать команде",
        "Хочу создавать проекты",
        "В будущем хочу стать лидером",
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=value, callback_data=f"reg:path:{index}")]
            for index, value in enumerate(values)
        ]
    )


def consent_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Согласен", callback_data="reg:consent:yes")],
            [InlineKeyboardButton(text="Не согласен", callback_data="reg:consent:no")],
        ]
    )


def pending_registration_keyboard(channel_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Проверить статус заявки",
                    callback_data="registration:status",
                )
            ],
            [InlineKeyboardButton(text="Перейти на канал ЭРА", url=channel_url)],
        ]
    )
