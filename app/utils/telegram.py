from aiogram.types import Message


async def send_long_text(message: Message, text: str, **kwargs) -> None:
    limit = 3900
    chunks: list[str] = []
    remaining = text.strip()
    while len(remaining) > limit:
        split_at = remaining.rfind("\n", 0, limit)
        if split_at < limit // 2:
            split_at = limit
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)
    for index, chunk in enumerate(chunks):
        await message.answer(chunk, **(kwargs if index == len(chunks) - 1 else {}))


async def edit_text_or_answer(message: Message, text: str, **kwargs) -> None:
    """Same edit/not-modified/send fallback used by the existing FAQ card."""
    from aiogram.exceptions import TelegramBadRequest

    try:
        await message.edit_text(text, **kwargs)
    except TelegramBadRequest as exc:
        detail = str(exc).lower()
        if "not modified" in detail:
            return
        if not any(reason in detail for reason in (
            "message to edit not found", "message can't be edited",
            "message can not be edited", "there is no text in the message to edit",
        )):
            raise
        await message.answer(text, **kwargs)
