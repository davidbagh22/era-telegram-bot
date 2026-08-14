from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def faq_keyboard() -> InlineKeyboardMarkup:
    """Fast private-help actions attached to the pinned general-chat FAQ."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔥 Что такое ЭРА", callback_data="faq:what_is_era")],
            [InlineKeyboardButton(text="🚀 Как здесь расти", callback_data="faq:what_it_gives")],
            [InlineKeyboardButton(text="🧭 С чего начать", callback_data="faq:what_to_do")],
            [InlineKeyboardButton(text="💡 Как предложить идею", callback_data="faq:what_can_i_do")],
            [InlineKeyboardButton(text="💬 Задать вопрос", callback_data="faq:contact")],
        ]
    )
