from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def leader_panel_keyboard() -> InlineKeyboardMarkup:
    options = (
        ("🌿 Мой контур", "leader:department"),
        ("👥 Моя команда", "leader:participants"),
        ("💡 Проекты команды", "leader:projects"),
        ("📅 Мероприятия команды", "leader:events"),
        ("➕ Предложить мероприятие", "leader:event:new"),
        ("✅ Задания команды", "leader:tasks"),
        ("➕ Назначить задание", "leader:task:new"),
        ("⭐ Предложить поощрение или роль", "leader:proposal:new"),
        ("📣 Предложить рассылку", "leader:broadcast:new"),
        ("Связь с председателем", "question:start"),
        ("← Главное меню", "menu:main"),
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=callback)]
            for label, callback in options
        ]
    )
