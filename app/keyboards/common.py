from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def subscription_keyboard(channel_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Подписаться на канал ЭРА", url=channel_url)],
            [
                InlineKeyboardButton(
                    text="Проверить подписку", callback_data="subscription:check"
                )
            ],
        ]
    )


def registration_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Начать регистрацию", callback_data="registration:start"
                )
            ]
        ]
    )


def back_keyboard(callback: str = "menu:main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data=callback)]]
    )


def yes_no_keyboard(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Да", callback_data=f"{prefix}:yes"),
                InlineKeyboardButton(text="Нет", callback_data=f"{prefix}:no"),
            ]
        ]
    )


def options_keyboard(
    options: list[tuple[str, str]], *, columns: int = 1, back: str | None = None
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label, callback in options:
        builder.button(text=label, callback_data=callback)
    builder.adjust(columns)
    if back:
        builder.row(InlineKeyboardButton(text="Назад", callback_data=back))
    return builder.as_markup()
