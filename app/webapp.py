from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from aiogram.types import BotCommand, MenuButtonDefault, Update
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request

from app.bot import create_bot, create_dispatcher
from app.config import get_settings
from app.database.session import create_engine_and_sessionmaker
from app.services.ai_service import AIService
from app.services.scheduler_service import create_scheduler
from app.services.seed_service import seed_reference_data

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
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
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.bot = bot
    app.state.dispatcher = dispatcher

    # Registration cleanup does not remove FSM keys from Redis. Clear private
    # admin contexts on every deploy so an old date/deadline step cannot trap
    # the operational account after database maintenance.
    for admin_id in settings.admin_ids:
        admin_context = await dispatcher.fsm.get_context(
            bot=bot,
            chat_id=admin_id,
            user_id=admin_id,
        )
        await admin_context.clear()

    app.state.ai_service = AIService(settings)
    scheduler = create_scheduler(bot, settings, session_factory)
    scheduler.start()
    app.state.scheduler = scheduler

    try:
        base_url = settings.effective_base_url
        if base_url:
            webhook_url = f"{base_url}/telegram/webhook"
            await bot.set_webhook(
                webhook_url,
                secret_token=settings.effective_webhook_secret or None,
                allowed_updates=dispatcher.resolve_used_update_types(),
                drop_pending_updates=False,
            )
            await bot.set_chat_menu_button(menu_button=MenuButtonDefault())
            await bot.set_my_commands(
                [
                    BotCommand(command="start", description="Открыть бота ЭРА"),
                    BotCommand(command="menu", description="Главное меню"),
                    BotCommand(command="journey", description="Мой путь"),
                    BotCommand(command="events", description="Мероприятия"),
                    BotCommand(command="projects", description="Проекты"),
                    BotCommand(command="rating", description="Рейтинг"),
                    BotCommand(command="team", description="Команда ЭРА"),
                    BotCommand(command="about", description="Что умеет бот"),
                    BotCommand(command="rules", description="Правила сообщества"),
                ]
            )
            logger.info("Telegram webhook configured: %s", webhook_url)
        else:
            logger.warning("PUBLIC_BASE_URL is not set; Telegram webhook is disabled")
        yield
    finally:
        scheduler.shutdown(wait=False)
        await dispatcher.storage.close()
        await bot.session.close()
        await engine.dispose()


app = FastAPI(
    title="ERA Telegram Bot Service",
    version="2.0.1",
    lifespan=lifespan,
    docs_url=None,
    openapi_url=None,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "2.0.1"}


@app.post("/telegram/webhook", include_in_schema=False)
async def telegram_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    secret: str | None = Header(default=None, alias="X-Telegram-Bot-Api-Secret-Token"),
) -> dict[str, bool]:
    expected_secret = request.app.state.settings.effective_webhook_secret
    if expected_secret and secret != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid webhook secret")
    payload = await request.json()
    update = Update.model_validate(payload, context={"bot": request.app.state.bot})
    background_tasks.add_task(
        request.app.state.dispatcher.feed_update,
        request.app.state.bot,
        update,
    )
    return {"ok": True}
