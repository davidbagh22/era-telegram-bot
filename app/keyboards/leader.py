from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def leader_panel_keyboard() -> InlineKeyboardMarkup:
    options = (
        ("Мой департамент", "leader:department"),
        ("Участники", "leader:participants"),
        ("Мероприятия", "leader:events"),
        ("Создать мероприятие", "leader:event:new"),
        ("Задачи", "leader:tasks"),
        ("Создать задачу", "leader:task:new"),
        ("Отчёты", "leader:reports"),
        ("Проекты", "leader:projects"),
        ("Предложения админу", "leader:proposal:new"),
        ("Рассылка", "leader:broadcast:new"),
        ("Связь с председателем", "question:start"),
        ("Главное меню", "menu:main"),
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=callback)]
            for label, callback in options
        ]
    )
