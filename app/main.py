import asyncio
import logging

from app.bot import create_bot, create_dispatcher
from app.config import get_settings
from app.database.session import create_engine_and_sessionmaker
from app.services.channel_public_content_service import run_daily_channel_content
from app.services.scheduler_service import create_scheduler
from app.services.seed_service import seed_reference_data
from app.services.system_scheduler import add_system_jobs


async def main() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    engine, session_factory = create_engine_and_sessionmaker(settings.database_url)
    async with session_factory() as session:
        await seed_reference_data(session, settings)

    bot = create_bot(settings)
    dispatcher = create_dispatcher(settings, session_factory)
    scheduler = create_scheduler(bot, settings, session_factory)
    add_system_jobs(scheduler, bot, settings, session_factory)

    # Replace the legacy daily public-content job: keep the ERA channel post,
    # but never send automatic quotes into the general chat.
    if scheduler.get_job("era-daily-public-content") is not None:
        scheduler.remove_job("era-daily-public-content")
    scheduler.add_job(
        run_daily_channel_content,
        "interval",
        minutes=5,
        args=(bot, settings, session_factory),
        id="era-daily-channel-content",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    scheduler.start()
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await dispatcher.start_polling(
            bot, allowed_updates=dispatcher.resolve_used_update_types()
        )
    finally:
        scheduler.shutdown(wait=False)
        await dispatcher.storage.close()
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
