from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def faq_keyboard() -> InlineKeyboardMarkup:
    """Attached to the pinned FAQ card in the general chat (see
    app/services/chat_faq_service.py). Every button's callback_data is
    handled by app/handlers/chat_faq.py, which answers into the tapper's
    own DM -- these callback_data values are the single source of truth
    for that mapping, so don't rename one without updating the handler."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌟 Что такое ЭРА?", callback_data="faq:what_is_era")],
            [InlineKeyboardButton(text="🎁 Что мне это даст?", callback_data="faq:what_it_gives")],
            [InlineKeyboardButton(text="🙋 Что я могу сделать?", callback_data="faq:what_can_i_do")],
            [InlineKeyboardButton(text="🚀 Что мне делать?", callback_data="faq:what_to_do")],
            [InlineKeyboardButton(text="💬 Связь", callback_data="faq:contact")],
        ]
    )
