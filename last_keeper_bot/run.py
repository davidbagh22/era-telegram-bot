import asyncio

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot import init_db, log, router, settings


async def main() -> None:
    await init_db()
    bot = Bot(settings.bot_token)
    await bot.delete_webhook(drop_pending_updates=False)
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(router)
    log.info("Last Keeper bot started in polling mode")
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
