from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def leader_panel_keyboard() -> InlineKeyboardMarkup:
    options = (
        ("✅ Задачи", "leader:tasks"),
        ("➕ Назначить задачу", "leader:task:new"),
        ("📢 Опубликовать задачу", "leader:task:open"),
        ("📥 Заявки на задачи", "leader:task:applications"),
        ("👥 Работа в команде", "leader:participants"),
        ("📅 Мои мероприятия", "leader:events"),
        ("💡 Проекты направления", "leader:projects"),
        ("📅 Предложить мероприятие", "leader:event:new"),
        ("✨ Проверка активностей", "leader:event_activities"),
        ("🎖 Предложить поощрение", "leader:proposal:new"),
        ("⬆️ Предложить повышение", "leader:proposal:new"),
        ("🏅 Предложить знак", "leader:proposal:new"),
        ("📁 Предложить документ в портфолио", "leader:proposal:new"),
        ("💬 Связь с председателем", "question:start"),
        ("← Главное меню", "menu:main"),
    )
    rows = [[InlineKeyboardButton(text=label, callback_data=callback)] for label, callback in options]
    return InlineKeyboardMarkup(inline_keyboard=rows)
