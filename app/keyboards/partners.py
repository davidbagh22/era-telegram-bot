from collections.abc import Iterable

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def _url_row(label: str, url: str | None) -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text=label, url=url)] if url else []


def partner_list_keyboard(partners: Iterable) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=partner.name[:50], callback_data=f"partner:view:{partner.id}")]
        for partner in partners
    ]
    rows.append([InlineKeyboardButton(text="← Возможности", callback_data="rewards:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def partner_card_keyboard(partner) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    source_row = _url_row("Открыть источник", partner.source_url)
    if source_row:
        rows.append(source_row)
    rows.append([InlineKeyboardButton(text="← Партнёры", callback_data="partners:list")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_partners_keyboard(partners: Iterable = ()) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="Добавить партнёра", callback_data="admin:partner:add")]]
    for partner in partners:
        status = "🟢" if partner.is_active else "⚪️"
        rows.append([InlineKeyboardButton(text=f"{status} {partner.name[:42]}", callback_data=f"admin:partner:view:{partner.id}")])
    rows.append([InlineKeyboardButton(text="← Развитие", callback_data="admin:menu:growth")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_partner_card_keyboard(partner_id: int, active: bool = True) -> InlineKeyboardMarkup:
    toggle_text = "Выключить" if active else "Включить"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Добавить инициативу", callback_data=f"admin:partner:add_initiative:{partner_id}")],
            [InlineKeyboardButton(text="Добавить задание", callback_data=f"admin:partner:add_task:{partner_id}")],
            [InlineKeyboardButton(text="Изменить ссылку", callback_data=f"admin:partner:edit_url:{partner_id}")],
            [InlineKeyboardButton(text=toggle_text, callback_data=f"admin:partner:toggle:{partner_id}")],
            [InlineKeyboardButton(text="Архив", callback_data=f"admin:partner:archive:{partner_id}")],
            [InlineKeyboardButton(text="← Партнёры", callback_data="admin:partners")],
        ]
    )
