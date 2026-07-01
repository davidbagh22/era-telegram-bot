from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def leader_panel_keyboard() -> InlineKeyboardMarkup:
    options = (
        ("✅ Задачи", "leader:tasks"),
        ("➕ Назначить задачу", "leader:task:new"),
        ("📢 Опубликовать задачу", "leader:task:open"),
        ("📥 Заявки на задачи", "leader:task:applications"),
        ("👥 Работа в команде", "leader:participants"),
        ("📋 Мои участники", "leader:participants"),
        ("📅 Предложить мероприятие", "leader:event:new"),
        ("🎖 Предложить поощрение", "leader:proposal:new"),
        ("⬆️ Предложить повышение", "leader:proposal:new"),
        ("🏅 Предложить знак", "leader:proposal:new"),
        ("📁 Предложить документ в портфолио", "leader:proposal:new"),
        ("💬 Связь с председателем", "question:start"),
        ("← Главное меню", "menu:main"),
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=callback)]
            for label, callback in options
        ]
    )
