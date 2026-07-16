from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeChat, MenuButtonDefault, Update
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request

from app.bot import create_bot, create_dispatcher
from app.config import get_settings
from app.database.session import create_engine_and_sessionmaker
from app.services.ai_service import AIService
from app.services.scheduler_service import create_scheduler
from app.services.seed_service import seed_reference_data

logger = logging.getLogger(__name__)

# Render sets RENDER_GIT_COMMIT automatically for every deploy; no extra
# render.yaml configuration is needed. Falls back to "unknown" locally
# or on any host that doesn't set it.
DEPLOYED_COMMIT = os.environ.get("RENDER_GIT_COMMIT", "unknown")[:7]


USER_COMMANDS = [
    BotCommand(command="start", description="Открыть бота ЭРА"),
    BotCommand(command="profile", description="Личный кабинет"),
    BotCommand(command="data", description="Мои данные"),
    BotCommand(command="events", description="Афиша"),
    BotCommand(command="tasks", description="Задачи"),
    BotCommand(command="opportunities", description="Возможности"),
    BotCommand(command="points", description="Баллы"),
    BotCommand(command="contact", description="Связь"),
    BotCommand(command="help", description="Что умеет бот"),
]

ADMIN_COMMANDS = USER_COMMANDS + [
    BotCommand(command="panel", description="Панель управления"),
    BotCommand(command="admin_users", description="Участники"),
    BotCommand(command="admin_events", description="События"),
    BotCommand(command="admin_projects", description="Проекты"),
    BotCommand(command="admin_partners", description="Партнёры"),
    BotCommand(command="admin_tasks", description="Задачи"),
    BotCommand(command="admin_rights", description="Должности и права"),
]

LAST_KEEPER_COMMANDS = [
    BotCommand(command="start", description="Войти в Архив"),
    BotCommand(command="admin", description="Панель Архивариуса"),
]


def _set_temporary_environment(values: dict[str, str]) -> dict[str, str | None]:
    previous: dict[str, str | None] = {}
    for key, value in values.items():
        previous[key] = os.environ.get(key)
        os.environ[key] = value
    return previous


def _restore_environment(previous: dict[str, str | None]) -> None:
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


async def configure_last_keeper(app: FastAPI, base_url: str | None, default_secret: str | None) -> None:
    """Configure the second Telegram bot on the same FastAPI service.

    A webhook is used instead of a background polling process. This is important
    on Render's web-service plan: an incoming Telegram webhook can wake the
    service, while an outbound polling loop cannot.
    """

    app.state.last_keeper_status = "disabled"
    app.state.last_keeper_bot = None
    app.state.last_keeper_dispatcher = None
    app.state.last_keeper_webhook_secret = None

    token = os.environ.get("LAST_KEEPER_BOT_TOKEN", "").strip()
    if not token:
        logger.warning("LAST_KEEPER_BOT_TOKEN is not configured; Last Keeper bot is disabled")
        return
    if not base_url:
        app.state.last_keeper_status = "missing-public-base-url"
        logger.error("Last Keeper token is configured, but PUBLIC_BASE_URL is missing")
        return

    env_values = {
        "BOT_TOKEN": token,
        "ADMIN_IDS": os.environ.get("LAST_KEEPER_ADMIN_IDS", os.environ.get("ADMIN_IDS", "")),
        "DATABASE_PATH": os.environ.get("LAST_KEEPER_DATABASE_PATH", "/tmp/last_keeper.db"),
    }
    previous = _set_temporary_environment(env_values)
    try:
        from last_keeper_bot.bot import init_db, router as last_keeper_router
    finally:
        _restore_environment(previous)

    last_keeper_bot = Bot(token)
    last_keeper_dispatcher = Dispatcher(storage=MemoryStorage())
    last_keeper_dispatcher.include_router(last_keeper_router)
    webhook_secret = os.environ.get("LAST_KEEPER_WEBHOOK_SECRET", "").strip() or default_secret
    webhook_url = f"{base_url.rstrip('/')}/telegram/last-keeper-webhook?v=1.1.0"

    try:
        identity = await last_keeper_bot.get_me()
        await init_db()
        await last_keeper_bot.set_webhook(
            webhook_url,
            secret_token=webhook_secret or None,
            allowed_updates=last_keeper_dispatcher.resolve_used_update_types(),
            drop_pending_updates=False,
        )
        await last_keeper_bot.set_chat_menu_button(menu_button=MenuButtonDefault())
        await last_keeper_bot.set_my_commands(LAST_KEEPER_COMMANDS)
    except Exception:
        app.state.last_keeper_status = "startup-error"
        logger.exception("Last Keeper bot failed during startup")
        await last_keeper_dispatcher.storage.close()
        await last_keeper_bot.session.close()
        return

    app.state.last_keeper_bot = last_keeper_bot
    app.state.last_keeper_dispatcher = last_keeper_dispatcher
    app.state.last_keeper_webhook_secret = webhook_secret
    app.state.last_keeper_status = "ok"
    logger.info("Last Keeper webhook configured for @%s: %s", identity.username, webhook_url)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    logger.info("Starting ERA bot, commit=%s", DEPLOYED_COMMIT)

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

    # Redis is dedicated to aiogram FSM storage in this service. Clear stale
    # production forms on deploy; PostgreSQL user and organization data is
    # stored separately and is not affected.
    recovery_marker = "era:recovery:fsm-global-v2"
    redis_client = dispatcher.storage.redis
    if not await redis_client.exists(recovery_marker):
        await redis_client.flushdb()
        await redis_client.set(recovery_marker, "done")
        logger.warning("Redis FSM storage cleared during recovery deploy")

    app.state.ai_service = AIService(settings)
    scheduler = create_scheduler(bot, settings, session_factory)
    scheduler.start()
    app.state.scheduler = scheduler

    try:
        base_url = settings.effective_base_url
        if base_url:
            webhook_url = f"{base_url.rstrip('/')}/telegram/webhook?v=2.1.0"
            await bot.set_webhook(
                webhook_url,
                secret_token=settings.effective_webhook_secret or None,
                allowed_updates=dispatcher.resolve_used_update_types(),
                drop_pending_updates=False,
            )
            await bot.set_chat_menu_button(menu_button=MenuButtonDefault())
            await bot.set_my_commands(USER_COMMANDS)
            for admin_id in settings.admin_ids:
                await bot.set_my_commands(
                    ADMIN_COMMANDS,
                    scope=BotCommandScopeChat(chat_id=admin_id),
                )
            logger.info("Telegram webhook configured: %s", webhook_url)
        else:
            logger.warning("PUBLIC_BASE_URL is not set; Telegram webhook is disabled")

        await configure_last_keeper(app, base_url, settings.effective_webhook_secret)
        yield
    finally:
        scheduler.shutdown(wait=False)
        last_keeper_dispatcher = getattr(app.state, "last_keeper_dispatcher", None)
        last_keeper_bot = getattr(app.state, "last_keeper_bot", None)
        if last_keeper_dispatcher is not None:
            await last_keeper_dispatcher.storage.close()
        if last_keeper_bot is not None:
            await last_keeper_bot.session.close()
        await dispatcher.storage.close()
        await bot.session.close()
        await engine.dispose()


app = FastAPI(
    title="ERA Telegram Bot Service",
    version="2.2.0",
    lifespan=lifespan,
    docs_url=None,
    openapi_url=None,
)


@app.get("/health")
async def health(request: Request) -> dict[str, str]:
    return {
        "status": "ok",
        "version": "2.2.0",
        "commit": DEPLOYED_COMMIT,
        "last_keeper": getattr(request.app.state, "last_keeper_status", "starting"),
    }


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


@app.post("/telegram/last-keeper-webhook", include_in_schema=False)
async def last_keeper_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    secret: str | None = Header(default=None, alias="X-Telegram-Bot-Api-Secret-Token"),
) -> dict[str, bool]:
    last_keeper_bot = getattr(request.app.state, "last_keeper_bot", None)
    last_keeper_dispatcher = getattr(request.app.state, "last_keeper_dispatcher", None)
    if last_keeper_bot is None or last_keeper_dispatcher is None:
        raise HTTPException(status_code=503, detail="Last Keeper bot is disabled")

    expected_secret = getattr(request.app.state, "last_keeper_webhook_secret", None)
    if expected_secret and secret != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    payload = await request.json()
    update = Update.model_validate(payload, context={"bot": last_keeper_bot})
    background_tasks.add_task(last_keeper_dispatcher.feed_update, last_keeper_bot, update)
    return {"ok": True}
