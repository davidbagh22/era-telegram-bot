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
